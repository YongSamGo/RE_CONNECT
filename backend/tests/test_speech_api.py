"""읽을 자료 참조·실제 Redis 읽기 완료·세션/체험/본문 변경 경합."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update

from app.adapters.internal_speech import InternalSpeechAdapter
from app.contracts.drafts import DraftUpdate
from app.contracts.journey import MessageCreate
from app.contracts.speech import SpeechRequest
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.speech import ControlledSpeechAdapter
from app.modules.journeys.messages import JourneyMessageService
from app.modules.requests.repository import RedisRequestStore
from app.modules.requests.service import RequestService, ResourceReadCheck, SessionCompletionGuard
from app.modules.speech.service import SpeechService
from app.persistence.operations import OpportunityVersion
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_internal_speech import terminal, wav
from tests.test_journey_drafts import OPPORTUNITY, body, setup as base_setup
from tests.test_journey_messages import Runtime as MessageRuntime
from tests.test_journeys import BODY
from tests.test_profile_confirmation import ready_edit


class Runtime:
    def __init__(self):
        self.texts, self.started, self.finish = [], None, None

    async def handle(self, request):
        self.texts.append(json.loads(request.content)['text'])
        if self.started:
            self.started.set()
            await self.finish.wait()
        return terminal(request, content=wav(rate=24000))


async def setup(admission, admission_store, redis, db):
    issued, sessions, journeys, journey, identity, _, drafts = await base_setup(admission, admission_store, redis, db)
    requests = RequestService(RedisRequestStore(redis, prefix=admission_store.prefix + 'requests:', session_key=journeys.store.session_key))
    runtime = Runtime()
    service = SpeechService(journeys, drafts, drafts.opportunities, journeys.consents, requests,
        ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(runtime.handle)), admission))
    return issued, sessions, journeys, journey, identity, drafts, runtime, service


def public(field='title', segment=0):
    return SpeechRequest(target={'kind': 'opportunity', 'opportunity_id': OPPORTUNITY, 'version': 1, 'field': field}, segment=segment)


@pytest.mark.parametrize('database', ['sqlite', 'postgresql'])
def test_actual_http_versioned_public_field_only_and_no_audio_replay_or_revision_mutation(database):
    async def scenario(admission, admission_store, redis):
        with open_test_database(database) as db:
            issued, sessions, journeys, journey, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
            app.state.session_service, app.state.admission_service, app.state.speech_service = sessions, admission, service
            before = await journeys.profile(issued.session, journey.journey_id)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
                client.cookies.set('__Host-rc_session', issued.token); await client.get('/api/v1/me')
                headers = {**csrf(client), 'Idempotency-Key': str(uuid4())}
                assert (await client.post('/api/v1/speech', json=public().model_dump(mode='json'))).status_code == 403
                response = await client.post('/api/v1/speech', json=public().model_dump(mode='json'), headers=headers)
                assert response.status_code == 200 and response.content == wav(rate=24000)
                assert response.headers['content-type'] == 'audio/wav' and response.headers['cache-control'] == 'no-store'
                assert response.headers['x-speech-segment-count'] == '1'
                assert runtime.texts == ['가상 도서관 자료 정리']
                retry = await client.post('/api/v1/speech', json=public().model_dump(mode='json'), headers=headers)
                assert retry.status_code == 409 and retry.json()['code'] == 'REQUEST_ALREADY_COMPLETED'
                for change in [{'text': '사용자 자유 문장'}, {'voice': 'clone'}, {'owner_id': str(uuid4())}, {'segment': True}]:
                    assert (await client.post('/api/v1/speech', json={**public().model_dump(mode='json'), **change}, headers={**headers, 'Idempotency-Key': str(uuid4())})).status_code == 422
                wrong_version = public().model_dump(mode='json'); wrong_version['target']['version'] = 99
                assert (await client.post('/api/v1/speech', json=wrong_version, headers={**headers, 'Idempotency-Key': str(uuid4())})).status_code == 409
                assert (await client.post('/api/v1/speech', json=public(segment=99).model_dump(mode='json'), headers={**headers, 'Idempotency-Key': str(uuid4())})).status_code == 422
                assert len(runtime.texts) == 1
                await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
                assert (await client.post('/api/v1/speech', json=public().model_dump(mode='json'), headers={**headers, 'Idempotency-Key': str(uuid4())})).status_code == 403
            assert await journeys.profile(issued.session, journey.journey_id) == before
            assert await redis.hget(admission_store.control_key, 'global') == '1'
    with_redis(scenario)


def test_long_visible_field_reads_only_selected_2000_character_segment():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, _, _, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            content = '가' * 2000 + '나' * 2000 + '다' * 1000
            db.execute(update(OpportunityVersion).where(OpportunityVersion.opportunity_id == OPPORTUNITY).values(description_text=content))
            audio, count = await service.read(issued.session, identity, str(uuid4()), public('description_text', 1))
            assert audio == wav(rate=24000) and count == 3 and runtime.texts == ['나' * 2000]
            with pytest.raises(AppError, match='VALIDATION_FAILED'):
                await service.read(issued.session, identity, str(uuid4()), public('description_text', 3))
            assert len(runtime.texts) == 1
    with_redis(scenario)


def test_private_draft_reads_current_stored_revision_without_changing_body_approval_or_idle_lifetime():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, drafts, runtime, service = await setup(admission, admission_store, redis, db)
            draft = await drafts.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            draft = await drafts.update(issued.session, journey.journey_id, draft.draft_id, DraftUpdate(self_introduction='화면의 직접 작성 내용', motivation='', base_revision=1))
            target = SpeechRequest(target={'kind': 'journey_draft', 'journey_id': journey.journey_id, 'draft_id': draft.draft_id, 'revision': 2, 'field': 'self_introduction'}, segment=0)
            meta = journeys.store.resource_key(identity.subject_id, journey.journey_id) + ':lifecycle'
            before = await redis.hgetall(meta); ttl = await redis.pttl(meta)
            assert (await service.read(issued.session, identity, str(uuid4()), target))[1] == 1
            assert runtime.texts == ['화면의 직접 작성 내용']
            assert await redis.hgetall(meta) == before and 0 < await redis.pttl(meta) <= ttl
            assert (await journeys.profile(issued.session, journey.journey_id)).revision == 3
            wrong = target.model_copy(update={'target': target.target.model_copy(update={'revision': 1})})
            with pytest.raises(AppError, match='VERSION_CONFLICT'):
                await service.read(issued.session, identity, str(uuid4()), wrong)
    with_redis(scenario)


def test_only_owned_assistant_questions_can_be_resolved_including_the_initial_question():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, _, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            target = SpeechRequest(target={'kind': 'journey_message', 'journey_id': journey.journey_id, 'message_id': journey.first_message.message_id}, segment=0)
            await service.read(issued.session, identity, str(uuid4()), target)
            assert runtime.texts[-1] == journey.first_message.text
            messages = JourneyMessageService(journeys, service.requests, ControlledLLMAdapter(MessageRuntime(), admission))
            message = await messages.send(issued.session, identity, journey.journey_id, str(uuid4()), MessageCreate(text='가상 도서관에서 자료 정리를 도왔어요.', transcription_id=None, base_revision=1))
            question = target.model_copy(update={'target': target.target.model_copy(update={'message_id': message.assistant_message.message_id})})
            await service.read(issued.session, identity, str(uuid4()), question)
            assert runtime.texts[-1] == message.assistant_message.text
            user_text = target.model_copy(update={'target': target.target.model_copy(update={'message_id': message.user_message_id})})
            with pytest.raises(AppError, match='NOT_FOUND'):
                await service.read(issued.session, identity, str(uuid4()), user_text)
            other = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            foreign = question.model_copy(update={'target': question.target.model_copy(update={'journey_id': other.journey_id})})
            with pytest.raises(AppError, match='NOT_FOUND'):
                await service.read(issued.session, identity, str(uuid4()), foreign)
            assert (await journeys.profile(issued.session, journey.journey_id)).revision == 2
    with_redis(scenario)


@pytest.mark.parametrize('change', ['draft_edit', 'profile_edit', 'delete', 'withdraw', 'revoke', 'regrant'])
def test_atomic_read_completion_rechecks_dependencies_after_the_last_source_lookup(change, monkeypatch):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, drafts, _, service = await setup(admission, admission_store, redis, db)
            draft = await drafts.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            draft = await drafts.update(issued.session, journey.journey_id, draft.draft_id, DraftUpdate(self_introduction='승인 전 표시 문장', motivation='', base_revision=1))
            target = SpeechRequest(target={'kind': 'journey_draft', 'journey_id': journey.journey_id, 'draft_id': draft.draft_id, 'revision': 2, 'field': 'self_introduction'}, segment=0)
            complete = service.requests.complete_readonly
            async def race(*args, **kwargs):
                if change == 'draft_edit':
                    await drafts.update(issued.session, journey.journey_id, draft.draft_id, DraftUpdate(self_introduction='새로 편집한 문장', motivation='', base_revision=2))
                elif change == 'profile_edit':
                    await journeys.update_profile(issued.session, journey.journey_id, ready_edit(revision=3))
                elif change == 'delete':
                    await journeys.end(issued.session, journey.journey_id)
                elif change == 'revoke':
                    await redis.delete(journeys.store.session_key(issued.session.digest))
                else:
                    await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
                    if change == 'regrant':
                        from app.modules.consents.models import ConsentCreate
                        from app.modules.consents.service import ConsentActor
                        await asyncio.sleep(0.003)
                        await journeys.consents.grant(ConsentActor(identity.subject_id, session_digest=issued.session.digest), ConsentCreate(purpose='ai_processing', notice_version=BODY.ai_notice_version))
                return await complete(*args, **kwargs)
            monkeypatch.setattr(service.requests, 'complete_readonly', race)
            with pytest.raises(AppError):
                await service.read(issued.session, identity, str(uuid4()), target)
    with_redis(scenario)


@pytest.mark.parametrize('change', ['source', 'withdraw', 'revoke'])
def test_public_audio_is_discarded_after_source_or_session_changes_during_synthesis(change):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, _, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
            task = asyncio.create_task(service.read(issued.session, identity, str(uuid4()), public()))
            await asyncio.wait_for(runtime.started.wait(), 3)
            if change == 'source':
                db.execute(update(OpportunityVersion).where(OpportunityVersion.opportunity_id == OPPORTUNITY).values(title='변경된 표시 문장'))
            elif change == 'withdraw':
                await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
            else:
                await redis.delete(journeys.store.session_key(issued.session.digest))
            runtime.finish.set()
            with pytest.raises(AppError):
                await task
    with_redis(scenario)


def test_same_key_pending_and_other_key_busy_do_not_duplicate_inference():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, _, _, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            runtime.started, runtime.finish = asyncio.Event(), asyncio.Event(); key = str(uuid4())
            task = asyncio.create_task(service.read(issued.session, identity, key, public()))
            await asyncio.wait_for(runtime.started.wait(), 3)
            with pytest.raises(AppError, match='REQUEST_IN_PROGRESS'):
                await service.read(issued.session, identity, key, public())
            with pytest.raises(AppError, match='INFERENCE_BUSY'):
                await service.read(issued.session, identity, str(uuid4()), public())
            runtime.finish.set(); await task
            assert len(runtime.texts) == 1
    with_redis(scenario)


def test_saved_document_identity_cannot_be_asserted_by_a_reference():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, _, _, identity, _, runtime, service = await setup(admission, admission_store, redis, db)
            with pytest.raises(AppError, match='UNAUTHENTICATED'):
                await service.read(issued.session, identity, str(uuid4()), SpeechRequest(target={'kind': 'saved_draft', 'document_id': uuid4(), 'version': 1, 'field': 'motivation'}, segment=0))
            assert not runtime.texts
    with_redis(scenario)


def test_read_guards_require_server_digest_notice_milliseconds_and_exact_owned_field_name():
    with pytest.raises(ValueError):
        SessionCompletionGuard('not-digest', 'notice', 1)
    with pytest.raises(ValueError):
        SessionCompletionGuard('a' * 64, 'notice', True)
    for name in ['profile_draft', 'draft:forged', f'other:{uuid4()}']:
        with pytest.raises(ValueError):
            ResourceReadCheck(name, '{}')
