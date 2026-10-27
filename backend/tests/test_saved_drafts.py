"""승인 지원서 암호화·근거/소유권·동의·실제 SQL/Redis/HTTP 경합."""

import asyncio
from threading import Event
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.contracts.drafts import DraftUpdate
from app.contracts.saved_drafts import DraftSaveRequest
from app.core.business_errors import AppError
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.auth.service import Identity
from app.modules.drafts.repository import RedisDraftStore
from app.modules.drafts.service import DraftService
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService
from app.modules.saved_drafts.repository import SqlDraftRepository
from app.modules.saved_drafts.service import SavedDraftService
from app.persistence import ApplicationDocument, ApplicationDraft, ApplicationWriteReceipt, Consent, ProfileVersion
from app.persistence.operations import OpportunityVersion, OpportunityPublication
from tests.test_consents import AI_VERSION
from tests.test_journey_drafts import Runtime
from tests.test_member_auth import headers, login
from tests.test_profile_confirmation import ready_edit
from tests.test_save_intents import create, grant, run, save_login
from tests.test_saved_profiles import configured as configure_profile, post as save_profile, request_body as profile_body


def configured(ctx):
    profiles = configure_profile(ctx)
    drafts = DraftService(RedisDraftStore(ctx['redis'], session_key=ctx['sessions'].store.key, resource_key=ctx['requests'].resource_key),
        ctx['journeys'], PublicOpportunityService(SqlPublicOpportunityRepository(ctx['engine'].connect)),
        ControlledLLMAdapter(Runtime(), ctx['app'].state.admission_service))
    ctx['app'].state.draft_service = drafts
    repository = SqlDraftRepository(profiles)
    ctx['app'].state.saved_draft_service = SavedDraftService(repository, ctx['members'], ctx['consents'], ctx['intents'], ctx['journeys'], drafts)
    return repository, drafts


def body(identity, document=None, base=None):
    return {'source': {'type': 'save_intent', 'save_intent_id': identity}, 'document_id': document, 'base_document_version': base}


async def post(browser, value, key=None):
    return await browser.post('/api/v1/drafts', json=value, headers={**headers(browser), 'Idempotency-Key': key or str(uuid4())})


async def prepared(ctx, browser):
    repository, drafts = configured(ctx)
    changed = await drafts.update(ctx['issued'].session, ctx['journey'].journey_id, ctx['draft'].draft_id,
        DraftUpdate(self_introduction='직접 확인한 가상 지원서입니다.', motivation='직접 작성한 가상 동기입니다.', base_revision=2))
    ctx['draft'] = await drafts.approve(ctx['issued'].session, ctx['journey'].journey_id, changed.draft_id, changed.revision)
    intent = await create(ctx, browser);await save_login(browser);await grant(browser)
    return repository, intent


@pytest.mark.parametrize('changes', [{'owner_id': str(uuid4())}, {'self_introduction': '클라이언트 본문'},
    {'document_id': str(uuid4())}, {'base_document_version': True}, {'source': {'type': 'journey', 'journey_id': str(uuid4()), 'draft_id': str(uuid4()), 'revision': False}}])
def test_save_draft_rejects_body_owner_invalid_pairs_and_revisions(changes):
    with pytest.raises(ValidationError):DraftSaveRequest.model_validate({**body(str(uuid4())), **changes})


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_explicit_profile_step_then_encrypted_draft_and_owned_reads(tmp_path, backend):
    async def scenario(ctx, browser):
        _, intent = await prepared(ctx, browser);value = body(intent['save_intent_id']);key = str(uuid4())
        denied = await post(browser, value, key)
        assert denied.status_code == 409 and denied.json()['code'] == 'PROFILE_NOT_SAVED'
        with ctx['engine'].connect() as db:assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 0
        assert (await save_profile(browser, profile_body(intent['save_intent_id']))).status_code == 201
        assert (await browser.post('/api/v1/drafts', json=value)).status_code == 403
        saved = await post(browser, value, key)
        assert saved.status_code == 201 and saved.json()['version'] == 1 and saved.json()['profile_version'] == 1, saved.text
        assert (await post(browser, value, key)).json() == saved.json()
        assert (await post(browser, value)).json()['code'] == 'REQUEST_ALREADY_COMPLETED'
        document = saved.json()['document_id']
        detail = await browser.get('/api/v1/drafts/' + document)
        assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
        assert detail.json()['self_introduction'] == '직접 확인한 가상 지원서입니다.' and detail.json()['review_reasons'] == []
        listed = (await browser.get('/api/v1/drafts')).json()
        assert listed['total'] == 1 and listed['items'][0]['document_id'] == document and 'self_introduction' not in listed['items'][0]
        assert (await browser.get('/api/v1/drafts?page=2')).json()['items'] == []
        assert (await browser.get('/api/v1/drafts?page_size=21')).status_code == 422
        with sessionmaker(ctx['engine'])() as db:
            row = db.scalars(select(ApplicationDraft)).one()
            assert '가상 지원서'.encode() not in row.ciphertext and len(row.nonce) == 12 and row.algorithm == 'AES-256-GCM'
            assert db.scalar(select(func.count()).select_from(ApplicationWriteReceipt)) == 1
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(update(ApplicationWriteReceipt).values(version=99))
        await browser.post('/api/v1/auth/logout', headers=headers(browser))
        anonymous = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
        other = await ctx['members'].complete(anonymous, Identity('998877'), 'login')
        browser.cookies.set('__Host-rc_session', other.issued.token, domain='testserver.local', path='/');await browser.get('/api/v1/me')
        assert (await browser.get('/api/v1/drafts/' + document, headers={'X-User-ID': document})).status_code == 404
        assert (await browser.get('/api/v1/drafts')).json()['total'] == 0
    run(tmp_path, scenario, backend)


@pytest.mark.parametrize('failure', ['closed', 'pending', 'withdraw', 'wrong_document', 'sql', 'key', 'tamper'])
def test_failure_does_not_silently_save_profile_or_unapproved_application(tmp_path, failure):
    async def scenario(ctx, browser):
        repo, intent = await prepared(ctx, browser)
        assert (await save_profile(browser, profile_body(intent['save_intent_id']))).status_code == 201
        if failure == 'closed':
            with ctx['engine'].begin() as db:db.execute(update(OpportunityVersion).values(recruitment_status='closed'))
        if failure == 'pending':
            with ctx['engine'].begin() as db:
                values = dict(db.execute(select(OpportunityVersion.__table__)).mappings().one());values.update(version=2, paid=not values['paid'], review_status='pending', reviewed_at=None)
                db.execute(OpportunityVersion.__table__.insert(), values)
        if failure == 'withdraw':
            from app.contracts.time import utc_now
            with ctx['engine'].begin() as db:db.execute(update(Consent).values(withdrawn_at=utc_now()))
        if failure == 'sql':
            original = repo.write
            def failed(*args):original(*args);raise AppError('SERVICE_UNAVAILABLE')
            repo.write = failed
        if failure == 'key':repo.profiles.cipher = None
        value = body(intent['save_intent_id'], str(uuid4()) if failure == 'wrong_document' else None, 1 if failure == 'wrong_document' else None)
        response = await post(browser, value)
        if failure == 'tamper':
            assert response.status_code == 201
            with sessionmaker(ctx['engine']).begin() as db:
                row = db.scalars(select(ApplicationDraft)).one()
                values = {column.name: getattr(row, column.name) for column in ApplicationDraft.__table__.columns}
                values.update(version=2, nonce=b'fixture00002');db.add(ApplicationDraft(**values))
            result = await browser.get('/api/v1/drafts/' + response.json()['document_id'])
            assert result.status_code == 503 and '가상 지원서' not in result.text
        else:
            assert response.status_code == {'closed':409, 'pending':409, 'withdraw':403, 'wrong_document':404, 'sql':503, 'key':503}[failure], response.text
            with ctx['engine'].connect() as db:
                assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 0
                assert db.scalar(select(func.count()).select_from(ApplicationWriteReceipt)) == 0
                assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            session = await ctx['sessions'].resolve(browser.cookies.get('__Host-rc_session'))
            assert bool(await ctx['redis'].exists(ctx['intents'].store.key(session.digest))) == (failure != 'sql')
    run(tmp_path, scenario)


def test_postgresql_same_request_concurrency_and_deleted_result_not_recreated(tmp_path):
    async def scenario(ctx, browser):
        _, intent = await prepared(ctx, browser);await save_profile(browser, profile_body(intent['save_intent_id']))
        value = body(intent['save_intent_id']);key = str(uuid4())
        results = await asyncio.gather(*(post(browser, value, key) for _ in range(6)))
        assert all(r.status_code == 201 and r.json() == results[0].json() for r in results)
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 1
            assert db.scalar(select(func.count()).select_from(ApplicationWriteReceipt)) == 1
        with ctx['engine'].begin() as db:db.execute(delete(ApplicationDocument))
        assert (await post(browser, value, key)).status_code == 404
    run(tmp_path, scenario, 'postgresql')


def test_postgresql_logout_during_writer_rolls_back_application_and_receipt(tmp_path):
    async def scenario(ctx, browser):
        repo, intent = await prepared(ctx, browser);await save_profile(browser, profile_body(intent['save_intent_id']))
        began, release = Event(), Event();original = repo.write
        def delayed(*args):
            result = original(*args);began.set()
            if not release.wait(5):raise AppError('SERVICE_UNAVAILABLE')
            return result
        repo.write = delayed;old = browser.cookies.get('__Host-rc_session')
        saving = asyncio.create_task(post(browser, body(intent['save_intent_id'])))
        assert await asyncio.to_thread(began.wait, 5)
        logout = asyncio.create_task(browser.post('/api/v1/auth/logout', headers=headers(browser)))
        try:
            async with asyncio.timeout(.8):
                while await ctx['sessions'].resolve(old) is not None:await asyncio.sleep(.01)
        finally:release.set()
        assert (await saving).status_code == 401 and (await logout).status_code == 204
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 0
            assert db.scalar(select(func.count()).select_from(ApplicationWriteReceipt)) == 0
    run(tmp_path, scenario, 'postgresql')


@pytest.mark.parametrize('backend', ['sqlite', 'postgresql'])
def test_member_journey_approval_document_update_and_review_flags_preserve_body(tmp_path, backend):
    async def scenario(ctx, browser):
        configured(ctx);await login(browser);await grant(browser)
        assert (await browser.post('/api/v1/consents', json={'purpose':'ai_processing','notice_version':AI_VERSION}, headers=headers(browser))).status_code == 201
        result = await browser.post('/api/v1/journeys', json={'saved_profile':None,'ai_notice_version':AI_VERSION},
            headers={**headers(browser),'Idempotency-Key':str(uuid4())});assert result.status_code == 201
        journey = result.json()['journey_id'];profile_path = f'/api/v1/journeys/{journey}/profile'
        assert (await browser.patch(profile_path, json=ready_edit().model_dump(mode='json'), headers=headers(browser))).status_code == 200
        assert (await browser.post(profile_path+'/confirm', json={'base_revision':2}, headers=headers(browser))).status_code == 200
        assert (await save_profile(browser, {'source':{'type':'journey','journey_id':journey,'version':1},'base_saved_version':None})).status_code == 201
        drafts_path = f'/api/v1/journeys/{journey}/drafts'
        result = await browser.post(drafts_path, json={'profile_version':1,'opportunity':{'id':str(UUID(int=1)),'version':1},'mode':'manual','saved_document':None},
            headers={**headers(browser),'Idempotency-Key':str(uuid4())});assert result.status_code == 201
        draft_id = result.json()['draft_id'];draft_path = drafts_path+'/'+draft_id
        value = {'source':{'type':'journey','journey_id':journey,'draft_id':draft_id,'revision':1},'document_id':None,'base_document_version':None}
        assert (await post(browser,value)).json()['code'] == 'DRAFT_NOT_APPROVED'
        assert (await browser.post(draft_path+'/approve',json={'base_revision':1},headers=headers(browser))).status_code == 200
        value['source']['revision']=2;key=str(uuid4());saved=await post(browser,value,key)
        assert saved.status_code == 201,saved.text
        document=saved.json()['document_id']
        assert (await browser.patch(draft_path,json={'self_introduction':'새로 확인한 가상 본문','motivation':'직접 확인한 동기','base_revision':2},headers=headers(browser))).status_code == 200
        update_body={**value,'source':{**value['source'],'revision':3},'document_id':document,'base_document_version':1}
        assert (await post(browser,update_body)).json()['code'] == 'DRAFT_NOT_APPROVED'
        assert (await browser.post(draft_path+'/approve',json={'base_revision':3},headers=headers(browser))).status_code == 200
        update_body['source']['revision']=4
        second=await post(browser,update_body);assert second.status_code == 201 and second.json()['version']==2
        assert (await post(browser,value,key)).json()==saved.json()
        assert (await post(browser,update_body)).json()['code']=='VERSION_CONFLICT'
        detail=(await browser.get('/api/v1/drafts/'+document)).json()
        assert detail['self_introduction']=='새로 확인한 가상 본문' and detail['review_reasons']==[]
        current=(await browser.get(profile_path)).json();current['draft']['experiences'][0]['description']='변경한 가상 프로필'
        assert (await browser.patch(profile_path,json={'draft':current['draft'],'base_revision':3},headers=headers(browser))).status_code == 200
        assert (await browser.post(profile_path+'/confirm',json={'base_revision':4},headers=headers(browser))).status_code == 200
        assert (await save_profile(browser,{'source':{'type':'journey','journey_id':journey,'version':2},'base_saved_version':1})).status_code == 201
        with ctx['engine'].begin() as db:db.execute(update(OpportunityVersion).values(recruitment_status='closed'))
        flagged=(await browser.get('/api/v1/drafts/'+document)).json()
        assert set(flagged['review_reasons'])=={'profile_changed','opportunity_closed'}
        assert flagged['self_introduction']==detail['self_introduction'] and flagged['approved_at']==detail['approved_at']
        with ctx['engine'].begin() as db:
            values=dict(db.execute(select(OpportunityVersion.__table__)).mappings().one())
            values.update(version=2,title='새로운 가상 공고',content_hash='b'*64,recruitment_status='open')
            db.execute(OpportunityVersion.__table__.insert(),values)
            db.execute(update(OpportunityPublication).values(version=2))
        changed=(await browser.get('/api/v1/drafts/'+document)).json()
        assert set(changed['review_reasons'])=={'profile_changed','opportunity_changed'}
        assert changed['opportunity_title']==detail['opportunity_title'] and changed['self_introduction']==detail['self_introduction']
        with ctx['engine'].connect() as db:
            assert db.scalar(select(func.count()).select_from(ApplicationDraft))==2
    run(tmp_path,scenario,backend)


@pytest.mark.parametrize("database", ["sqlite", "postgresql"])
def test_anonymous_edit_approval_then_explicit_member_bundle_save(tmp_path, database):
    async def scenario(ctx, browser):
        configured(ctx)

        def mutation_headers():
            return {**headers(browser), "Idempotency-Key": str(uuid4())}

        created = await browser.post("/api/v1/journeys", json={"ai_notice_version": AI_VERSION, "saved_profile": None}, headers=mutation_headers())
        assert created.status_code == 201, created.text
        journey_id = created.json()["journey_id"]
        profile_path = f"/api/v1/journeys/{journey_id}/profile"
        edited_profile = await browser.patch(profile_path, json=ready_edit().model_dump(mode="json"), headers=headers(browser))
        assert edited_profile.status_code == 200, edited_profile.text
        confirmed = await browser.post(profile_path + "/confirm", json={"base_revision": 2}, headers=headers(browser))
        assert confirmed.status_code == 200, confirmed.text

        draft_path = f"/api/v1/journeys/{journey_id}/drafts"
        creation_headers = mutation_headers()
        creation_body = {"profile_version": 1, "opportunity": {"id": "00000000-0000-0000-0000-000000000001", "version": 1}, "mode": "manual", "saved_document": None}
        created_draft = await browser.post(draft_path, json=creation_body, headers=creation_headers)
        assert created_draft.status_code == 201, created_draft.text
        assert (await browser.post(draft_path, json=creation_body, headers=creation_headers)).json() == created_draft.json()
        draft_id = created_draft.json()["draft_id"]
        draft_path += "/" + draft_id
        content = {"self_introduction": "가상 도서관에서 자료를 정리했습니다.", "motivation": "가상 활동에 경험을 보태고 싶습니다."}
        updated = await browser.patch(draft_path, json={"base_revision": 1, **content}, headers=headers(browser))
        assert updated.status_code == 200 and updated.json()["approved_at"] is None
        intent_body = {"journey_id": journey_id, "profile": {"version": 1}, "draft": {"draft_id": draft_id, "revision": 2}}
        denied = await browser.post("/api/v1/auth/save-intents", json=intent_body, headers=mutation_headers())
        assert denied.status_code == 409 and denied.json()["code"] == "DRAFT_NOT_APPROVED"
        approved = await browser.post(draft_path + "/approve", json={"base_revision": 2}, headers=headers(browser))
        assert approved.status_code == 200 and approved.json()["approved_at"] is not None
        intent_body["draft"]["revision"] = 3
        intent = await browser.post("/api/v1/auth/save-intents", json=intent_body, headers=mutation_headers())
        assert intent.status_code == 201, intent.text
        intent_id = intent.json()["save_intent_id"]

        # 제공자 신원만 대역이다. state·PKCE·세션 교체와 동의/저장은 실제 서비스다.
        await save_login(browser)
        me = await browser.get("/api/v1/me")
        assert me.json()["authenticated"] is True
        assert me.json()["pending_save_intent"]["save_intent_id"] == intent_id
        await grant(browser)
        before_profile = await post(browser, body(intent_id))
        assert before_profile.status_code == 409 and before_profile.json()["code"] == "PROFILE_NOT_SAVED"
        profile_key = str(uuid4())
        saved_profile = await save_profile(browser, profile_body(intent_id), profile_key)
        assert saved_profile.status_code == 201, saved_profile.text
        assert (await save_profile(browser, profile_body(intent_id), profile_key)).json() == saved_profile.json()
        draft_key = str(uuid4())
        saved = await post(browser, body(intent_id), draft_key)
        assert saved.status_code == 201, saved.text
        assert (await post(browser, body(intent_id), draft_key)).json() == saved.json()
        current = await browser.get("/api/v1/drafts/" + saved.json()["document_id"])
        assert current.status_code == 200 and current.headers["cache-control"] == "no-store"
        for field, value in content.items():
            assert current.json()[field] == value
        assert current.json()["review_reasons"] == []
        with sessionmaker(ctx["engine"])() as db:
            assert db.scalar(select(func.count()).select_from(ProfileVersion)) == 1
            assert db.scalar(select(func.count()).select_from(ApplicationDraft)) == 1
            row = db.scalars(select(ApplicationDraft)).one()
            assert content["self_introduction"].encode() not in row.ciphertext
            assert row.algorithm == "AES-256-GCM"

    run(tmp_path, scenario, database)
