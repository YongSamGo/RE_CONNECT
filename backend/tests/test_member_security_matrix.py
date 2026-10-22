"""W10-08: 여러 실제 회원 세션의 소유권·낙관적 저장·실패 격리 HTTP 행렬."""

import asyncio
from contextlib import asynccontextmanager
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, update

from app.contracts.drafts import SavedDocumentRef
from app.core.business_errors import AppError
from app.modules.auth.service import Identity
from app.persistence import ApplicationDocument, ApplicationDraft, ApplicationWriteReceipt, DeletionRecord, ProfileVersion, ProfileWriteReceipt, User
from tests.test_consents import AI_VERSION
from tests.test_deletions import another_session, configured, count
from tests.test_member_auth import headers, login, start as oauth_start
from tests.test_profile_confirmation import ready_edit
from tests.test_save_intents import grant, run
from tests.test_saved_journey_import import accept_ai, start
from tests.test_saved_material_editing import copy, editing
from tests.test_saved_profiles import post as profile_save
from tests.test_saved_drafts import post as application_save


async def create_profile(browser):
    created = await browser.post('/api/v1/journeys', json={'ai_notice_version': AI_VERSION, 'saved_profile': None},
        headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
    assert created.status_code == 201, created.text
    journey = created.json(); path = f"/api/v1/journeys/{journey['journey_id']}/profile"
    assert (await browser.patch(path, json=ready_edit().model_dump(mode='json'), headers=headers(browser))).status_code == 200
    assert (await browser.post(path + '/confirm', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
    assert (await profile_save(browser, {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'version': 1}, 'base_saved_version': None})).status_code == 201
    return journey


async def approved_copy(browser, journey, request, introduction):
    response = await copy(browser, journey, request); assert response.status_code == 201, response.text
    draft = response.json(); path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{draft['draft_id']}"
    assert (await browser.patch(path, json={'base_revision': 1, 'self_introduction': introduction, 'motivation': '직접 확인한 가상 동기'}, headers=headers(browser))).status_code == 200
    approved = await browser.post(path + '/approve', json={'base_revision': 2}, headers=headers(browser))
    assert approved.status_code == 200, approved.text
    return {'type': 'journey', 'journey_id': journey['journey_id'], 'draft_id': draft['draft_id'], 'revision': approved.json()['revision']}


@asynccontextmanager
async def other_member(ctx, subject, opportunity, *, operator=False):
    anonymous = await ctx['sessions'].issue()
    completion = await ctx['members'].complete(anonymous.session, Identity(subject), 'login')
    account_id = completion.issued.session.user_id
    if operator:
        with ctx['engine'].begin() as db: db.execute(update(User).where(User.id == account_id).values(role='admin'))
    peer = '192.0.2.3' if operator else '192.0.2.2'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=(peer, 30001)), base_url='https://testserver') as browser:
        browser.cookies.set('__Host-rc_session', completion.issued.token, domain='testserver.local', path='/')
        me = (await browser.get('/api/v1/me')).json()
        assert me['user']['roles'] == (['operator'] if operator else ['user']) and me['consents'] == []
        assert (await browser.get('/api/v1/profiles/me')).json()['saved'] is None
        await accept_ai(browser); await grant(browser)
        journey = await create_profile(browser)
        made = await browser.post(f"/api/v1/journeys/{journey['journey_id']}/drafts", json={'profile_version': 1,
            'opportunity': opportunity, 'mode': 'manual', 'saved_document': None}, headers={**headers(browser), 'Idempotency-Key': str(uuid4())})
        assert made.status_code == 201
        draft = made.json(); path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{draft['draft_id']}"
        assert (await browser.patch(path, json={'base_revision': 1, 'self_introduction': '다른 회원이 직접 작성한 가상 지원서', 'motivation': '다른 회원의 가상 동기'}, headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/approve', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        source = {'type': 'journey', 'journey_id': journey['journey_id'], 'draft_id': draft['draft_id'], 'revision': 3}
        saved = await application_save(browser, {'source': source, 'document_id': None, 'base_document_version': None})
        assert saved.status_code == 201
        yield browser, account_id, journey, source, saved.json()


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_two_members_anonymous_and_operator_cannot_read_edit_save_or_delete_another_owners_data(tmp_path, backend):
    async def scenario(ctx, owner):
        configured(ctx, tmp_path)
        _, document, saved, journey, request = await editing(ctx, owner)
        made = await copy(owner, journey, request); assert made.status_code == 201
        draft_id = made.json()['draft_id']; profile_path = f"/api/v1/journeys/{journey['journey_id']}/profile"
        draft_path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{draft_id}"
        original = (await owner.get(profile_path)).json()
        owner_id = (await owner.get('/api/v1/me')).json()['user']['id']
        assert await ctx['sessions'].resolve(ctx['issued'].token) is None
        assert (await owner.get('/api/v1/me')).json()['pending_save_intent'] is None
        async with other_member(ctx, '8877001', request['opportunity']) as member, other_member(ctx, '8877002', request['opportunity'], operator=True) as operator:
            for outsider, _, own_journey, own_source, own_document in (member, operator):
                spoofed = {**headers(outsider), 'X-Account-ID': owner_id, 'X-User-ID': owner_id, 'X-Role': 'admin'}
                own_profile = (await outsider.get('/api/v1/profiles/me', headers=spoofed)).json()['saved']
                assert own_profile['profile_id'] != (await owner.get('/api/v1/profiles/me')).json()['saved']['profile_id']
                listing = (await outsider.get('/api/v1/drafts', params={'owner_id': owner_id}, headers=spoofed)).json()
                assert [item['document_id'] for item in listing['items']] == [own_document['document_id']]
                actions = [
                    ('GET', '/api/v1/drafts/' + document['document_id'], None),
                    ('DELETE', '/api/v1/drafts/' + document['document_id'], None),
                    ('GET', profile_path, None),
                    ('PATCH', profile_path, {'draft': original['draft'], 'base_revision': original['revision']}),
                    ('POST', profile_path + '/confirm', {'base_revision': original['revision']}),
                    ('GET', draft_path, None),
                    ('PATCH', draft_path, {'base_revision': 1, 'self_introduction': '타인 덮어쓰기 시도', 'motivation': '위조 동기'}),
                    ('POST', draft_path + '/approve', {'base_revision': 1}),
                    ('POST', '/api/v1/profiles/me/versions', {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'version': 1}, 'base_saved_version': 1}),
                    ('POST', '/api/v1/drafts', {'source': own_source, 'document_id': document['document_id'], 'base_document_version': 1}),
                    ('POST', f"/api/v1/journeys/{own_journey['journey_id']}/drafts", request),
                ]
                for method, path, body in actions:
                    response = await outsider.request(method, path, json=body, headers={**spoofed, 'Idempotency-Key': str(uuid4())})
                    assert response.status_code == 404, (method, path, response.text)
                    assert saved['self_introduction'] not in response.text
                missing = await outsider.get('/api/v1/drafts/' + str(uuid4()))
                foreign = await outsider.get('/api/v1/drafts/' + document['document_id'])
                assert missing.json()['code'] == foreign.json()['code'] == 'NOT_FOUND'
                # 체험 삭제는 타인/없음을 구분하지 않는204 계약이며 실제 소유 자료는 유지한다.
                assert (await outsider.delete(f"/api/v1/journeys/{journey['journey_id']}", headers=spoofed)).status_code == 204
                for path in ('/api/v1/profiles/me', '/api/v1/me'):
                    assert (await outsider.request('DELETE', path, json={'owner_id': owner_id}, headers=spoofed)).status_code == 422
                assert (await owner.get(profile_path)).json() == original
                assert (await owner.get(draft_path)).json()['revision'] == 1
                assert (await owner.get('/api/v1/drafts/' + document['document_id'])).json() == saved
            anonymous = await ctx['sessions'].issue()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.4', 30001)), base_url='https://testserver') as guest:
                guest.cookies.set('__Host-rc_session', anonymous.token, domain='testserver.local', path='/'); await guest.get('/api/v1/me')
                for method, path, body in [('GET', '/api/v1/profiles/me', None), ('GET', '/api/v1/drafts', None),
                    ('GET', '/api/v1/drafts/' + document['document_id'], None), ('DELETE', '/api/v1/drafts/' + document['document_id'], None),
                    ('DELETE', '/api/v1/profiles/me', None), ('DELETE', '/api/v1/me', None),
                    ('POST', f"/api/v1/journeys/{journey['journey_id']}/drafts", request)]:
                    response = await guest.request(method, path, json=body, headers={**headers(guest), 'Idempotency-Key': str(uuid4()), 'X-Account-ID': owner_id})
                    assert response.status_code == 401, response.text
                assert (await guest.get(draft_path)).status_code == 404
                assert (await guest.delete(f"/api/v1/journeys/{journey['journey_id']}", headers=headers(guest))).status_code == 204
        assert (await owner.get(profile_path)).json() == original
        assert count(ctx, User) == count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 3
        assert count(ctx, DeletionRecord) == 0
    run(tmp_path, scenario, backend)


async def changed_profile(browser, journey, description):
    path = f"/api/v1/journeys/{journey['journey_id']}/profile"
    view = (await browser.get(path)).json(); view['draft']['experiences'][0]['description'] = description
    assert (await browser.patch(path, json={'draft': view['draft'], 'base_revision': view['revision']}, headers=headers(browser))).status_code == 200
    confirmed = await browser.post(path + '/confirm', json={'base_revision': view['revision'] + 1}, headers=headers(browser))
    assert confirmed.status_code == 200
    return {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'version': confirmed.json()['profile']['version']}, 'base_saved_version': 1}


@pytest.mark.parametrize('same_key', [True, False])
def test_postgresql_simultaneous_profile_saves_have_one_version_and_one_receipt(tmp_path, same_key):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); _, _, _, journey, _ = await editing(ctx, browser)
        first = await changed_profile(browser, journey, '동시에 저장할 첫 번째 가상 경험')
        second, key = first, str(uuid4())
        if not same_key:
            saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
            new_journey = (await start(browser, saved)).json()
            second = await changed_profile(browser, new_journey, '동시에 저장할 두 번째 가상 경험')
        results = await asyncio.gather(profile_save(browser, first, key), profile_save(browser, second, key if same_key else str(uuid4())))
        if same_key: assert all(result.status_code == 201 for result in results) and results[0].json() == results[1].json()
        else: assert sorted(result.status_code for result in results) == [201, 409]
        assert count(ctx, ProfileVersion) == 2 and count(ctx, ProfileWriteReceipt) == 2
        assert (await browser.get('/api/v1/profiles/me')).json()['saved']['version'] == 2
    run(tmp_path, scenario, 'postgresql')


def test_postgresql_simultaneous_document_updates_preserve_original_and_reject_lost_update(tmp_path):
    async def scenario(ctx, browser):
        configured(ctx, tmp_path); _, document, saved, journey, request = await editing(ctx, browser)
        first = await approved_copy(browser, journey, request, '첫 번째로 다시 승인한 가상 지원서')
        second = await approved_copy(browser, journey, request, '두 번째로 다시 승인한 가상 지원서')
        requests = [{'source': source, 'document_id': document['document_id'], 'base_document_version': 1} for source in (first, second)]
        results = await asyncio.gather(*(application_save(browser, value) for value in requests))
        assert sorted(result.status_code for result in results) == [201, 409]
        assert count(ctx, ApplicationDraft) == count(ctx, ApplicationWriteReceipt) == 2
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        original = await ctx['app'].state.saved_draft_service.edit_source(session, SavedDocumentRef(document_id=document['document_id'], version=1))
        assert original.content.self_introduction == saved['self_introduction']
    run(tmp_path, scenario, 'postgresql')


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_failed_deletion_fences_only_the_requesting_member_and_retry_keeps_other_data(tmp_path, backend):
    async def scenario(ctx, owner):
        service, _ = configured(ctx, tmp_path); _, _, _, _, request = await editing(ctx, owner)
        async with other_member(ctx, '8877011', request['opportunity']) as other:
            browser, _, _, _, document = other
            original = (await browser.get('/api/v1/drafts/' + document['document_id'])).json()
            append = service.journal.append
            def failed(event): raise AppError('SERVICE_UNAVAILABLE')
            service.journal.append = failed
            result = await owner.delete('/api/v1/profiles/me', headers=headers(owner))
            assert result.status_code == 503 and count(ctx, ProfileVersion) == 2
            assert (await owner.get('/api/v1/profiles/me')).status_code == 401
            assert (await browser.get('/api/v1/drafts/' + document['document_id'])).json() == original
            service.journal.append = append
            assert await service.retry() == 1
            assert count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 1
            assert (await browser.get('/api/v1/drafts/' + document['document_id'])).json() == original
            await owner.get('/api/v1/me'); assert (await login(owner)).headers['location'].endswith('status=success')
            assert (await owner.get('/api/v1/profiles/me')).json()['saved'] is None
    run(tmp_path, scenario, backend)


def test_postgresql_save_in_one_device_then_delete_in_another_leaves_no_late_document(tmp_path):
    async def scenario(ctx, owner):
        configured(ctx, tmp_path); repository, document, _, _, request = await editing(ctx, owner)
        second = await another_session(ctx, owner)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.5', 30001)), base_url='https://testserver') as browser:
            browser.cookies.set('__Host-rc_session', second.token, domain='testserver.local', path='/'); await browser.get('/api/v1/me')
            saved = (await browser.get('/api/v1/profiles/me')).json()['saved']; journey = (await start(browser, saved)).json()
            source = await approved_copy(browser, journey, request, '다른 기기에서 승인한 가상 지원서')
            began, release = Event(), Event(); write = repository.write
            def paused(*args):
                value = write(*args); began.set()
                if not release.wait(5): raise RuntimeError('시험 저장 대기 만료')
                return value
            repository.write = paused
            saving = asyncio.create_task(application_save(browser, {'source': source, 'document_id': document['document_id'], 'base_document_version': 1}))
            assert await asyncio.to_thread(began.wait, 5)
            deleting = asyncio.create_task(owner.delete('/api/v1/drafts/' + document['document_id'], headers=headers(owner)))
            try:
                await asyncio.sleep(.03); assert not deleting.done()
            finally: release.set()
            assert (await saving).status_code == 201 and (await deleting).status_code == 204
            assert await ctx['sessions'].resolve(second.token) is None
        assert count(ctx, ApplicationDocument) == count(ctx, ApplicationDraft) == 0 and count(ctx, ProfileVersion) == 1
        with ctx['engine'].connect() as db: assert db.scalar(select(DeletionRecord.status)) == 'completed'
    run(tmp_path, scenario, 'postgresql')


def test_account_delete_cookie_failure_does_not_return_success_or_affect_another_member(tmp_path):
    async def scenario(ctx, owner):
        configured(ctx, tmp_path); _, _, _, _, request = await editing(ctx, owner)
        async with other_member(ctx, '8877021', request['opportunity']) as other:
            browser, _, _, _, document = other
            state = await oauth_start(owner, 'reauth')
            assert (await owner.get('/api/v1/auth/kakao/callback', params={'state': state, 'code': 'fixture-code'})).headers['location'].endswith('status=success')
            issue = ctx['sessions'].issue
            async def failed(): raise AppError('SERVICE_UNAVAILABLE')
            ctx['sessions'].issue = failed
            result = await owner.delete('/api/v1/me', headers=headers(owner))
            assert result.status_code == 503 and 'set-cookie' not in result.headers
            ctx['sessions'].issue = issue
            assert not (await owner.get('/api/v1/me')).json()['authenticated']
            assert (await browser.get('/api/v1/drafts/' + document['document_id'])).status_code == 200
            assert count(ctx, User) == count(ctx, ProfileVersion) == count(ctx, ApplicationDraft) == 1
            with ctx['engine'].connect() as db: assert db.scalar(select(DeletionRecord.status)) == 'completed'
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_same_idempotency_key_is_scoped_to_each_authenticated_owner(tmp_path, backend):
    async def scenario(ctx, owner):
        configured(ctx, tmp_path); _, document, _, journey, request = await editing(ctx, owner)
        first = await approved_copy(owner, journey, request, '같은 키를 사용하는 첫 회원의 가상 지원서')
        async with other_member(ctx, '8877031', request['opportunity']) as other:
            browser, _, own_journey, _, own_document = other
            second_request = {**request, 'saved_document': {'document_id': own_document['document_id'], 'version': 1}}
            second = await approved_copy(browser, own_journey, second_request, '같은 키를 사용하는 다른 회원의 가상 지원서')
            key = str(uuid4())
            payloads = [{'source': source, 'document_id': result['document_id'], 'base_document_version': 1}
                for source, result in ((first, document), (second, own_document))]
            results = [await application_save(api, value, key) for api, value in zip((owner, browser), payloads, strict=True)]
            assert all(result.status_code == 201 and result.json()['version'] == 2 for result in results)
            assert results[0].json()['document_id'] != results[1].json()['document_id']
            for api, value, response in zip((owner, browser), payloads, results, strict=True):
                assert (await application_save(api, value, key)).json() == response.json()
            with ctx['engine'].connect() as db:
                assert len(db.execute(select(ApplicationWriteReceipt.owner_id).where(ApplicationWriteReceipt.key_id == UUID(key))).all()) == 2
    run(tmp_path, scenario, backend)
