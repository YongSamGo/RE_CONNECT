"""폐기 가능한 로컬 Compose 전용. backend에서 python -m tools.fault_drill로 실행한다.

Redis 재시작은 모든 임시 데이터를 지운다. DB는 tmpfs 보존을 위해 pause만 사용한다.
실제 모델 대신 종료가 확인되는 admission 콜백을 사용하며 모델 readiness는 닫힌 포트다.
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import subprocess  # nosec B404 - 고정 로컬 명령 인자만 실행한다.
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.core.business_errors import AppError, ERRORS
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.repository import RedisAdmissionStore
from app.modules.admission.service import InferenceIdentity

ROOT = Path(__file__).resolve().parents[2]


def compose(action, service):
    docker = shutil.which('docker')
    if docker is None or (action, service) not in {
        ('stop', 'redis'), ('start', 'redis'), ('pause', 'postgres'), ('unpause', 'postgres')
    }:
        raise RuntimeError('COMPOSE_FAILED')
    result = subprocess.run(  # nosec B603 - 절대 실행 파일·고정 경로·허용 목록 인자, 셸 사용 안 함.
        [docker, 'compose', '-p', 'reconnect-dev', '--env-file', str(ROOT / '.env.example'), '-f',
         str(ROOT / 'infra/compose.dev.yaml'), action, service],
        cwd=ROOT, shell=False, timeout=45, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError('COMPOSE_FAILED')


def local_url(name, schemes, port):
    value = os.environ[name]
    parsed = urlsplit(value)
    if parsed.scheme not in schemes or parsed.hostname != '127.0.0.1' or parsed.port != port:
        raise ValueError('LOCAL_CONFIG_REQUIRED')
    return value


async def record(stage, name, operation):
    row = {'stage': stage, 'probe': name}
    try:
        result = await asyncio.wait_for(operation(), 15)
        if isinstance(result, httpx.Response):
            row['status'] = result.status_code
            body = result.json()
            if name == 'ready':
                row['readiness'] = body.get('status') if body.get('status') in {'ready', 'degraded', 'unavailable'} else 'invalid'
                row['checks'] = {key: body.get('checks', {}).get(key) if body.get('checks', {}).get(key) in {'ok', 'fail'} else 'invalid'
                                 for key in ('db', 'redis', 'llm', 'speech')}
            elif body.get('code') in ERRORS:
                row['code'] = body['code']
            retry = result.headers.get('Retry-After', '')
            row['retry_after'] = int(retry) if retry.isdigit() and 1 <= int(retry) <= 86400 else None
        else:
            row.update(status=200, code='ok', retry_after=None)
    except AppError as exc:
        row.update(status=ERRORS[exc.code].status, code=exc.code, retry_after=exc.retry_after)
    except TimeoutError:
        row['result'] = 'timeout'
    except Exception:  # 원문 오류·URL·응답 본문은 출력하지 않는다.
        row['result'] = 'probe_failed'
    print(json.dumps(row), flush=True)
    return row


async def drill():
    database = local_url('PERSISTENCE_TEST_DATABASE_URL', {'postgresql+psycopg'}, 5432)
    redis = local_url('PERSISTENCE_TEST_REDIS_URL', {'redis'}, 6379)
    settings = Settings(_env_file=None, app_env='test', database_url=database, redis_url=redis,
                        request_limit_key=secrets.token_hex(32), inference_control_epoch=uuid4(),
                        ollama_base_url='http://127.0.0.1:1')
    app = create_app(settings)
    rows = []
    redis_stopped = db_paused = False
    async with app.router.lifespan_context(app):
        store = RedisAdmissionStore(app.state.redis, epoch=settings.inference_control_epoch)
        admission = app.state.admission_service
        # 기존 제어 기록이 있으면 삭제하거나 덮어쓰지 않고 종료한다.
        if await store.initialize(admission.identity_key_id, no_runs_today=True) != 'initialized':
            raise RuntimeError('CONTROL_EXISTS')
        async def ended(completion):
            completion.confirm_ended()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver') as client:
            async def snapshot(stage):
                for name, path in [('ready', '/health/ready'), ('regions', '/api/v1/regions'),
                                   ('opportunities', '/api/v1/opportunities'), ('me', '/api/v1/me')]:
                    rows.append(await record(stage, name, lambda path=path: client.get(path)))
                for kind in ('llm', 'stt', 'tts'):
                    rows.append(await record(stage, kind, lambda kind=kind: admission.run(
                        InferenceIdentity(uuid4(), '192.0.2.1'), kind, ended)))
            try:
                await snapshot('baseline')
                redis_stopped = True
                await asyncio.to_thread(compose, 'stop', 'redis')
                await snapshot('redis_stopped')
                await asyncio.to_thread(compose, 'start', 'redis')
                redis_stopped = False
                for _ in range(30):
                    try:
                        if await app.state.redis.ping():
                            break
                    except Exception:
                        await asyncio.sleep(0.2)
                        continue
                    await asyncio.sleep(0.2)
                else:
                    raise RuntimeError('REDIS_START_FAILED')
                await snapshot('redis_restarted')
                if await store.initialize(admission.identity_key_id, no_runs_today=False) != 'initialized':
                    raise RuntimeError('INIT_FAILED')
                await snapshot('default_init')
                db_paused = True
                await asyncio.to_thread(compose, 'pause', 'postgres')
                await snapshot('postgres_paused')
                await asyncio.to_thread(compose, 'unpause', 'postgres')
                db_paused = False
                await snapshot('postgres_resumed')
            finally:
                try:
                    if db_paused:
                        await asyncio.to_thread(compose, 'unpause', 'postgres')
                finally:
                    if redis_stopped:
                        await asyncio.to_thread(compose, 'start', 'redis')
    return 1 if any('result' in row for row in rows) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-disposable-local', action='store_true', required=True)
    parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        return asyncio.run(drill())
    except Exception:
        print(json.dumps({'completed': False, 'code': 'DRILL_FAILED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
