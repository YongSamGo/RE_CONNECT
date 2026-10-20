"""실제 암호화·SQL·Redis·HTTP 저장: 인가 SEC-02, 세션/동의/TOCTOU TIM-01."""

import asyncio
import json
from threading import Event
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.contracts.saved_profiles import ProfileSaveRequest
from app.core.business_errors import AppError
from app.core.encryption import ContentCipher
from app.modules.auth.service import Identity
from app.modules.saved_profiles.repository import SqlProfileRepository
from app.modules.saved_profiles.service import SavedProfileService
from app.persistence import ApplicationDraft, Consent, ProfileDocument, ProfileVersion, ProfileWriteReceipt, User
from tests.test_consents import AI_VERSION
from tests.test_encryption import ring
from tests.test_member_auth import headers, login
from tests.test_profile_confirmation import ready_edit
from tests.test_save_intents import create, grant, run, save_login


def configured(ctx):
    repository = SqlProfileRepository(ContentCipher(ring()))
    ctx['journeys'].consents = ctx['consents']
    service = SavedProfileService(repository, ctx['members'], ctx['consents'], ctx['intents'], ctx['journeys'])
    ctx['app'].state.saved_profile_service = service
    return repository


def request_body(identity, base=None):
    return {'source': {'type': 'save_intent', 'save_intent_id': identity}, 'base_saved_version': base}


async def post(browser, body, key=None):
    return await browser.post('/api/v1/profiles/me/versions', json=body,
        headers={**headers(browser), 'Idempotency-Key': key or str(uuid4())})


@pytest.mark.parametrize('changes', [{'owner_id': str(uuid4())}, {'content': {'description': '주입 본문'}},
    {'base_saved_version': True}, {'source': {'type': 'journey', 'journey_id': '../other', 'version': 1}},
    {'source': {'type': 'save_intent', 'save_intent_id': str(uuid4()), 'approved_at': '2026-01-01'}}])
def test_profile_save_accepts_only_strict_server_references(changes):
    with pytest.raises(ValidationError):
        ProfileSaveRequest.model_validate({**request_body(str(uuid4())), **changes})


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_http_encrypted_save_replays_consumed_intent_and_rejects_other_owner(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx)
        assert (await browser.get('/api/v1/profiles/me')).status_code == 401
        intent = await create(ctx, browser, draft=False);await save_login(browser)
        assert (await browser.get('/api/v1/profiles/me')).json() == {'saved': None}
        body = request_body(intent['save_intent_id']);key = str(uuid4())
        assert (await post(browser, body, key)).json()['code'] == 'CONSENT_REQUIRED'
        await grant(browser)
        assert (await browser.post('/api/v1/profiles/me/versions', json=body)).status_code == 403
        first = await post(browser, body, key)
        assert first.status_code == 201 and first.json()['created'] and first.json()['version'] == 1
        assert (await post(browser, body, key)).json() == first.json()
        saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
        assert saved['content']['experiences'][0]['description'] == '가상 도서관 경험'
        assert saved['confirmed_at'] <= saved['saved_at'] and saved['version'] == 1
        with sessionmaker(ctx['engine'])() as db:
            row = db.scalars(select(ProfileVersion)).one()
            assert '가상 도서관 경험'.encode() not in row.ciphertext and len(row.nonce) == 12 and row.algorithm == 'AES-256-GCM'
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            assert db.scalar(select(func.count()).select_from(ProfileWriteReceipt)) == 1
            assert set(ProfileWriteReceipt.__table__.columns.keys()) == {'owner_id', 'key_id', 'input_hash', 'intent_hash', 'profile_id', 'version', 'saved_at', 'created', 'replaced_version', 'recorded_at', 'expires_at'}
        assert (await post(browser, request_body(intent['save_intent_id'], 1), key)).json()['code'] == 'IDEMPOTENCY_KEY_REUSED'
        from app.contracts.time import utc_now
        with ctx['engine'].begin() as db:db.execute(update(Consent).values(withdrawn_at=utc_now()))
        assert (await post(browser, body, key)).json()['code'] == 'CONSENT_REQUIRED'
        await browser.post('/api/v1/auth/logout', headers=headers(browser))
        anonymous = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        other = await ctx['members'].complete(anonymous, Identity('999888'), 'login')
        browser.cookies.set('__Host-rc_session', other.issued.token, domain='testserver.local', path='/')
        await browser.get('/api/v1/me')
        assert (await browser.get('/api/v1/profiles/me', headers={'X-User-ID': saved['profile_id']})).json() == {'saved': None}
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_member_http_journey_confirmation_dedup_and_immutable_replacement(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx);await login(browser);await grant(browser)
        granted = await browser.post('/api/v1/consents', json={'purpose': 'ai_processing', 'notice_version': AI_VERSION}, headers=headers(browser))
        assert granted.status_code == 201
        result = await browser.post('/api/v1/journeys', json={'saved_profile': None, 'ai_notice_version': AI_VERSION},
            headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert result.status_code == 201, result.text
        journey_id = result.json()['journey_id'];path = f'/api/v1/journeys/{journey_id}/profile'
        assert (await browser.patch(path, json=ready_edit().model_dump(mode='json'), headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/confirm', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        body = {'source': {'type': 'journey', 'journey_id': journey_id, 'version': 1}, 'base_saved_version': None}
        key = str(uuid4());first = await post(browser, body, key)
        assert first.status_code == 201, first.text
        assert (await browser.post(path + '/confirm', json={'base_revision': 3}, headers=headers(browser))).status_code == 200
        same = await post(browser, {'source': {**body['source'], 'version': 2}, 'base_saved_version': 1})
        assert same.status_code == 200 and same.json()['created'] is False and same.json()['version'] == 1
        view = (await browser.get(path)).json()
        view['draft']['experiences'][0]['description'] = '두 번째로 확인한 가상 경험'
        assert (await browser.patch(path, json={'draft': view['draft'], 'base_revision': 4}, headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/confirm', json={'base_revision': 5}, headers=headers(browser))).status_code == 200
        changed = {'source': {**body['source'], 'version': 3}, 'base_saved_version': None}
        assert (await post(browser, changed)).json()['code'] == 'VERSION_CONFLICT'
        second = await post(browser, {**changed, 'base_saved_version': 1})
        assert second.status_code == 201 and second.json()['version'] == 2 and second.json()['replaced_version'] == 1
        assert (await post(browser, body, key)).json() == first.json()  # source/base는 이제 과거여도 같은 응답
        saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
        assert saved['content']['experiences'][0]['description'] == '두 번째로 확인한 가상 경험'
        with sessionmaker(ctx['engine'])() as db:
            rows = db.scalars(select(ProfileVersion).order_by(ProfileVersion.version)).all()
            assert len(rows) == 2 and rows[0].ciphertext != rows[1].ciphertext and rows[0].nonce != rows[1].nonce
            for table in (ProfileVersion, ProfileWriteReceipt):
                with pytest.raises(IntegrityError), db.begin_nested():
                    db.execute(update(table).values(saved_at=rows[0].saved_at))
        assert (await browser.delete(f'/api/v1/journeys/{journey_id}', headers=headers(browser))).status_code == 204
        assert (await post(browser, {**changed, 'base_saved_version': 2})).status_code == 404
        # 새 세션에서도 실제 회원 AI 동의는 SQL에서 다시 검사한 뒤 Redis guard에 결합한다.
        assert (await browser.post('/api/v1/auth/logout', headers=headers(browser))).status_code == 204
        await login(browser)
        again = await browser.post('/api/v1/journeys', json={'saved_profile': None, 'ai_notice_version': AI_VERSION},
            headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert again.status_code == 201
        from app.modules.admission.llm import ControlledLLMAdapter
        from app.modules.admission.service import InferenceIdentity
        from app.modules.journeys.messages import JourneyMessageService
        from app.modules.requests.service import RequestService
        from tests.test_journey_messages import Runtime, TEXT
        runtime = Runtime();admission = ctx['app'].state.admission_service
        ctx['app'].state.journey_message_service = JourneyMessageService(ctx['journeys'], RequestService(ctx['requests']), ControlledLLMAdapter(runtime, admission))
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        budget = 'limit:' + admission.generation_budget(InferenceIdentity(session.subject_id, '192.0.2.1', session.user_id))
        before = int(await ctx['redis'].hget(admission.store.control_key, budget))
        message = await browser.post(f"/api/v1/journeys/{again.json()['journey_id']}/messages",
            json={'text': TEXT, 'transcription_id': None, 'base_revision': 1},
            headers={**headers(browser), 'Idempotency-Key': str(uuid4()), 'X-Account-ID': str(uuid4())})
        assert message.status_code == 200 and runtime.calls == 2
        assert int(await ctx['redis'].hget(admission.store.control_key, budget)) == before + 2
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('mode', ['key', 'bundle', 'sql_failure', 'withdraw', 'tamper'])
def test_missing_key_bundle_consent_failure_and_tampered_envelope_fail_closed(tmp_path, mode):
    async def scenario(ctx, browser):
        repo = configured(ctx);intent = await create(ctx, browser, draft=mode == 'bundle');await save_login(browser);await grant(browser)
        original = repo.write
        if mode == 'key':repo.cipher = None
        if mode == 'withdraw':
            from app.contracts.time import utc_now
            with ctx['engine'].begin() as db:db.execute(update(Consent).values(withdrawn_at=utc_now()))
        if mode == 'sql_failure':
            def fail(*args):
                original(*args);raise AppError('SERVICE_UNAVAILABLE')
            repo.write = fail
        response = await post(browser, request_body(intent['save_intent_id']))
        if mode == 'bundle':
            assert response.status_code == 201
            session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
            pending = await ctx['intents'].pending(session, await ctx['members'].require(session))
            assert str(pending.save_intent_id) == intent['save_intent_id'] and pending.targets.draft
            assert pending.expires_at.isoformat().replace('+00:00', 'Z') == intent['expires_at']
            with ctx['engine'].connect() as db:
                assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
                assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 0
            reused = await post(browser, request_body(intent['save_intent_id'], 1))
            assert reused.status_code == 409 and reused.json()['code'] == 'REQUEST_ALREADY_COMPLETED'
        elif mode == 'tamper':
            assert response.status_code == 201
            with sessionmaker(ctx['engine']).begin() as db:
                row = db.scalars(select(ProfileVersion)).one()
                # 실제 envelope를 다른 버전으로 옮기면 AAD 검증을 통과할 수 없다.
                db.add(ProfileVersion(profile_id=row.profile_id, owner_id=row.owner_id, version=2, confirmed_at=row.confirmed_at,
                    saved_at=row.saved_at, ciphertext=row.ciphertext, nonce=b'changed00001', key_id=row.key_id, algorithm=row.algorithm, schema_version=1))
            denied = await browser.get('/api/v1/profiles/me')
            assert denied.status_code == 503 and '가상 도서관 경험' not in denied.text
        else:
            assert response.status_code == {'key': 503, 'bundle': 409, 'sql_failure': 503, 'withdraw': 403}[mode]
            with ctx['engine'].connect() as db:
                assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
                assert db.scalar(select(func.count()).select_from(ProfileWriteReceipt)) == 0
            session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
            assert bool(await ctx['redis'].exists(ctx['intents'].store.key(session.digest))) == (mode != 'sql_failure')
    run(tmp_path, scenario)


def test_postgresql_concurrent_retransmission_inserts_one_version_and_receipt(tmp_path):
    async def scenario(ctx, browser):
        configured(ctx);intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        key = str(uuid4());body = request_body(intent['save_intent_id'])
        replies = await asyncio.gather(*(post(browser, body, key) for _ in range(6)))
        assert all(reply.status_code == 201 and reply.json() == replies[0].json() for reply in replies)
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            assert db.scalar(select(func.count()).select_from(ProfileWriteReceipt)) == 1
        # 삭제된 결과는 완료 기록이 남아 있는 동안 같은 요청으로 되살리지 않는다.
        with ctx['engine'].begin() as db:db.execute(delete(ProfileDocument))
        assert (await post(browser, body, key)).status_code == 404
        with ctx['engine'].connect() as db:assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
    run(tmp_path, scenario, 'postgresql')


def test_postgresql_logout_during_real_encrypted_writer_rolls_back_receipt_and_body(tmp_path):
    async def scenario(ctx, browser):
        repo = configured(ctx);intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        old = browser.cookies.get('__Host-rc_session');began, release = Event(), Event();original = repo.write
        def delayed(*args):
            result = original(*args);began.set()
            if not release.wait(5):raise AppError('SERVICE_UNAVAILABLE')
            return result
        repo.write = delayed
        saving = asyncio.create_task(post(browser, request_body(intent['save_intent_id'])))
        assert await asyncio.to_thread(began.wait, 5)
        leaving = asyncio.create_task(browser.post('/api/v1/auth/logout', headers=headers(browser)))
        try:
            async with asyncio.timeout(.8):
                while await ctx['sessions'].resolve(old) is not None:await asyncio.sleep(.01)
            assert not leaving.done()
        finally:release.set()
        assert (await saving).status_code == 401
        assert (await leaving).status_code == 204
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
            assert db.scalar(select(func.count()).select_from(ProfileWriteReceipt)) == 0
    run(tmp_path, scenario, 'postgresql')


def test_cancelled_http_writer_finishes_worker_then_rolls_back_body_and_receipt(tmp_path):
    async def scenario(ctx, browser):
        repo = configured(ctx);intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
        began, release = Event(), Event();original = repo.write
        def delayed(*args):
            result = original(*args);began.set()
            if not release.wait(5):raise AppError('SERVICE_UNAVAILABLE')
            return result
        repo.write = delayed
        task = asyncio.create_task(post(browser, request_body(intent['save_intent_id'])))
        assert await asyncio.to_thread(began.wait, 5)
        task.cancel();await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
            assert db.scalar(select(func.count()).select_from(ProfileWriteReceipt)) == 0
    run(tmp_path, scenario)
