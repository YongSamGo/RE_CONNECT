"""저장 프로필의 실제 복호화·소유권·현재 AI 동의·새 체험 분리 시험."""

from uuid import uuid4
import asyncio
from threading import Event

import pytest

from app.modules.auth.service import Identity
from tests.test_consents import AI_VERSION
from tests.test_member_auth import headers
from tests.test_save_intents import create, grant, run, save_login
from tests.test_saved_profiles import configured, post as save_profile, request_body


async def prepared(ctx, browser):
    repository = configured(ctx)
    ctx['journeys'].stored_profiles = ctx['app'].state.saved_profile_service
    intent = await create(ctx, browser, draft=False);await save_login(browser);await grant(browser)
    assert (await save_profile(browser, request_body(intent['save_intent_id']))).status_code == 201
    saved = (await browser.get('/api/v1/profiles/me')).json()['saved']
    return repository, saved


async def accept_ai(browser):
    response = await browser.post('/api/v1/consents',json={'purpose':'ai_processing','notice_version':AI_VERSION},headers=headers(browser))
    assert response.status_code == 201


async def start(browser, saved, key=None):
    return await browser.post('/api/v1/journeys',json={'ai_notice_version':AI_VERSION,
        'saved_profile':{'profile_id':saved['profile_id'],'version':saved['version']}},
        headers={**headers(browser),'Idempotency-Key':key or str(uuid4())})


@pytest.mark.parametrize('backend',['sqlite','postgresql'])
def test_saved_profile_starts_new_confirmed_one_with_no_conversation_or_automatic_save(tmp_path,backend):
    async def scenario(ctx,browser):
        _,saved=await prepared(ctx,browser)
        assert (await start(browser,saved)).json()['code']=='CONSENT_REQUIRED'
        await accept_ai(browser);key=str(uuid4());result=await start(browser,saved,key)
        assert result.status_code==201,result.text
        journey=result.json();assert journey['confirmed']['version']==1 and journey['confirmed']['confirmed_at']==saved['confirmed_at']
        assert journey['journey_id']!=str(ctx['journey'].journey_id) and journey['first_message']['message_id']!=str(ctx['journey'].first_message.message_id)
        path=f"/api/v1/journeys/{journey['journey_id']}/profile";view=(await browser.get(path)).json()
        assert view['draft']==saved['content'] and view['evidence']==[] and not view['has_unconfirmed_changes']
        session=await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        from uuid import UUID
        assert await ctx['journeys'].store.message_data(session,UUID(journey['journey_id']),AI_VERSION,'conversation')=='[]'
        view['draft']['experiences'][0]['description']='새 체험에서만 바꾼 가상 경험'
        assert (await browser.patch(path,json={'draft':view['draft'],'base_revision':1},headers=headers(browser))).status_code==200
        assert (await browser.get('/api/v1/profiles/me')).json()['saved']==saved
        assert (await start(browser,saved,key)).json()['journey_id']==journey['journey_id']
        another=await start(browser,saved);assert another.status_code==201 and another.json()['journey_id']!=journey['journey_id']
        fresh=(await browser.get(f"/api/v1/journeys/{another.json()['journey_id']}/profile")).json()
        assert fresh['draft']==saved['content'] and fresh['confirmed']['version']==1 and fresh['evidence']==[]
    run(tmp_path,scenario,backend)


def test_anonymous_other_owner_and_missing_key_cannot_import_saved_profile(tmp_path):
    async def scenario(ctx,browser):
        repo,saved=await prepared(ctx,browser);await accept_ai(browser)
        cipher=repo.cipher;repo.cipher=None
        assert (await start(browser,saved)).status_code==503
        repo.cipher=cipher
        await browser.post('/api/v1/auth/logout',headers=headers(browser))
        assert (await start(browser,saved)).status_code==401
        anonymous=await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        other=await ctx['members'].complete(anonymous,Identity('887766'),'login')
        browser.cookies.set('__Host-rc_session',other.issued.token,domain='testserver.local',path='/');await browser.get('/api/v1/me');await accept_ai(browser)
        assert (await start(browser,saved)).status_code==404
        session=await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        assert await ctx['redis'].exists(ctx['sessions'].store.key(session.digest)+':journeys')==0
    run(tmp_path,scenario)


@pytest.mark.parametrize('backend',['sqlite','postgresql'])
def test_owned_saved_draft_reference_prepares_edit_data_without_reusing_approval(tmp_path,backend):
    async def scenario(ctx,browser):
        from app.contracts.drafts import SavedDocumentRef
        from app.core.business_errors import AppError
        from tests.test_saved_drafts import prepared as prepare_draft,post as save_draft,body as draft_body
        _,intent=await prepare_draft(ctx,browser)
        assert (await save_profile(browser,request_body(intent['save_intent_id']))).status_code==201
        saved=await save_draft(browser,draft_body(intent['save_intent_id']));assert saved.status_code==201
        session=await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        reference=SavedDocumentRef(document_id=saved.json()['document_id'],version=1)
        service=ctx['app'].state.saved_draft_service
        with pytest.raises(AppError) as denied:await service.edit_source(session,reference)
        assert denied.value.code=='CONSENT_REQUIRED'
        await accept_ai(browser);source=await service.edit_source(session,reference)
        assert source.content.self_introduction=='직접 확인한 가상 지원서입니다.' and source.profile_reference.version==1
        assert not hasattr(source,'approved_at') and '가상' not in repr(source)
        with pytest.raises(AppError) as missing:
            await service.edit_source(session,SavedDocumentRef(document_id=reference.document_id,version=99))
        assert missing.value.code=='NOT_FOUND'
        await browser.post('/api/v1/auth/logout',headers=headers(browser))
        anonymous=await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        other=await ctx['members'].complete(anonymous,Identity('776655'),'login')
        browser.cookies.set('__Host-rc_session',other.issued.token,domain='testserver.local',path='/');await browser.get('/api/v1/me');await accept_ai(browser)
        other_session=await ctx['sessions'].resolve(other.issued.token)
        with pytest.raises(AppError) as foreign:await service.edit_source(other_session,reference)
        assert foreign.value.code=='NOT_FOUND'
    run(tmp_path,scenario,backend)


def test_postgresql_logout_during_source_read_cannot_create_late_copied_journey(tmp_path):
    async def scenario(ctx,browser):
        repo,saved=await prepared(ctx,browser);await accept_ai(browser)
        began,release=Event(),Event();original=repo.reference
        def delayed(*args):
            result=original(*args);began.set()
            if not release.wait(5):raise RuntimeError('시험 읽기 대기 만료')
            return result
        repo.reference=delayed;old=browser.cookies.get('__Host-rc_session')
        creating=asyncio.create_task(start(browser,saved));assert await asyncio.to_thread(began.wait,5)
        leaving=asyncio.create_task(browser.post('/api/v1/auth/logout',headers=headers(browser)))
        try:
            async with asyncio.timeout(.8):
                while await ctx['sessions'].resolve(old) is not None:await asyncio.sleep(.01)
            assert not leaving.done()
        finally:release.set()
        assert (await creating).status_code==404 and (await leaving).status_code==204
        assert (await browser.get('/api/v1/me')).json()['authenticated'] is False
    run(tmp_path,scenario,'postgresql')
