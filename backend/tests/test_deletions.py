"""실제 SQL·Redis·외부 파일 이력의 소유권·전 버전 삭제·재시도/복구."""

from datetime import timedelta
import os
import asyncio
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import sessionmaker

from app.core.business_errors import AppError
from app.modules.auth.member_cleanup import RedisMemberCleanup
from app.modules.auth.service import Identity
from app.adapters.auth import OAuthFailure
from app.modules.deletions.journal import FileDeletionJournal, UnavailableDeletionJournal
from app.modules.deletions.repository import SqlDeletionRepository
from app.modules.deletions.service import DeletionService
from app.persistence import ApplicationDocument, ApplicationDraft, Consent, DeletionRecord, ProfileDocument, ProfileVersion, User
from tests.test_member_auth import headers, login, start as oauth_start
from tests.test_save_intents import run
from tests.test_saved_material_editing import editing
from tests.test_saved_journey_import import start


def configured(ctx, tmp_path):
    if os.name != 'posix': pytest.skip('실제 별도 파일 저널의 POSIX 권한은 Linux 통합에서 검증')
    directory = tmp_path / 'deletion-journal'; directory.mkdir(mode=0o700)
    ctx['journeys'].consents = ctx['consents']
    service = DeletionService(SqlDeletionRepository(sessionmaker(ctx['engine']).begin), FileDeletionJournal(directory),
        ctx['members'], ctx['intents'].policy, RedisMemberCleanup(ctx['members'].store))
    ctx['app'].state.deletion_service = service
    return service, directory


def count(ctx, model):
    with ctx['engine'].connect() as db: return db.scalar(select(func.count()).select_from(model))


async def another_session(ctx, browser):
    session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
    with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == session.user_id))
    anonymous = await ctx['sessions'].issue()
    result = await ctx['members'].complete(anonymous.session, Identity(subject), 'login')
    return result.issued


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_profile_deletion_removes_all_versions_and_applications_and_every_old_session(tmp_path, backend):
    async def scenario(ctx, browser):
        service, directory = configured(ctx, tmp_path)
        _, document, _, journey, request = await editing(ctx, browser)
        copied = await browser.post(f"/api/v1/journeys/{journey['journey_id']}/drafts", json=request,
            headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{copied.json()['draft_id']}"
        assert (await browser.patch(path, json={'base_revision': 1, 'self_introduction': '가상 두 번째 저장', 'motivation': '가상 직접 작성'}, headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/approve', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        assert (await browser.post('/api/v1/drafts', json={'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'draft_id': copied.json()['draft_id'], 'revision': 3},
            'document_id': document['document_id'], 'base_document_version': 1}, headers={**headers(browser), 'Idempotency-Key': str(uuid4())})).status_code == 201
        assert count(ctx, ApplicationDraft) == 2
        profile_path = f"/api/v1/journeys/{journey['journey_id']}/profile"
        view = (await browser.get(profile_path)).json()
        view['draft']['experiences'][0]['description'] = '두 번째로 재확정한 가상 경험'
        assert (await browser.patch(profile_path, json={'base_revision': view['revision'], 'draft': view['draft']}, headers=headers(browser))).status_code == 200
        assert (await browser.post(profile_path + '/confirm', json={'base_revision': view['revision'] + 1}, headers=headers(browser))).status_code == 200
        assert (await browser.post('/api/v1/profiles/me/versions', json={'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'version': 2},
            'base_saved_version': 1}, headers={**headers(browser), 'Idempotency-Key': str(uuid4())})).status_code == 201
        assert count(ctx, ProfileVersion) == 2
        old = browser.cookies.get('__Host-rc_session'); another = await another_session(ctx, browser)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app']), base_url='https://testserver') as second:
            second.cookies.set('__Host-rc_session', another.token, domain='testserver.local', path='/'); await second.get('/api/v1/me')
            saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
            assert (await start(second, saved)).status_code == 201
            result = await browser.delete('/api/v1/profiles/me', headers=headers(browser))
            assert result.status_code == 204, result.text
            assert browser.cookies.get('__Host-rc_session') != old and await ctx['sessions'].resolve(old) is None
            assert await ctx['sessions'].resolve(another.token) is None
            assert (await second.get('/api/v1/me')).json()['authenticated'] is False
        assert (await browser.get('/api/v1/me')).json()['authenticated'] is True
        assert (await browser.get('/api/v1/profiles/me')).json()['saved'] is None
        assert (await browser.get('/api/v1/drafts')).json()['total'] == 0
        assert (await browser.get(path)).status_code == 404
        assert count(ctx, ProfileDocument) == count(ctx, ProfileVersion) == count(ctx, ApplicationDocument) == count(ctx, ApplicationDraft) == 0
        with ctx['engine'].connect() as db:
            row = db.execute(select(DeletionRecord.__table__)).mappings().one()
            assert row['status'] == 'completed' and row['expires_at'] - row['deleted_at'] == timedelta(days=30)
        raw = next(directory.glob('*.json')).read_text()
        assert all(value not in raw for value in ('가상', 'ciphertext', 'kakao_subject', 'self_introduction', 'motivation'))
        assert await service.retry() == 0
        assert (await browser.delete('/api/v1/profiles/me', headers=headers(browser))).status_code == 204
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
@pytest.mark.parametrize('purpose', ['storage', 'ai_processing'])
def test_withdrawal_deletes_only_the_purpose_data_and_invalidates_temporary_work(tmp_path, backend, purpose):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        old = browser.cookies.get('__Host-rc_session')
        response = await browser.post('/api/v1/consents/withdraw', json={'purpose': purpose}, headers=headers(browser))
        assert response.status_code == 200, response.text
        assert response.json()['purpose'] == purpose and response.json()['deleted']['journeys'] >= 1
        assert await ctx['sessions'].resolve(old) is None
        assert (await browser.get(f"/api/v1/journeys/{journey['journey_id']}/profile")).status_code == 404
        me = (await browser.get('/api/v1/me')).json(); assert me['authenticated']
        assert purpose not in {consent['purpose'] for consent in me['consents']}
        assert count(ctx, ProfileVersion) == (0 if purpose == 'storage' else 1)
        assert count(ctx, ApplicationDraft) == (0 if purpose == 'storage' else 1)
        again = await browser.post('/api/v1/consents/withdraw', json={'purpose': purpose}, headers=headers(browser))
        assert again.status_code == 200 and again.json()['deleted'] == {'journeys': 0, 'profile_versions': 0, 'documents': 0}
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_delete_account_requires_current_provider_reauth_and_keeps_only_minimum_history(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); await editing(ctx, browser)
        assert (await browser.delete('/api/v1/me', headers=headers(browser))).json()['code'] == 'REAUTH_REQUIRED'
        assert count(ctx, DeletionRecord) == 0
        state = await oauth_start(browser, 'reauth')
        result = await browser.get('/api/v1/auth/kakao/callback', params={'state': state, 'code': 'fixture-code'})
        assert result.headers['location'].endswith('purpose=reauth&status=success')
        old_user = (await browser.get('/api/v1/me')).json()['user']['id']
        result = await browser.delete('/api/v1/me', headers=headers(browser)); assert result.status_code == 204, result.text
        assert not (await browser.get('/api/v1/me')).json()['authenticated']
        assert count(ctx, User) == count(ctx, Consent) == count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 0
        assert count(ctx, DeletionRecord) == 1
        assert (await login(browser)).headers['location'].endswith('status=success')
        assert (await browser.get('/api/v1/me')).json()['user']['id'] != old_user
    run(tmp_path, scenario, backend)


def test_missing_journal_is_fail_closed_without_changing_generation_or_saved_data(tmp_path):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        service.journal = UnavailableDeletionJournal()
        response = await browser.delete('/api/v1/profiles/me', headers=headers(browser))
        assert response.status_code == 503 and count(ctx, DeletionRecord) == 0
        assert (await browser.get('/api/v1/profiles/me')).status_code == 200 and count(ctx, ProfileVersion) == 1
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_external_failure_fences_login_and_reads_until_durable_retry_finishes(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        append = service.journal.append
        def unavailable(event): raise AppError('SERVICE_UNAVAILABLE')
        service.journal.append = unavailable
        response = await browser.delete('/api/v1/profiles/me', headers=headers(browser))
        assert response.status_code == 503 and count(ctx, ProfileVersion) == 1
        with ctx['engine'].connect() as db: assert db.scalar(select(DeletionRecord.status)) == 'failed'
        assert (await browser.get('/api/v1/profiles/me')).status_code == 401
        await browser.get('/api/v1/me')
        assert (await login(browser)).headers['location'].endswith('status=failed')
        service.journal.append = append
        assert await service.retry() == 1 and count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 0
        assert (await login(browser)).headers['location'].endswith('status=success')
        assert (await browser.get('/api/v1/profiles/me')).json()['saved'] is None
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_independent_journal_reapplies_deleted_target_after_database_snapshot_restore(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        tables = [ProfileDocument, ProfileVersion, ApplicationDocument, ApplicationDraft]
        with ctx['engine'].connect() as db:
            snapshots = [(model, [dict(row) for row in db.execute(select(model.__table__)).mappings()]) for model in tables]
        assert (await browser.delete('/api/v1/profiles/me', headers=headers(browser))).status_code == 204
        # 운영 복원이 아닌, 격리 시험 DB의 삭제 전 암호문 스냅샷 재현이다.
        with ctx['engine'].begin() as db:
            db.execute(delete(DeletionRecord)); db.execute(update(User).values(session_generation=0))
            for model, rows in snapshots: db.execute(insert(model), rows)
        assert count(ctx, ProfileVersion) == 1 and count(ctx, DeletionRecord) == 0
        assert await service.recover() == 1
        assert count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 0
        with ctx['engine'].connect() as db: assert db.scalar(select(DeletionRecord.status)) == 'completed'
        await browser.get('/api/v1/me')
        assert (await login(browser)).headers['location'].endswith('status=success')
        from tests.test_consents import AI_VERSION
        from tests.test_profile_confirmation import ready_edit
        created = await browser.post('/api/v1/journeys', json={'ai_notice_version': AI_VERSION, 'saved_profile': None},
            headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert created.status_code == 201
        journey_id = created.json()['journey_id']; path = f'/api/v1/journeys/{journey_id}/profile'
        assert (await browser.patch(path, json=ready_edit().model_dump(mode='json'), headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/confirm', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        assert (await browser.post('/api/v1/profiles/me/versions', json={'source': {'type': 'journey', 'journey_id': journey_id, 'version': 1},
            'base_saved_version': None}, headers={**headers(browser), 'Idempotency-Key': str(uuid4())})).status_code == 201
        with ctx['engine'].connect() as db:
            new_profile = db.scalar(select(ProfileDocument.id))
            assert new_profile != snapshots[0][1][0]['id']
        assert await service.recover() == 1
        with ctx['engine'].connect() as db: assert db.scalar(select(ProfileDocument.id)) == new_profile
        assert count(ctx, ProfileVersion) == 1
    run(tmp_path, scenario, backend)


def test_anonymous_ai_withdrawal_clears_current_journey_without_persistent_member_history(tmp_path):
    async def scenario(ctx, browser):
        old = browser.cookies.get('__Host-rc_session')
        result = await browser.post('/api/v1/consents/withdraw', json={'purpose': 'ai_processing'}, headers=headers(browser))
        assert result.status_code == 200 and result.json()['deleted'] == {'journeys': 1, 'profile_versions': 0, 'documents': 0}
        assert await ctx['sessions'].resolve(old) is None and count(ctx, DeletionRecord) == 0
        assert (await browser.get('/api/v1/me')).json()['consents'] == []
        assert (await browser.post('/api/v1/consents/withdraw', json={'purpose': 'storage'}, headers=headers(browser))).status_code == 401
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_other_member_cannot_delete_document_and_delete_rejects_owner_body_or_missing_csrf(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); _, document, _, _, _ = await editing(ctx, browser)
        assert (await browser.delete('/api/v1/profiles/me')).status_code == 403
        assert (await browser.request('DELETE', '/api/v1/profiles/me', json={'owner_id': str(uuid4())}, headers=headers(browser))).status_code == 422
        assert (await browser.delete('/api/v1/profiles/me?owner_id=' + str(uuid4()), headers=headers(browser))).status_code == 422
        assert count(ctx, DeletionRecord) == 0
        anonymous = await ctx['sessions'].issue()
        other = await ctx['members'].complete(anonymous.session, Identity('665522'), 'login')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app']), base_url='https://testserver') as second:
            second.cookies.set('__Host-rc_session', other.issued.token, domain='testserver.local', path='/'); await second.get('/api/v1/me')
            assert (await second.delete('/api/v1/drafts/' + document['document_id'], headers=headers(second))).status_code == 404
            assert count(ctx, DeletionRecord) == 0
        assert (await browser.get('/api/v1/drafts/' + document['document_id'])).status_code == 200
        assert (await browser.delete('/api/v1/drafts/' + document['document_id'], headers=headers(browser))).status_code == 204
        assert count(ctx, ApplicationDraft) == count(ctx, ApplicationDocument) == 0 and count(ctx, ProfileVersion) == 1
        assert (await browser.delete('/api/v1/drafts/' + document['document_id'], headers=headers(browser))).status_code == 404
    run(tmp_path, scenario, backend)


def test_postgresql_pending_deletion_blocks_late_sql_save_and_cleans_all_old_sources(tmp_path):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        path = f"/api/v1/journeys/{journey['journey_id']}/profile"
        profile = (await browser.get(path)).json()['draft']; profile['experiences'][0]['description'] = '늦은 저장 시험용 가상 경험'
        assert (await browser.patch(path, json={'base_revision': 1, 'draft': profile}, headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/confirm', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        began, release = Event(), Event(); prepare = service.repository.prepare
        def paused(*args):
            result = prepare(*args); began.set()
            if not release.wait(5): raise RuntimeError('시험 잠금 대기 만료')
            return result
        service.repository.prepare = paused
        deleting = asyncio.create_task(browser.delete('/api/v1/profiles/me', headers=headers(browser)))
        assert await asyncio.to_thread(began.wait, 5)
        saving = asyncio.create_task(browser.post('/api/v1/profiles/me/versions', json={'source': {'type': 'journey',
            'journey_id': journey['journey_id'], 'version': 2}, 'base_saved_version': 1}, headers={**headers(browser), 'Idempotency-Key': str(uuid4())}))
        try:
            await asyncio.sleep(.05); assert not saving.done()
        finally: release.set()
        assert (await deleting).status_code == 204
        assert (await saving).status_code in {401, 404}
        assert count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 0
    run(tmp_path, scenario, 'postgresql')


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_never_granted_storage_withdraw_is_a_noop_and_keeps_active_ai_work(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); service.journal = UnavailableDeletionJournal()
        assert (await login(browser)).headers['location'].endswith('status=success')
        from tests.test_saved_journey_import import accept_ai
        from tests.test_consents import AI_VERSION
        await accept_ai(browser)
        result = await browser.post('/api/v1/journeys', json={'ai_notice_version': AI_VERSION, 'saved_profile': None},
            headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert result.status_code == 201
        token = browser.cookies.get('__Host-rc_session')
        response = await browser.post('/api/v1/consents/withdraw', json={'purpose': 'storage'}, headers=headers(browser))
        assert response.status_code == 200 and response.json()['deleted'] == {'journeys': 0, 'profile_versions': 0, 'documents': 0}
        assert browser.cookies.get('__Host-rc_session') == token and count(ctx, DeletionRecord) == 0
        assert (await browser.get(f"/api/v1/journeys/{result.json()['journey_id']}/profile")).status_code == 200
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_withdrawal_blocks_a_previously_authorized_late_consent_grant_but_preserves_new_reacceptance(tmp_path, backend):
    async def scenario(ctx, browser):
        service, _ = configured(ctx, tmp_path); await editing(ctx, browser)
        store = ctx['consents'].store.member
        grant = store._grant; began, release = Event(), Event()
        def delayed(*args):
            began.set()
            if not release.wait(5): raise RuntimeError('시험 동의 대기 만료')
            return grant(*args)
        store._grant = delayed
        from tests.test_consents import AI_VERSION
        late = asyncio.create_task(browser.post('/api/v1/consents', json={'purpose': 'ai_processing', 'notice_version': AI_VERSION}, headers=headers(browser)))
        assert await asyncio.to_thread(began.wait, 5)
        try:
            response = await browser.post('/api/v1/consents/withdraw', json={'purpose': 'ai_processing'}, headers=headers(browser))
            assert response.status_code == 200
        finally: release.set()
        assert (await late).status_code in {401, 404}
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(Consent).where(Consent.purpose == 'ai_processing', Consent.withdrawn_at.is_(None))) == 0
        store._grant = grant
        from tests.test_saved_journey_import import accept_ai
        await accept_ai(browser)
        assert await service.recover() == 1
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(Consent).where(Consent.purpose == 'ai_processing', Consent.withdrawn_at.is_(None))) == 1
        assert count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 1
    run(tmp_path, scenario, backend)


def test_session_limit_allows_replacement_and_cleans_expired_member_work_before_new_login(tmp_path):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); await editing(ctx, browser)
        saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
        current = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        with ctx['engine'].connect() as db: subject = db.scalar(select(User.kakao_subject).where(User.id == current.user_id))
        sessions = [await another_session(ctx, browser) for _ in range(15)]
        index = ctx['members'].store.member_prefix + str(current.user_id) + ':sessions'
        assert await ctx['redis'].scard(index) == 16
        anonymous = await ctx['sessions'].issue()
        with pytest.raises(OAuthFailure): await ctx['members'].complete(anonymous.session, Identity(subject), 'login')
        replacement = await ctx['members'].complete(current, Identity(subject), 'login')
        assert replacement.issued is not None and await ctx['redis'].scard(index) == 16
        expired = sessions[0]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app']), base_url='https://testserver') as second:
            second.cookies.set('__Host-rc_session', expired.token, domain='testserver.local', path='/'); await second.get('/api/v1/me')
            journey = await start(second, saved); assert journey.status_code == 201
            resource = ctx['requests'].resource_key(expired.session.subject_id, UUID(journey.json()['journey_id']))
        await ctx['redis'].pexpire(ctx['sessions'].store.key(expired.session.digest), 1)
        await asyncio.sleep(.01)
        assert await ctx['sessions'].resolve(expired.token) is None
        anonymous = await ctx['sessions'].issue()
        admitted = await ctx['members'].complete(anonymous.session, Identity(subject), 'login')
        assert admitted.issued is not None and await ctx['redis'].scard(index) == 16
        assert await ctx['redis'].exists(resource, resource + ':lifecycle', resource + ':requests') == 0
        assert count(ctx, ProfileVersion) == 1
    run(tmp_path, scenario)
