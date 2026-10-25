"""저장본을 보존하는 임시 재편집·승인·명시 저장의 실제 SQL/Redis 경계."""

from uuid import uuid4
import asyncio
from threading import Event

import pytest

from tests.test_member_auth import headers
from tests.test_save_intents import run
from tests.test_saved_drafts import prepared, post, body
from tests.test_saved_profiles import post as save_profile, request_body
from tests.test_saved_journey_import import accept_ai, start


async def editing(ctx, browser):
    repository, intent = await prepared(ctx, browser)
    assert (await save_profile(browser, request_body(intent['save_intent_id']))).status_code == 201
    original = await post(browser, body(intent['save_intent_id']))
    assert original.status_code == 201
    document = original.json()
    await accept_ai(browser)
    ctx['journeys'].stored_profiles = ctx['app'].state.saved_profile_service
    ctx['app'].state.draft_service.stored_drafts = ctx['app'].state.saved_draft_service
    profile = (await browser.get('/api/v1/profiles/me')).json()['saved']
    journey = (await start(browser, profile)).json()
    saved = (await browser.get(f"/api/v1/drafts/{document['document_id']}")).json()
    request = {'profile_version': 1, 'opportunity': saved['opportunity'], 'mode': 'from_saved',
        'saved_document': {'document_id': document['document_id'], 'version': 1}}
    return repository, document, saved, journey, request


async def copy(browser, journey, request, key=None):
    return await browser.post(f"/api/v1/journeys/{journey['journey_id']}/drafts", json=request,
        headers={**headers(browser), 'Idempotency-Key': key or str(uuid4())})


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_reedit_needs_new_approval_and_explicit_save_preserves_old_version_on_failure(tmp_path, backend):
    async def scenario(ctx, browser):
        repository, document, saved, journey, request = await editing(ctx, browser)
        key = str(uuid4()); response = await copy(browser, journey, request, key)
        assert response.status_code == 201, response.text
        draft = response.json()
        assert draft['mode'] == 'from_saved' and draft['revision'] == 1 and draft['approved_at'] is None
        assert draft['draft_id'] != str(ctx['draft'].draft_id)
        assert draft['self_introduction'] == saved['self_introduction'] and draft['motivation'] == saved['motivation']
        assert (await copy(browser, journey, request, key)).json() == draft
        path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{draft['draft_id']}"
        value = {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'draft_id': draft['draft_id'], 'revision': 1},
            'document_id': document['document_id'], 'base_document_version': 1}
        assert (await post(browser, value)).json()['code'] == 'DRAFT_NOT_APPROVED'
        changed = await browser.patch(path, json={'base_revision': 1, 'self_introduction': '다시 확인한 가상 경험',
            'motivation': '다시 적은 가상 동기'}, headers=headers(browser))
        assert changed.status_code == 200 and changed.json()['approved_at'] is None
        assert (await browser.get(f"/api/v1/drafts/{document['document_id']}")).json() == saved
        approved = await browser.post(path + '/approve', json={'base_revision': 2}, headers=headers(browser))
        assert approved.status_code == 200 and approved.json()['approved_at'] is not None
        value['source']['revision'] = approved.json()['revision']
        cipher = repository.profiles.cipher; repository.profiles.cipher = None
        assert (await post(browser, value)).status_code == 503
        repository.profiles.cipher = cipher
        assert (await browser.get(path)).json()['self_introduction'] == '다시 확인한 가상 경험'
        assert (await browser.get(f"/api/v1/drafts/{document['document_id']}")).json() == saved
        saved_key = str(uuid4()); result = await post(browser, value, saved_key)
        assert result.status_code == 201 and result.json()['version'] == 2, result.text
        assert (await post(browser, value, saved_key)).json() == result.json()
        assert (await post(browser, value)).json()['code'] == 'VERSION_CONFLICT'
        current = (await browser.get(f"/api/v1/drafts/{document['document_id']}")).json()
        assert current['self_introduction'] == '다시 확인한 가상 경험'
        from app.contracts.drafts import SavedDocumentRef
        session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        old = await ctx['app'].state.saved_draft_service.edit_source(session,
            SavedDocumentRef(document_id=document['document_id'], version=1))
        assert old.content.self_introduction == saved['self_introduction']
    run(tmp_path, scenario, backend)


def test_from_saved_rejects_foreign_or_missing_reference_and_anonymous(tmp_path):
    async def scenario(ctx, browser):
        _, _, _, journey, request = await editing(ctx, browser)
        assert (await copy(browser, journey, {**request, 'saved_document': {**request['saved_document'], 'version': 99}})).status_code == 404
        await browser.post('/api/v1/auth/logout', headers=headers(browser))
        assert (await copy(browser, journey, request)).status_code == 401
        from app.modules.auth.service import Identity
        anonymous = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        other = await ctx['members'].complete(anonymous, Identity('886611'), 'login')
        browser.cookies.set('__Host-rc_session', other.issued.token, domain='testserver.local', path='/')
        await browser.get('/api/v1/me'); await accept_ai(browser)
        assert (await copy(browser, journey, request)).status_code == 404
    run(tmp_path, scenario)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_changed_profile_copy_warns_and_requires_explicit_profile_save_first(tmp_path, backend):
    async def scenario(ctx, browser):
        _, document, saved, journey, request = await editing(ctx, browser)
        path = f"/api/v1/journeys/{journey['journey_id']}/profile"
        profile = (await browser.get(path)).json()['draft']
        profile['experiences'][0]['description'] = '새로 재확정한 가상 경험'
        assert (await browser.patch(path, json={'draft': profile, 'base_revision': 1}, headers=headers(browser))).status_code == 200
        assert (await browser.post(path + '/confirm', json={'base_revision': 2}, headers=headers(browser))).status_code == 200
        request['profile_version'] = 2
        response = await copy(browser, journey, request)
        assert response.status_code == 201, response.text
        draft = response.json()
        assert len(draft['warnings']) == 2 and draft['self_introduction'] == saved['self_introduction'] and draft['approved_at'] is None
        draft_path = f"/api/v1/journeys/{journey['journey_id']}/drafts/{draft['draft_id']}"
        approved = await browser.post(draft_path + '/approve', json={'base_revision': 1}, headers=headers(browser))
        assert approved.status_code == 200
        value = {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'draft_id': draft['draft_id'], 'revision': 2},
            'document_id': document['document_id'], 'base_document_version': 1}
        assert (await post(browser, value)).json()['code'] == 'PROFILE_NOT_SAVED'
        assert (await browser.get(f"/api/v1/drafts/{document['document_id']}")).json() == saved
        result = await save_profile(browser, {'source': {'type': 'journey', 'journey_id': journey['journey_id'], 'version': 2}, 'base_saved_version': 1})
        assert result.status_code == 201
        result = await post(browser, value)
        assert result.status_code == 201 and result.json()['profile_version'] == 2
    run(tmp_path, scenario, backend)


def test_postgresql_logout_during_saved_copy_prevents_late_redis_document(tmp_path):
    async def scenario(ctx, browser):
        repository, _, _, journey, request = await editing(ctx, browser)
        began, release = Event(), Event(); original = repository.edit_reference
        def delayed(*args):
            source = original(*args); began.set()
            if not release.wait(5): raise RuntimeError('시험 읽기 대기 만료')
            return source
        repository.edit_reference = delayed
        old = browser.cookies.get('__Host-rc_session')
        copying = asyncio.create_task(copy(browser, journey, request))
        assert await asyncio.to_thread(began.wait, 5)
        leaving = asyncio.create_task(browser.post('/api/v1/auth/logout', headers=headers(browser)))
        try:
            async with asyncio.timeout(.8):
                while await ctx['sessions'].resolve(old) is not None: await asyncio.sleep(.01)
            assert not leaving.done()
        finally: release.set()
        assert (await copying).status_code == 401 and (await leaving).status_code == 204
    run(tmp_path, scenario, 'postgresql')
