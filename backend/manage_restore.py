"""복원 DB 공개 전 확인 (W12-06): 스키마 최신 → 최신 삭제 이력 재적용 → 대기 처리 → 대상 부재 검사.

복원 체크리스트 5~7단계를 한 번에 묶는다 (docs/security/backup-restore.md).
`ready_to_publish: true`(종료 코드 0)가 아니면 운영 연결을 바꾸거나 API를 열지 않는다.
출력은 건수와 판정뿐이다. 회원 ID·대상 ID·본문은 출력하지 않는다.
"""

import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.config import get_settings
from app.persistence import (ApplicationDocument, ApplicationDraft, ApplicationWriteReceipt, Consent, DeletionRecord,
    ProfileDocument, ProfileVersion, ProfileWriteReceipt, User)

MAX_EVENTS = 1000
RETRY_BATCH = 100
# 재적용 직후 남은 대기는 복원 시점에 진행 중이던 요청뿐이다. 끝없이 돌지 않게 횟수를 제한한다.
MAX_RETRY_ROUNDS = 10
WITHDRAW_PURPOSE = {'storage_withdraw': 'storage', 'ai_withdraw': 'ai_processing'}


def schema_current(connection):
    """복원 DB가 현재 이미지의 Alembic head인가. 옛 스냅샷은 migrate 뒤에만 재적용한다."""
    script = ScriptDirectory.from_config(Config(str(Path(__file__).with_name('alembic.ini'))))
    return set(MigrationContext.configure(connection).get_current_heads()) == set(script.get_heads())


def _any(db, *condition):
    return db.scalar(select(exists().where(*condition)))


def remaining(db, event):
    """이력의 삭제 대상이 아직 DB에 남아 있는가. remove()가 지우는 범위와 같게 본다."""
    owner = event.owner_id
    if event.action == 'account_delete':
        return any(_any(db, model.owner_id == owner) for model in (ProfileDocument, ProfileVersion, ApplicationDocument,
            ApplicationDraft, ApplicationWriteReceipt, ProfileWriteReceipt, Consent)) or _any(db, User.id == owner)
    if event.action == 'application_delete':
        return (_any(db, ApplicationDocument.owner_id == owner, ApplicationDocument.id == event.target_id)
            or _any(db, ApplicationDraft.owner_id == owner, ApplicationDraft.document_id == event.target_id))
    found = False
    if event.action in {'profile_delete', 'storage_withdraw'}:
        found = any(_any(db, model.owner_id == owner, model.profile_id == event.target_id)
            for model in (ProfileVersion, ApplicationDocument, ApplicationDraft)) or _any(
            db, ProfileDocument.owner_id == owner, ProfileDocument.id == event.target_id)
    if event.action in WITHDRAW_PURPOSE:
        found = found or _any(db, Consent.owner_id == owner, Consent.purpose == WITHDRAW_PURPOSE[event.action],
            Consent.accepted_at <= event.deleted_at, Consent.withdrawn_at.is_(None))
    return found


def inspect(db, events):
    """읽기만 한다. 문제 종류별 건수를 돌려준다."""
    problems = Counter()
    for event in events:
        record = db.get(DeletionRecord, event.id)
        if record is None: problems['record_missing'] += 1
        elif {name: getattr(record, name) for name in ('owner_id', 'scope', 'target_id', 'action', 'generation')} != {
                name: getattr(event, name) for name in ('owner_id', 'scope', 'target_id', 'action', 'generation')}:
            problems['record_mismatch'] += 1
        elif record.status != 'completed': problems['record_not_completed'] += 1
        if remaining(db, event): problems['target_remains'] += 1
        generation = db.scalar(select(User.session_generation).where(User.id == event.owner_id))
        if generation is not None and generation < event.generation: problems['session_not_revoked'] += 1
    waiting = db.scalar(select(func.count()).select_from(DeletionRecord).where(DeletionRecord.status.in_(['pending', 'failed'])))
    if waiting: problems['deletions_waiting'] = waiting
    return problems


async def check(service, engine, limit, *, reapply=True):
    report = {'reapplied': 0, 'retried': 0, 'checked_events': 0}
    with engine.connect() as connection:
        current = await asyncio.to_thread(schema_current, connection)
    if not current:
        # 옛 스키마에 현재 모델로 지우면 일부 표를 놓칠 수 있다. 재적용하지 않고 닫는다.
        return {**report, 'ready_to_publish': False, 'problems': {'schema_not_current': 1}}
    await asyncio.to_thread(service.journal.check)
    if reapply:
        report['reapplied'] = await service.recover(limit)
        for _ in range(MAX_RETRY_ROUNDS):
            done = await service.retry(RETRY_BATCH)
            report['retried'] += done
            if done < RETRY_BATCH: break
    events = await asyncio.to_thread(service.journal.events, utc_now(), limit=limit)
    report['checked_events'] = len(events)

    def examine():
        with Session(engine) as db:
            return inspect(db, events)
    problems = await asyncio.to_thread(examine)
    return {**report, 'ready_to_publish': not problems, 'problems': dict(sorted(problems.items()))}


async def execute(limit, reapply):
    settings = get_settings()
    if settings.database_url is None or settings.redis_url is None:
        raise AppError('SERVICE_UNAVAILABLE')
    from app.main import create_app
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        return await check(app.state.deletion_service, app.state.db_engine, limit, reapply=reapply)


def main(argv=None, runner=execute):
    parser = argparse.ArgumentParser(description='복원 DB 공개 전 삭제 재적용과 확인 (출력은 건수뿐)')
    parser.add_argument('--limit', type=int, default=MAX_EVENTS)
    parser.add_argument('--verify-only', action='store_true', help='재적용 없이 읽기 전용으로 다시 확인')
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_EVENTS: parser.error(f'limit은 1~{MAX_EVENTS}입니다')
    try:
        report = asyncio.run(runner(args.limit, not args.verify_only))
    except (AppError, OSError, ValueError, ValidationError, RedisError, SQLAlchemyError):
        # 오류 본문에는 연결 정보·식별자가 섞일 수 있어 출력하지 않는다. 한도 초과도 여기로 닫힌다.
        print(json.dumps({'completed': False, 'ready_to_publish': False, 'code': 'SERVICE_UNAVAILABLE'}))
        return 2
    print(json.dumps({'completed': True, **report}))
    return 0 if report['ready_to_publish'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
