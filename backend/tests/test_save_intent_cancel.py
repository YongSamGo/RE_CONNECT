"""저장 대기 취소: 부적절한 인가(SEC-02), CSRF(INP-11), 경쟁조건(TIM-01)."""

import asyncio
from threading import Event
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.persistence import ApplicationDraft, ProfileVersion
from app.core.business_errors import AppError
from tests.test_member_auth import headers
from tests.test_save_intents import create, grant, run, save_login
from tests.test_saved_drafts import configured, body as draft_body, post as save_draft
from tests.test_saved_profiles import post as save_profile, request_body


def path(identity):
    return '/api/v1/auth/save-intents/' + identity


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_anonymous_cancel_is_owner_scoped_idempotent_and_does_not_end_journey(tmp_path, backend):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser)
        url = path(intent['save_intent_id'])
        assert (await browser.delete(url)).status_code == 403
        assert (await browser.delete(url, headers=headers(browser))).status_code == 204
        assert (await browser.delete(url, headers=headers(browser))).status_code == 204
        assert await ctx['intents'].reference(ctx['issued'].session) is None
        assert (await browser.get(f"/api/v1/journeys/{ctx['journey'].journey_id}/profile")).status_code == 200
        # A new reference is not cancelled by a replay for the previous ID.
        next_intent = await create(ctx, browser)
        assert (await browser.delete(url, headers=headers(browser))).status_code == 204
        assert await ctx['intents'].reference(ctx['issued'].session) == next_intent['save_intent_id']
        other = await ctx['sessions'].issue()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(ctx['app'], client=('192.0.2.5', 30001)), base_url='https://testserver') as peer:
            peer.cookies.set('__Host-rc_session', other.token, domain='testserver.local', path='/')
            await peer.get('/api/v1/me')
            response = await peer.delete(path(next_intent['save_intent_id']), headers={**headers(peer), 'X-User-ID': str(ctx['issued'].session.subject_id), 'X-Role': 'admin'})
            assert response.status_code == 204
        assert await ctx['intents'].reference(ctx['issued'].session) == next_intent['save_intent_id']
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_member_cancel_keeps_saved_profile_consent_and_session_but_blocks_draft(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx)
        intent = await create(ctx, browser)
        await save_login(browser)
        await grant(browser)
        key = str(uuid4())
        first = await save_profile(browser, request_body(intent['save_intent_id']), key)
        assert first.status_code == 201
        before = (await browser.get('/api/v1/me')).json()
        assert before['pending_save_intent'] is not None
        response = await browser.delete(path(intent['save_intent_id']), headers=headers(browser))
        assert response.status_code == 204 and response.headers['cache-control'] == 'no-store'
        after = (await browser.get('/api/v1/me')).json()
        assert after['authenticated'] and after['user'] == before['user'] and after['consents'] == before['consents']
        assert after['pending_save_intent'] is None
        denied = await save_draft(browser, draft_body(intent['save_intent_id']))
        assert denied.status_code == 404 and denied.json()['code'] == 'SAVE_INTENT_NOT_FOUND'
        # A completed write receipt is a replay, never a second body write.
        assert (await save_profile(browser, request_body(intent['save_intent_id']), key)).json() == first.json()
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 0
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_cancel_rejects_body_query_and_preserves_pending_on_failure(tmp_path, backend):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser)
        url = path(intent['save_intent_id'])
        assert (await browser.delete(url + '?owner_id=' + str(uuid4()), headers=headers(browser))).status_code == 422
        assert (await browser.request('DELETE', url, json={'owner_id': str(uuid4())}, headers=headers(browser))).status_code == 422
        assert (await browser.delete(path('invalid-id'), headers=headers(browser))).status_code == 422
        assert await ctx['intents'].reference(ctx['issued'].session) == intent['save_intent_id']
    run(tmp_path, scenario, backend)


def test_member_cancellation_waits_for_active_profile_write_then_prevents_bundle_tail(tmp_path):
    async def scenario(ctx, browser):
        repository, _ = configured(ctx)
        intent = await create(ctx, browser)
        await save_login(browser)
        await grant(browser)
        began, release = Event(), Event()
        original = repository.profiles.write
        def held(*args):
            result = original(*args)
            began.set()
            if not release.wait(5):
                raise AppError('SERVICE_UNAVAILABLE')
            return result
        repository.profiles.write = held
        saving = asyncio.create_task(save_profile(browser, request_body(intent['save_intent_id'])))
        assert await asyncio.to_thread(began.wait, 5)
        cancelling = asyncio.create_task(browser.delete(path(intent['save_intent_id']), headers=headers(browser)))
        try:
            await asyncio.sleep(.05)
            assert not cancelling.done()
        finally:
            release.set()
        assert (await saving).status_code == 201
        assert (await cancelling).status_code == 204
        assert (await browser.get('/api/v1/me')).json()['pending_save_intent'] is None
        assert (await save_draft(browser, draft_body(intent['save_intent_id']))).status_code == 404
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 0
    run(tmp_path, scenario, 'postgresql')


def test_cancel_store_failure_returns_failure_preserves_payload_and_allows_retry(tmp_path):
    async def scenario(ctx, browser):
        intent = await create(ctx, browser)
        original = ctx['intents'].store.discard
        async def unavailable(*args):
            raise AppError('SERVICE_UNAVAILABLE')
        ctx['intents'].store.discard = unavailable
        failed = await browser.delete(path(intent['save_intent_id']), headers=headers(browser))
        assert failed.status_code == 503
        assert await ctx['intents'].reference(ctx['issued'].session) == intent['save_intent_id']
        ctx['intents'].store.discard = original
        assert (await browser.delete(path(intent['save_intent_id']), headers=headers(browser))).status_code == 204
        assert await ctx['intents'].reference(ctx['issued'].session) is None
    run(tmp_path, scenario)
