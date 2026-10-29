"""W12-06 복원 후 삭제 재적용: 공개 전 확인이 스냅숏 복원 DB를 재적용 전에는 막고, 재적용 뒤에만 연다."""

import asyncio
import json
import os
import secrets
from uuid import UUID, uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.core.business_errors import AppError
from app.persistence import Base
from manage_restore import check, main, schema_current
from tests.test_deletions import configured
from tests.test_member_auth import headers
from tests.test_member_lifecycle_matrix import reauth
from tests.test_migrations import migration_config
from tests.test_save_intents import run
from tests.test_saved_material_editing import editing

ACTIONS = ['profile_delete', 'application_delete', 'storage_withdraw', 'ai_withdraw', 'account_delete']
READY = {'reapplied': 1, 'retried': 0, 'checked_events': 1, 'ready_to_publish': True, 'problems': {}}


def dump(engine):
    """격리 시험 DB 전체의 스냅숏. 운영 RDS 복원이 아니라 같은 효과(모든 표가 과거 시점으로)를 재현한다."""
    with engine.connect() as db:
        return [(table, [dict(row) for row in db.execute(table.select()).mappings()]) for table in Base.metadata.sorted_tables]


def load(engine, snapshot):
    with engine.begin() as db:
        for table, _ in reversed(snapshot): db.execute(table.delete())
        for table, rows in snapshot:
            if rows: db.execute(insert(table), rows)


async def delete(browser, action, document):
    if action == 'account_delete':
        await reauth(browser)
        return await browser.delete('/api/v1/me', headers=headers(browser))
    if action == 'profile_delete': return await browser.delete('/api/v1/profiles/me', headers=headers(browser))
    if action == 'application_delete':
        return await browser.delete('/api/v1/drafts/' + document['document_id'], headers=headers(browser))
    purpose = 'storage' if action == 'storage_withdraw' else 'ai_processing'
    return await browser.post('/api/v1/consents/withdraw', json={'purpose': purpose}, headers=headers(browser))


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
@pytest.mark.parametrize('action', ACTIONS)
def test_restored_snapshot_opens_only_after_latest_deletion_is_reapplied(tmp_path, backend, action):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); _, document, _, _, _ = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        snapshot = dump(ctx['engine'])
        assert (await delete(browser, action, document)).status_code in {200, 204}
        # 삭제 직후 DB(복원 전)도 그대로 통과한다. recover는 이미 끝난 이력에 대해 멱등이다.
        assert await check(service, ctx['engine'], 1000) == READY

        load(ctx['engine'], snapshot)
        stale = await check(service, ctx['engine'], 1000, reapply=False)
        assert stale == {'reapplied': 0, 'retried': 0, 'checked_events': 1, 'ready_to_publish': False,
            'problems': {'record_missing': 1, 'session_not_revoked': 1, 'target_remains': 1}}

        result = await check(service, ctx['engine'], 1000)
        assert result == READY and str(user_id) not in json.dumps(result)
        assert (await check(service, ctx['engine'], 1000, reapply=False))['ready_to_publish'] is True
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_deletion_in_flight_at_snapshot_time_is_finished_before_publish(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        append = service.journal.append

        def unavailable(event): raise AppError('SERVICE_UNAVAILABLE')
        # 외부 이력이 확정되기 전에 스냅숏이 찍힌 요청: DB에는 대기 기록과 원래 자료가 함께 남는다.
        service.journal.append = unavailable
        assert (await browser.delete('/api/v1/profiles/me', headers=headers(browser))).status_code == 503
        service.journal.append = append
        stale = await check(service, ctx['engine'], 1000, reapply=False)
        assert stale['ready_to_publish'] is False and stale['problems'] == {'deletions_waiting': 1}
        result = await check(service, ctx['engine'], 1000)
        assert result == {**READY, 'reapplied': 0, 'retried': 1}
    run(tmp_path, scenario, backend)


def test_schema_behind_head_fails_closed_without_reapplying(tmp_path):
    engine = create_engine('sqlite:///' + (tmp_path / 'restored.db').as_posix())

    class Untouched:
        class journal:
            @staticmethod
            def check(): raise AssertionError('스키마가 옛 버전이면 이력도 읽지 않는다')

        async def recover(self, limit): raise AssertionError('스키마가 옛 버전이면 재적용하지 않는다')

    try:
        with engine.begin() as db: command.upgrade(migration_config(db), 'head')
        with engine.connect() as db: assert schema_current(db)
        with engine.begin() as db: command.downgrade(migration_config(db), '-1')
        with engine.connect() as db: assert not schema_current(db)
        result = asyncio.run(check(Untouched(), engine, 1000))
        assert result['ready_to_publish'] is False and result['problems'] == {'schema_not_current': 1}
    finally:
        engine.dispose()


@pytest.mark.parametrize(('report', 'code'), [(READY, 0), ({**READY, 'ready_to_publish': False, 'problems': {'target_remains': 2}}, 1)])
def test_exit_code_follows_publish_verdict(capsys, report, code):
    async def runner(limit, reapply):
        assert (limit, reapply) == (1000, True)
        return report
    assert main([], runner) == code
    assert json.loads(capsys.readouterr().out) == {'completed': True, **report}


def test_unavailable_journal_or_over_limit_closes_without_details(capsys):
    async def runner(limit, reapply):
        assert (limit, reapply) == (5, False)
        raise AppError('SERVICE_UNAVAILABLE')
    assert main(['--limit', '5', '--verify-only'], runner) == 2
    assert json.loads(capsys.readouterr().out) == {'completed': False, 'ready_to_publish': False, 'code': 'SERVICE_UNAVAILABLE'}


@pytest.mark.parametrize('limit', ['0', '1001'])
def test_limit_must_stay_within_recovery_bound(limit):
    with pytest.raises(SystemExit):
        main(['--limit', limit], lambda *args: None)


class NoEvents:
    """삭제 이력이 없는 버킷. 권한 시험에서 DB 조회만 보게 한다."""
    @staticmethod
    def check(): return None

    @staticmethod
    def events(now, *, limit): return []


def test_runtime_like_role_with_read_only_version_table_passes_verify_only():
    """grant_runtime.sql과 같은 권한(일반 표 DML + alembic_version 읽기만)의 실제 계정으로 확인이 끝나야 한다."""
    url = os.environ.get('PERSISTENCE_TEST_DATABASE_URL')
    if url is None: pytest.skip('PostgreSQL 실행 환경 없음. CI의 DB/Redis 통합 잡에서 실행한다')
    schema, role, password = 'test_' + uuid4().hex, 'restore_check_' + uuid4().hex[:12], secrets.token_hex(16)
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    restricted = create_engine(make_url(url).set(username=role, password=password), connect_args={'options': f'-csearch_path={schema}'})
    try:
        with admin.connect() as db:
            db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            db.exec_driver_sql(f'SET search_path TO "{schema}"')
            command.upgrade(migration_config(db), 'head')
            db.exec_driver_sql(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{password}' NOSUPERUSER NOINHERIT")
            db.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            db.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
            db.exec_driver_sql(f'REVOKE ALL ON TABLE "{schema}".alembic_version FROM "{role}"')
        # 고치기 전 정책(버전 표 접근 없음): 스키마 확인이 권한 오류로 막힌다.
        with restricted.connect() as db, pytest.raises(ProgrammingError):
            schema_current(db)
        with admin.connect() as db: db.exec_driver_sql(f'GRANT SELECT ON TABLE "{schema}".alembic_version TO "{role}"')

        class Service:
            journal = NoEvents()
        result = asyncio.run(check(Service(), restricted, 1000, reapply=False))
        assert result == {'reapplied': 0, 'retried': 0, 'checked_events': 0, 'ready_to_publish': True, 'problems': {}}
        with restricted.connect() as db:
            for sql in ("INSERT INTO alembic_version VALUES ('unapproved')", 'DELETE FROM alembic_version'):
                with pytest.raises(ProgrammingError): db.execute(text(sql))
                db.rollback()
    finally:
        restricted.dispose()
        with admin.connect() as db:
            db.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            db.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        admin.dispose()
