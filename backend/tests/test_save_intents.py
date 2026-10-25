"""실제 Redis·SQL·ASGI 일회 전달: 인가 SEC-02, CSRF INP-11, TOCTOU TIM-01."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import sessionmaker

from app.contracts.save_intents import SaveIntentCreate
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.auth.accounts import SqlAccountRepository
from app.modules.auth.member_store import RedisMemberStore
from app.modules.auth.members import MemberService
from app.modules.auth.repository import RedisFlowStore
from app.modules.auth.service import OAuthService
from app.modules.consents.repository import RedisConsentStore, SQLConsentStore, RoutedConsentStore
from app.modules.consents.service import ConsentService
from app.modules.drafts.repository import RedisDraftStore
from app.modules.drafts.service import DraftService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.requests.service import RequestScope, ResultReference, RequestService
from app.modules.save_intents.policy import SqlSaveIntentPolicy
from app.modules.save_intents.repository import RedisSaveIntentStore
from app.modules.save_intents.service import SaveIntentService
from app.persistence import Consent, ProfileDocument, ProfileVersion, User
from tests.ingestion_helpers import ingestion_database
from tests.test_admission import with_redis
from tests.test_consents import AI_VERSION, STORAGE_VERSION
from tests.test_journeys import BODY, real_services
from tests.test_journey_drafts import Runtime, body as draft_body
from tests.test_kakao_auth import adapter, responses
from tests.test_member_auth import headers, login, start
from tests.test_profile_confirmation import ready_edit
from tests.test_public_opportunities import seeded


@pytest.mark.parametrize('changes', [{'profile': {'version': True}}, {'draft': {'draft_id': '../other', 'revision': 1}},
    {'body': '클라이언트 원문'}, {'owner_id': str(uuid4())}, {'profile': {'version': 0}}])
def test_contract_rejects_identity_body_and_untrusted_versions(changes):
    with pytest.raises(ValidationError):
        SaveIntentCreate.model_validate({'journey_id': str(uuid4()), 'profile': {'version': 1}, 'draft': None, **changes})


def run(tmp_path, scenario, backend='sqlite'):
    with ingestion_database(backend, tmp_path) as (engine, _):
        async def redis_scenario(admission, control, redis):
            issued, sessions, journeys, store, requests, identity = await real_services(admission, control, redis)
            app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
            members = MemberService(SqlAccountRepository(sessionmaker(engine).begin),
                RedisMemberStore(redis, session_prefix=sessions.store.prefix, flow_prefix=control.prefix + 'oauth:'),
                sessions, transition=app.state.member_service.transition)
            consents = ConsentService(RoutedConsentStore(RedisConsentStore(redis, session_key=sessions.store.key), SQLConsentStore(engine)),
                ai_version=AI_VERSION, storage_version=STORAGE_VERSION)
            intents = SaveIntentService(RedisSaveIntentStore(redis, session_key=sessions.store.key, resource_key=requests.resource_key),
                members, consents, SqlSaveIntentPolicy(sessionmaker(engine).begin))
            members.save_intents = intents
            app.state.member_service, app.state.save_intent_service, app.state.consent_service = members, intents, consents
            app.state.session_service, app.state.admission_service, app.state.journey_service = sessions, admission, journeys
            app.state.oauth_service = OAuthService(RedisFlowStore(redis, session_prefix=sessions.store.prefix, prefix=control.prefix + 'oauth:'),
                adapter(responses), members)
            with engine.begin() as db:
                from app.contracts.time import utc_now
                seeded(db)(1, requirements=[], source_checked_at=utc_now(), reviewed_at=utc_now())
            drafts = DraftService(RedisDraftStore(redis, session_key=sessions.store.key, resource_key=requests.resource_key),
                journeys, PublicOpportunityService(SqlPublicOpportunityRepository(engine.connect)), ControlledLLMAdapter(Runtime(), admission))
            journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
            await journeys.confirm_profile(issued.session, journey.journey_id, 2)
            draft = await drafts.create(issued.session, identity, journey.journey_id, str(uuid4()), draft_body())
            approved = await drafts.approve(issued.session, journey.journey_id, draft.draft_id, 1)
            ctx = dict(app=app, members=members, consents=consents, intents=intents, redis=redis, sessions=sessions,
                journeys=journeys, requests=requests, issued=issued, journey=journey, draft=approved, engine=engine)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as browser:
                browser.cookies.set('__Host-rc_session', issued.token, domain='testserver.local', path='/')
                await browser.get('/api/v1/me')
                await scenario(ctx, browser)
        with_redis(redis_scenario)


def body(ctx, *, draft=True):
    return {'journey_id': str(ctx['journey'].journey_id), 'profile': {'version': 1},
        'draft': {'draft_id': str(ctx['draft'].draft_id), 'revision': ctx['draft'].revision} if draft else None}


async def create(ctx, browser, *, draft=True, key=None):
    result = await browser.post('/api/v1/auth/save-intents', json=body(ctx, draft=draft),
        headers={**headers(browser), 'Idempotency-Key': key or str(uuid4())})
    assert result.status_code == 201, result.text
    return result.json()


async def save_login(browser):
    state = await start(browser, 'save')
    result = await browser.get('/api/v1/auth/kakao/callback', params={'state': state, 'code': 'fixture-code'})
    assert result.headers['location'].endswith('purpose=save&status=success')


async def grant(browser):
    response = await browser.post('/api/v1/consents', json={'purpose': 'storage', 'notice_version': STORAGE_VERSION}, headers=headers(browser))
    assert response.status_code == 201, response.text


def test_issue_idempotency_replacement_csrf_owner_and_server_only_snapshot(tmp_path):
    async def scenario(ctx, browser):
        key = str(uuid4()); first = await create(ctx, browser, key=key)
        redis_key = ctx['intents'].store.key(ctx['issued'].session.digest)
        ttl = await ctx['redis'].pttl(redis_key)
        assert 0 < ttl <= 600000 and (await create(ctx, browser, key=key)) == first
        assert await ctx['redis'].pttl(redis_key) <= ttl
        raw = json.loads(await ctx['redis'].hget(redis_key, 'payload'))
        assert set(raw) == {'profile', 'draft', 'confirmed_ms'} and '가상 도서관 경험' in raw['profile']
        assert set(first) == {'save_intent_id', 'expires_at', 'targets'} and first['targets'] == {'profile': True, 'draft': True}
        invalid_headers = {**headers(browser), 'Idempotency-Key': str(uuid4())}
        assert (await browser.post('/api/v1/auth/save-intents', json=body(ctx))).status_code == 403
        for changes in [{'owner_id': str(uuid4())}, {'profile': {'version': True}}, {'draft': {'draft_id': str(uuid4()), 'revision': 1}, 'extra': '본문'}]:
            assert (await browser.post('/api/v1/auth/save-intents', json={**body(ctx), **changes}, headers=invalid_headers)).status_code == 422
        for profile, reason in [(None, 'required_with')]:
            result = await browser.post('/api/v1/auth/save-intents', json={**body(ctx), 'profile': profile}, headers=invalid_headers)
            assert result.status_code == 422 and result.json()['fields'] == [{'path': 'profile', 'reason': reason}]
        changed = await browser.post('/api/v1/auth/save-intents', json=body(ctx, draft=False), headers={**headers(browser), 'Idempotency-Key': key})
        assert changed.status_code == 409 and changed.json()['code'] == 'IDEMPOTENCY_KEY_REUSED'
        second = await create(ctx, browser, draft=False)
        assert second['save_intent_id'] != first['save_intent_id']
        replay = await browser.post('/api/v1/auth/save-intents', json=body(ctx), headers={**headers(browser), 'Idempotency-Key': key})
        assert replay.status_code == 409 and replay.json()['code'] == 'REQUEST_ALREADY_COMPLETED'
        other = await ctx['sessions'].issue()
        browser.cookies.set('__Host-rc_session', other.token, domain='testserver.local', path='/');await browser.get('/api/v1/me')
        assert (await browser.post('/api/v1/auth/save-intents', json=body(ctx), headers={**headers(browser), 'Idempotency-Key': str(uuid4())})).status_code == 404
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_actual_oauth_transfer_requires_consent_and_consumes_once_in_sql_transaction(tmp_path, backend):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser)
        old = ctx['issued'].session
        resource = ctx['requests'].resource_key(old.subject_id, ctx['journey'].journey_id)
        record = await ctx['journeys'].load(old, ctx['journey'].journey_id)
        requests = RequestService(ctx['requests'])
        permit = await requests.begin(RequestScope(old.subject_id, 'messages', ctx['journey'].journey_id), str(uuid4()), {}, base_revision=3)
        await save_login(browser)
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        assert session.user_id is not None and session.subject_id != old.subject_id
        assert await ctx['sessions'].resolve(ctx['issued'].token) is None
        assert not await ctx['redis'].exists(resource, resource + ':lifecycle', ctx['intents'].store.key(old.digest))
        with pytest.raises(AppError) as late:
            await requests.complete(permit, ResultReference('message', uuid4(), 4), guard=record.guard)
        assert late.value.code == 'NOT_FOUND'
        me = (await browser.get('/api/v1/me')).json()
        assert me['consents'] == [] and me['pending_save_intent']['existing_saved_profile_version'] is None
        assert me['pending_save_intent']['save_intent_id'] == intent['save_intent_id']
        assert me['pending_save_intent']['expires_at'] == intent['expires_at']
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
        writes = []
        async def write(db, account, transfer):
            assert transfer.draft.approved_at is not None and transfer.draft.revision == ctx['draft'].revision
            assert transfer.profile.experiences[0].description == '가상 도서관 경험'
            db.add(ProfileDocument(id=uuid4(), owner_id=account.id));writes.append(account.id)
            return 'delivered'
        async def consume():
            return await ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
                base_saved_version=None, write=write)
        with pytest.raises(AppError) as error:
            await consume()
        assert error.value.code == 'CONSENT_REQUIRED' and writes == []
        await grant(browser)
        assert (await browser.get('/api/v1/me')).json()['consents'][0]['purpose'] == 'storage'
        outcomes = await asyncio.gather(*(consume() for _ in range(6)), return_exceptions=True)
        assert outcomes.count('delivered') == 1 and len(writes) == 1
        assert all(v == 'delivered' or isinstance(v, AppError) and v.code == 'SAVE_INTENT_NOT_FOUND' for v in outcomes)
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileDocument)) == 1
        assert (await browser.get('/api/v1/me')).json()['pending_save_intent'] is None
        assert (await browser.post('/api/v1/auth/save-intents', json=body(ctx), headers={**headers(browser), 'Idempotency-Key': str(uuid4())})).json()['code'] == 'ALREADY_SIGNED_IN'
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('mode', ['cancel', 'expire', 'replace'])
def test_oauth_state_binds_exact_intent_and_cancellation_expiry_never_transfer(tmp_path, mode):
    async def scenario(ctx, browser):
        first = await create(ctx, browser)
        state = await start(browser, 'save')
        expected = None
        if mode == 'expire':
            await ctx['redis'].hset(ctx['intents'].store.key(ctx['issued'].session.digest), 'expires_ms', 1)
        if mode == 'replace':
            expected = (await create(ctx, browser, draft=False))['save_intent_id']
        query = {'state': state, **({'error': 'access_denied'} if mode == 'cancel' else {'code': 'fixture-code'})}
        response = await browser.get('/api/v1/auth/kakao/callback', params=query)
        assert response.headers['location'].endswith('status=cancelled' if mode == 'cancel' else 'status=expired')
        assert await ctx['intents'].reference(ctx['issued'].session) == expected
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
        assert await ctx['sessions'].resolve(ctx['issued'].token) is not None
    run(tmp_path, scenario)


@pytest.mark.parametrize('failure', ['withdraw', 'version', 'writer', 'logout', 'during_write'])
def test_current_consent_replacement_and_failure_cannot_restore_consumed_intent(tmp_path, failure):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        if failure == 'withdraw':
            from app.contracts.time import utc_now
            with ctx['engine'].begin() as db:
                db.execute(update(Consent).values(withdrawn_at=utc_now()))
        if failure == 'logout':
            response = await browser.post('/api/v1/auth/logout', headers=headers(browser));assert response.status_code == 204
        calls = []
        async def writer(db, account, transfer):
            calls.append(transfer)
            db.add(ProfileDocument(id=uuid4(), owner_id=account.id));db.flush()
            if failure == 'during_write':
                await ctx['sessions'].store.revoke(session.digest)
                return 'must not commit'
            raise AppError('SERVICE_UNAVAILABLE')
        with pytest.raises(AppError) as error:
            await ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
                base_saved_version=1 if failure == 'version' else None, write=writer)
        assert error.value.code == {'withdraw': 'CONSENT_REQUIRED', 'version': 'VERSION_CONFLICT', 'writer': 'SERVICE_UNAVAILABLE', 'logout': 'SESSION_EXPIRED', 'during_write': 'SESSION_EXPIRED'}[failure]
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileDocument)) == 0
        if failure in {'writer', 'logout', 'during_write'}:
            assert await ctx['redis'].exists(ctx['intents'].store.key(session.digest)) == 0
        else:
            assert await ctx['redis'].exists(ctx['intents'].store.key(session.digest)) == 1
        assert len(calls) == (1 if failure in {'writer', 'during_write'} else 0)
    run(tmp_path, scenario)


def test_unapproved_stale_and_normal_login_discard_instead_of_implicit_transfer(tmp_path):
    async def scenario(ctx, browser):
        redis_key = ctx['requests'].resource_key(ctx['issued'].session.subject_id, ctx['journey'].journey_id) + ':lifecycle'
        old_raw = await ctx['redis'].hget(redis_key, 'draft:' + str(ctx['draft'].draft_id))
        changed = json.loads(old_raw);changed['approved_at'] = None
        await ctx['redis'].hset(redis_key, 'draft:' + str(ctx['draft'].draft_id), json.dumps(changed))
        failed = await browser.post('/api/v1/auth/save-intents', json=body(ctx), headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert failed.status_code == 409 and failed.json()['code'] == 'DRAFT_NOT_APPROVED'
        await ctx['redis'].hset(redis_key, 'draft:' + str(ctx['draft'].draft_id), old_raw)
        stale = {**body(ctx), 'profile': {'version': 2}}
        failed = await browser.post('/api/v1/auth/save-intents', json=stale, headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert failed.status_code == 409 and failed.json()['code'] == 'VERSION_CONFLICT'
        await create(ctx, browser)
        result = await login(browser);assert result.headers['location'].endswith('purpose=login&status=success')
        assert (await browser.get('/api/v1/me')).json()['pending_save_intent'] is None
        assert not await ctx['redis'].exists(redis_key, ctx['intents'].store.key(ctx['issued'].session.digest))
    run(tmp_path, scenario)


def test_cancelled_writer_rolls_back_and_releases_sql_connection(tmp_path):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        began = asyncio.Event()
        async def writer(db, account, approved):
            db.add(ProfileDocument(id=uuid4(), owner_id=account.id));db.flush();began.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
            base_saved_version=None, write=writer))
        await asyncio.wait_for(began.wait(), 5);task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileDocument)) == 0
        assert await ctx['redis'].exists(ctx['intents'].store.key(session.digest)) == 0
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_existing_saved_version_requires_explicit_matching_replacement(tmp_path, backend):
    async def scenario(ctx, browser):
        from app.contracts.time import utc_now
        intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        with sessionmaker(ctx['engine']).begin() as db:
            profile = ProfileDocument(id=uuid4(), owner_id=session.user_id);db.add(profile);db.flush()
            # 암호화 저장본이 이미 존재하는 DB 상태를 위한 가상 envelope. 암호화의 증거가 아니다.
            db.add(ProfileVersion(profile_id=profile.id, owner_id=session.user_id, version=3,
                ciphertext=b'fictional-encrypted-envelope', nonce=b'fixture00001', key_id='fixture-key-id',
                algorithm='AES-256-GCM', schema_version=1, confirmed_at=utc_now(), saved_at=utc_now()))
        assert (await browser.get('/api/v1/me')).json()['pending_save_intent']['existing_saved_profile_version'] == 3
        received = []
        async def writer(db, account, transfer):
            received.append(transfer);return 'explicit replacement authorized'
        with pytest.raises(AppError) as error:
            await ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
                base_saved_version=None, write=writer)
        assert error.value.code == 'VERSION_CONFLICT' and received == []
        assert await ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
            base_saved_version=3, write=writer) == 'explicit replacement authorized'
        assert len(received) == 1
    run(tmp_path, scenario, backend)


def test_unknown_operational_notice_cannot_grant_or_consume(tmp_path):
    async def scenario(ctx, browser):
        from types import MappingProxyType
        intent = await create(ctx, browser, draft=False);await save_login(browser)
        ctx['consents'].versions = MappingProxyType({'ai_processing': None, 'storage': None})
        denied = await browser.post('/api/v1/consents', json={'purpose': 'storage', 'notice_version': STORAGE_VERSION}, headers=headers(browser))
        assert denied.status_code == 503
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        async def never_write(*args):
            raise AssertionError('미정인 동의로 저장할 수 없음')
        with pytest.raises(AppError) as error:
            await ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
                base_saved_version=None, write=never_write)
        assert error.value.code == 'CONSENT_REQUIRED'
        assert (await browser.get('/api/v1/me')).json()['consents'] == []
    run(tmp_path, scenario)


def test_postgresql_logout_waits_for_prior_writer_before_reporting_success(tmp_path):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        old_token = browser.cookies.get('__Host-rc_session');session = await ctx['sessions'].resolve(old_token)
        began, release = asyncio.Event(), asyncio.Event()
        async def writer(db, account, approved):
            db.add(ProfileDocument(id=uuid4(), owner_id=account.id));db.flush();began.set()
            await release.wait();return 'must roll back'
        saving = asyncio.create_task(ctx['intents'].consume(session, intent['save_intent_id'], storage_notice_version=STORAGE_VERSION,
            base_saved_version=None, write=writer))
        await asyncio.wait_for(began.wait(), 5)
        logout = asyncio.create_task(browser.post('/api/v1/auth/logout', headers=headers(browser)))
        try:
            async with asyncio.timeout(.8):
                while await ctx['sessions'].resolve(old_token) is not None:
                    await asyncio.sleep(.01)
            assert not logout.done()
        finally:
            release.set()
        with pytest.raises(AppError) as error:
            await saving
        assert error.value.code == 'SESSION_EXPIRED'
        assert (await logout).status_code == 204
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileDocument)) == 0
    run(tmp_path, scenario, 'postgresql')
