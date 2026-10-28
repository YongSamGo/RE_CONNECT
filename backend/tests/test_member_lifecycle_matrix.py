"""W13-03: 로그인 취소·저장 대기 만료, 동시 탈퇴·철회, 늦은 결과, 복원 뒤 재삭제의 회원 흔적 시험."""

import asyncio
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import String, Uuid, func, insert, or_, select

from app.persistence import Base, DeletionRecord, ProfileVersion, ProfileWriteReceipt, User
from tests.test_deletions import another_session, configured, count
from tests.test_member_auth import headers, login, start as oauth_start
from tests.test_save_intents import create, grant, run, save_login
from tests.test_saved_journey_import import start
from tests.test_saved_material_editing import editing
from tests.test_saved_profiles import configured as configure_profile, post as profile_save, request_body as profile_body

# 삭제 뒤에도 복원 재적용을 위해 회원 ID를 최소 이력으로 남기는 표다. 본문·외부 ID는 없다.
HISTORY_TABLES = {'deletion_records', 'audit_events'}
WITHDRAW_PURPOSES = {'storage_withdraw': 'storage', 'ai_withdraw': 'ai_processing'}


async def reauth(browser):
    state = await oauth_start(browser, 'reauth')
    result = await browser.get('/api/v1/auth/kakao/callback', params={'state': state, 'code': 'fixture-code'})
    assert result.headers['location'].endswith('purpose=reauth&status=success')


def member_rows(ctx, user_id):
    """회원 ID를 UUID 칸 어디에든 가진 행. 표·칸을 스키마에서 다시 읽어 새 표가 생겨도 빠지지 않는다."""
    rows = []
    with ctx['engine'].connect() as db:
        for table in Base.metadata.sorted_tables:
            columns = [column for column in table.columns if isinstance(column.type, Uuid)]
            if table.name in HISTORY_TABLES or not columns: continue
            found = db.execute(select(table).where(or_(*(column == user_id for column in columns)))).mappings().all()
            rows += [(table, dict(row)) for row in found]
    return rows


def sql_traces(ctx, user_id, subject):
    traces = {table.name for table, _ in member_rows(ctx, user_id)}
    with ctx['engine'].connect() as db:
        for table in Base.metadata.sorted_tables:
            columns = [column for column in table.columns if isinstance(column.type, String)]
            if columns and db.scalar(select(func.count()).select_from(table).where(or_(*(column == subject for column in columns)))):
                traces.add(table.name)
    return traces


async def member_needles(ctx, user_id, journeys):
    """회원 세션 다이제스트·체험 ID·회원 ID. 시험마다 새로 만든 값이라 다른 시험의 키와 섞이지 않는다."""
    index = ctx['members'].store.member_prefix + str(user_id) + ':sessions'
    return {str(user_id), *await ctx['redis'].smembers(index), *(str(value) for value in journeys)}


async def redis_traces(ctx, needles):
    client, prefix = ctx['redis'], ctx['sessions'].store.prefix.removesuffix('sessions:')
    readers = {'string': client.get, 'hash': client.hgetall, 'set': client.smembers, 'list': lambda key: client.lrange(key, 0, -1),
        'zset': lambda key: client.zrange(key, 0, -1)}
    found = []
    async for key in client.scan_iter(match=prefix + '*'):
        value = await readers[await client.type(key)](key) if await client.type(key) in readers else ''
        if any(needle in key or needle in str(value) for needle in needles): found.append(key)
    return found


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_cancelled_login_discards_pending_save_and_new_attempt_saves_exactly_once(tmp_path, backend):
    async def scenario(ctx, browser):
        configure_profile(ctx); ctx['journeys'].stored_profiles = ctx['app'].state.saved_profile_service
        cancelled_intent = await create(ctx, browser, draft=False)
        state = await oauth_start(browser, 'save')
        cancelled = await browser.get('/api/v1/auth/kakao/callback', params={'state': state, 'error': 'access_denied'})
        assert cancelled.headers['location'].endswith('purpose=save&status=cancelled')
        assert await ctx['intents'].reference(ctx['issued'].session) is None
        assert count(ctx, User) == 0 and not (await browser.get('/api/v1/me')).json()['authenticated']
        # 취소로 소비한 state를 승인 코드와 다시 보내도 로그인·저장이 되지 않는다.
        reused = await browser.get('/api/v1/auth/kakao/callback', params={'state': state, 'code': 'fixture-code'})
        assert not reused.headers['location'].endswith('status=success') and count(ctx, User) == 0
        # 비회원 체험은 남아 있어 새 저장 대기로 다시 시도할 수 있다.
        intent = await create(ctx, browser, draft=False)
        assert intent['save_intent_id'] != cancelled_intent['save_intent_id']
        await save_login(browser); await grant(browser)
        stale = await profile_save(browser, profile_body(cancelled_intent['save_intent_id']))
        assert stale.status_code == 404 and stale.json()['code'] == 'SAVE_INTENT_NOT_FOUND'
        key = str(uuid4()); saved = await profile_save(browser, profile_body(intent['save_intent_id']), key)
        assert saved.status_code == 201, saved.text
        assert (await profile_save(browser, profile_body(intent['save_intent_id']), key)).json() == saved.json()
        other_key = await profile_save(browser, profile_body(intent['save_intent_id']))
        assert other_key.status_code == 409 and other_key.json()['code'] == 'REQUEST_ALREADY_COMPLETED'
        assert count(ctx, ProfileVersion) == count(ctx, ProfileWriteReceipt) == 1
    run(tmp_path, scenario, backend)


def test_save_intent_expiring_after_login_saves_nothing_and_keeps_member_signed_in(tmp_path):
    async def scenario(ctx, browser):
        configure_profile(ctx); ctx['journeys'].stored_profiles = ctx['app'].state.saved_profile_service
        intent = await create(ctx, browser, draft=False); await save_login(browser); await grant(browser)
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        await ctx['redis'].hset(ctx['intents'].store.key(session.digest), 'expires_ms', 1)
        expired = await profile_save(browser, profile_body(intent['save_intent_id']))
        assert expired.status_code == 404 and expired.json()['code'] == 'SAVE_INTENT_NOT_FOUND'
        assert count(ctx, ProfileVersion) == count(ctx, ProfileWriteReceipt) == 0
        me = (await browser.get('/api/v1/me')).json()
        assert me['authenticated'] and me['pending_save_intent'] is None
        assert (await browser.get('/api/v1/profiles/me')).json()['saved'] is None
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_account_deletion_leaves_no_member_trace_in_sql_or_redis(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == user_id))
        second = await another_session(ctx, browser)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.5', 30001)), base_url='https://testserver') as device:
            device.cookies.set('__Host-rc_session', second.token, domain='testserver.local', path='/'); await device.get('/api/v1/me')
            other = (await start(device, (await device.get('/api/v1/profiles/me')).json()['saved'])).json()
            needles = await member_needles(ctx, user_id, [journey['journey_id'], other['journey_id']])
            assert len(needles) >= 5 and await redis_traces(ctx, needles)
            assert {'users', 'consents', 'profile_documents', 'profile_versions', 'application_documents', 'application_drafts'} <= sql_traces(ctx, user_id, subject)
            await reauth(browser)
            assert (await browser.delete('/api/v1/me', headers=headers(browser))).status_code == 204
            assert not (await device.get('/api/v1/me')).json()['authenticated']
        assert sql_traces(ctx, user_id, subject) == set() and await redis_traces(ctx, needles) == []
        with ctx['engine'].connect() as db:
            history = db.execute(select(DeletionRecord.scope, DeletionRecord.status).where(DeletionRecord.owner_id == user_id)).all()
        assert ('account', 'completed') in history
        assert await service.retry() == 0
        assert (await browser.delete('/api/v1/me', headers=headers(browser))).status_code == 401
    run(tmp_path, scenario, backend)


def test_postgresql_account_deletion_from_two_devices_at_once_completes_once(tmp_path):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == user_id))
        second = await another_session(ctx, browser)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.5', 30001)), base_url='https://testserver') as device:
            device.cookies.set('__Host-rc_session', second.token, domain='testserver.local', path='/'); await device.get('/api/v1/me')
            await reauth(browser); await reauth(device)
            needles = await member_needles(ctx, user_id, [journey['journey_id']])
            began, release = Event(), Event(); prepare = service.repository.prepare
            def paused(*args):
                result = prepare(*args)
                if not began.is_set():
                    began.set()
                    if not release.wait(5): raise RuntimeError('시험 삭제 대기 만료')
                return result
            service.repository.prepare = paused
            first = asyncio.create_task(browser.delete('/api/v1/me', headers=headers(browser)))
            assert await asyncio.to_thread(began.wait, 5)
            later = asyncio.create_task(device.delete('/api/v1/me', headers=headers(device)))
            try:
                await asyncio.sleep(.05); assert not later.done()
            finally: release.set()
            results = [await first, await later]
        # 먼저 끝난 탈퇴가 모든 세션을 폐기해 늦은 요청은 두 번째 삭제를 만들지 않는다.
        assert results[0].status_code == 204 and results[1].status_code == 401, [result.text for result in results]
        assert results[1].json()['code'] == 'SESSION_EXPIRED'
        with ctx['engine'].connect() as db:
            accounts = db.scalar(select(func.count()).select_from(DeletionRecord).where(DeletionRecord.owner_id == user_id, DeletionRecord.scope == 'account'))
        assert accounts == 1 and await service.retry() == 0
        assert sql_traces(ctx, user_id, subject) == set() and await redis_traces(ctx, needles) == []
    run(tmp_path, scenario, 'postgresql')


def test_postgresql_storage_withdrawal_racing_account_deletion_leaves_nothing_behind(tmp_path):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == user_id))
        second = await another_session(ctx, browser)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.5', 30001)), base_url='https://testserver') as device:
            device.cookies.set('__Host-rc_session', second.token, domain='testserver.local', path='/'); await device.get('/api/v1/me')
            await reauth(browser)
            needles = await member_needles(ctx, user_id, [journey['journey_id']])
            began, release = Event(), Event(); prepare = service.repository.prepare
            def paused(*args):
                result = prepare(*args)
                if not began.is_set():
                    began.set()
                    if not release.wait(5): raise RuntimeError('시험 삭제 대기 만료')
                return result
            service.repository.prepare = paused
            deleting = asyncio.create_task(browser.delete('/api/v1/me', headers=headers(browser)))
            assert await asyncio.to_thread(began.wait, 5)
            withdrawing = asyncio.create_task(device.post('/api/v1/consents/withdraw', json={'purpose': 'storage'}, headers=headers(device)))
            try:
                await asyncio.sleep(.05); assert not withdrawing.done()
            finally: release.set()
            deleted, withdrawn = await deleting, await withdrawing
        assert deleted.status_code == 204, deleted.text
        assert withdrawn.status_code == 401 and withdrawn.json()['code'] == 'SESSION_EXPIRED', withdrawn.text
        assert await service.retry() == 0
        assert sql_traces(ctx, user_id, subject) == set() and await redis_traces(ctx, needles) == []
    run(tmp_path, scenario, 'postgresql')


@pytest.mark.parametrize('action', ['account_delete', 'storage_withdraw', 'ai_withdraw'])
def test_late_ai_draft_after_deletion_or_withdrawal_recreates_nothing(tmp_path, action):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); _, _, _, journey, request = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        if action == 'account_delete': await reauth(browser)
        runtime = ctx['app'].state.draft_service.llm._runtime
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        path, key = f"/api/v1/journeys/{journey['journey_id']}/drafts", str(uuid4())
        value = {'profile_version': 1, 'opportunity': request['opportunity'], 'mode': 'generate', 'saved_document': None}
        old = dict(browser.cookies)
        generating = asyncio.create_task(browser.post(path, json=value, headers={**headers(browser), 'Idempotency-Key': key}))
        await asyncio.wait_for(runtime.started.wait(), 3)
        needles = await member_needles(ctx, user_id, [journey['journey_id']]) - {str(user_id)}
        assert await redis_traces(ctx, needles)
        if action == 'account_delete': result = await browser.delete('/api/v1/me', headers=headers(browser))
        else: result = await browser.post('/api/v1/consents/withdraw', json={'purpose': WITHDRAW_PURPOSES[action]}, headers=headers(browser))
        assert result.status_code in {200, 204}, result.text
        runtime.finish.set()
        late = await generating
        assert late.status_code == 404 and late.json()['code'] == 'NOT_FOUND', late.text
        assert await redis_traces(ctx, needles) == []
        # 옛 쿠키로 같은 키를 다시 보내도 지운 체험을 되살리거나 모델을 다시 부르지 않는다.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app']), base_url='https://testserver') as replay:
            for name, cookie in old.items(): replay.cookies.set(name, cookie, domain='testserver.local', path='/')
            assert (await replay.post(path, json=value, headers={**headers(replay), 'Idempotency-Key': key})).status_code in {401, 403, 404}
        assert await redis_traces(ctx, needles) == [] and runtime.calls == 1
        assert count(ctx, ProfileVersion) == (1 if action == 'ai_withdraw' else 0)
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_account_restored_from_backup_snapshot_is_deleted_again_before_reopening(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == user_id))
        # 운영 복원이 아닌, 격리 시험 DB에서 삭제 전 백업(암호문 그대로)을 재현한다.
        snapshot = member_rows(ctx, user_id)
        assert {table.name for table, _ in snapshot} >= {'users', 'profile_versions', 'application_drafts'}
        await reauth(browser)
        assert (await browser.delete('/api/v1/me', headers=headers(browser))).status_code == 204
        assert sql_traces(ctx, user_id, subject) == set()
        with ctx['engine'].begin() as db:
            db.execute(DeletionRecord.__table__.delete())
            for table, row in snapshot: db.execute(insert(table), [row])
        assert count(ctx, User) == 1 and count(ctx, DeletionRecord) == 0
        assert await service.recover() == 1
        assert sql_traces(ctx, user_id, subject) == set()
        with ctx['engine'].connect() as db:
            assert db.scalar(select(DeletionRecord.status).where(DeletionRecord.owner_id == user_id, DeletionRecord.scope == 'account')) == 'completed'
        # 복구 재적용 뒤 같은 카카오 계정의 로그인은 새 회원이고 옛 저장본을 보지 못한다.
        assert (await login(browser)).headers['location'].endswith('status=success')
        me = (await browser.get('/api/v1/me')).json()
        assert me['user']['id'] != str(user_id) and (await browser.get('/api/v1/profiles/me')).json()['saved'] is None
        await service.recover()
        assert (await browser.get('/api/v1/me')).json()['user']['id'] == me['user']['id']
    run(tmp_path, scenario, backend)
