"""운영자용 공유 추론 슬롯 확인·복구. 앱 밖에서만 실행하며 공개 API로 열지 않는다.

`release`는 모든 LLM/STT/TTS 런타임의 정지와 작업 배출을 운영자가 확인한 뒤에만 쓴다.
일일 집계는 바꾸지 않고, `status`가 보여 준 lease가 그대로일 때만 슬롯을 비운다.
비밀값·세대 UUID·원 lease token은 출력하지 않는다.
"""

import argparse
import asyncio
import json
import re

from redis.exceptions import RedisError

from app.adapters.redis import build_redis
from app.core.business_errors import AppError
from app.core.config import get_settings
from app.modules.admission.repository import RedisAdmissionStore
from app.modules.admission.service import AdmissionService

_LEASE = re.compile(r"[0-9a-f]{16}")


async def execute(command, lease=None):
    settings = get_settings()
    if settings.redis_url is None or settings.request_limit_key is None or settings.inference_control_epoch is None:
        raise AppError('SERVICE_UNAVAILABLE')
    client = build_redis(settings)
    try:
        store = RedisAdmissionStore(client, epoch=settings.inference_control_epoch)
        key_id = AdmissionService(store, identity_key=bytes.fromhex(settings.request_limit_key.get_secret_value())).identity_key_id
        if command == 'status':
            status = await store.slot_status(key_id)
            return {'ready': status.ready, 'day': status.day, 'global': status.global_count,
                    'active': status.lease is not None, 'kind': status.kind, 'lease': status.lease}
        return {'result': await store.recover(key_id, lease)}
    finally:
        await client.aclose()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='공유 추론 슬롯 상태 확인 또는 런타임 정지 확인 후 슬롯 해제')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='세대·키 일치, 일일 집계, 점유 중인 lease 지문 확인')
    release = commands.add_parser('release', help='status의 lease 지문이 그대로일 때만 슬롯을 비운다')
    release.add_argument('--lease', required=True, help='status가 출력한 16자리 lease 지문')
    release.add_argument('--confirm-runtime-stopped', action='store_true',
                         help='모든 LLM/STT/TTS 런타임의 정지와 작업 배출을 확인했다')
    args = parser.parse_args(argv)
    if args.command == 'release':
        if not _LEASE.fullmatch(args.lease):
            parser.error('lease는 status가 출력한 16자리 소문자 hex입니다')
        if not args.confirm_runtime_stopped:
            parser.error('모든 런타임 정지를 확인한 뒤 --confirm-runtime-stopped를 함께 지정합니다')
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        result = asyncio.run(execute(args.command, getattr(args, 'lease', None)))
    except (AppError, OSError, ValueError, RedisError):
        print(json.dumps({'completed': False, 'code': 'SERVICE_UNAVAILABLE'}))
        return 1
    print(json.dumps({'completed': True, **result}))
    return 1 if result.get('result') == 'lease_changed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
