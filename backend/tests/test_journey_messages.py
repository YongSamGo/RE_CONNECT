"""메시지의 실제 Redis 완료 경계·추론 주체·불변 확정본·오류/동시 편집 시험."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.llm import LLMUnavailableError
from app.contracts.journey import MessageCreate, ProfileUpdate
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.generation.models import ExtractionPlan
from app.modules.generation.service import GroundedGenerationService
from app.modules.journeys.messages import JourneyMessageService
from app.modules.requests.service import RequestService
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, real_services
from tests.test_profile_confirmation import ready_edit

TEXT = '가상 도서관에서 자료 정리를 도왔어요.'


class Runtime:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.started = None
        self.finish = None
        self.pause_call = None
        self.corrupt = False
        self.include_prior = False

    async def is_ready(self):
        return True

    def validate_request(self, **kwargs):
        pass

    async def generate_structured(self, *, instructions, untrusted_turns, output_model, on_runtime_ended):
        self.calls += 1
        if self.started is not None and (self.pause_call is None or self.calls == self.pause_call):
            self.started.set()
            await self.finish.wait()
        on_runtime_ended()
        if self.fail:
            raise LLMUnavailableError('모델 시험 장애')
        data = json.loads(untrusted_turns[0].text)
        if output_model is ExtractionPlan:
            turns = data['turns'] if self.include_prior else data['turns'][-1:]
            return output_model.model_validate({'experiences': [{'existing_id': None,
                'description': {'turn_index': turn['turn_index'], 'text': '원문에 없는 경험' if self.corrupt else turn['text']},
                'duration': None, 'skills': [{'turn_index': turn['turn_index'], 'text': '자료 정리'}] if '자료 정리' in turn['text'] else []} for turn in turns]})
        return output_model.model_validate({'field': data['allowed_fields'][0]})


async def setup(admission, admission_store, redis):
    issued, sessions, journeys, store, requests, identity = await real_services(admission, admission_store, redis)
    journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
    runtime = Runtime()
    service = JourneyMessageService(journeys, RequestService(requests), ControlledLLMAdapter(runtime, admission))
    return issued, sessions, journeys, requests, identity, journey, runtime, service


def test_real_http_stores_message_draft_evidence_and_replays_without_repeating_inference():
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, requests, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
        app.state.session_service, app.state.consent_service = sessions, journeys.consents
        app.state.admission_service, app.state.journey_service = admission, journeys
        app.state.journey_message_service = service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
            client.cookies.set('__Host-rc_session', issued.token)
            await client.get('/api/v1/me')
            path = f'/api/v1/journeys/{journey.journey_id}/messages'
            body = {'text': TEXT, 'transcription_id': None, 'base_revision': 1}
            headers = {**csrf(client), 'Idempotency-Key': str(uuid4())}
            assert (await client.post(path, json=body)).status_code == 403
            response = await client.post(path, json=body, headers=headers)
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
            result = response.json()
            assert result['revision'] == result['profile']['revision'] == 2
            assert result['profile']['confirmed'] is None and not result['profile']['has_unconfirmed_changes']
            assert result['profile']['draft']['experiences'][0]['description'] == TEXT
            assert result['profile']['evidence'] == [{'path': 'experiences[0]', 'message_ids': [result['user_message_id']]}]
            assert result['assistant_message']['text'] == '어느 지역에서 활동하고 싶으세요?'
            assert runtime.calls == 2 and await redis.hget(admission_store.control_key, 'global') == '2'
            resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
            ttl = await redis.pttl(resource)
            assert (await client.post(path, json=body, headers=headers)).json() == result
            assert 0 < await redis.pttl(resource) <= ttl
            assert runtime.calls == 2
            view = await journeys.profile(issued.session, journey.journey_id)
            draft = view.draft.model_dump(mode='json'); draft['skills'] = ['직접 확인한 역량']
            await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate({'draft': draft, 'base_revision': 2}))
            assert (await client.post(path, json=body, headers=headers)).json() == result
            assert runtime.calls == 2 and (await journeys.profile(issued.session, journey.journey_id)).revision == 3
            assert (await client.post(path, json={**body, 'text': '다른 답변'}, headers=headers)).status_code == 409
            for changes, status in [({'base_revision': True}, 422), ({'owner_id': str(uuid4())}, 422),
                                    ({'transcription_id': str(uuid4())}, 404), ({'text': '연락처는 공일공 구팔칠육 오사삼이예요.'}, 422)]:
                result = await client.post(path, json={**body, **changes}, headers={**headers, 'Idempotency-Key': str(uuid4())})
                assert result.status_code == status
            from app.modules.consents.models import ConsentCreate
            from app.modules.consents.service import ConsentActor
            stranger = await sessions.issue()
            await journeys.consents.grant(ConsentActor(stranger.session.subject_id, session_digest=stranger.session.digest),
                ConsentCreate(purpose='ai_processing', notice_version=BODY.ai_notice_version))
            client.cookies.clear(); client.cookies.set('__Host-rc_session', stranger.token)
            await client.get('/api/v1/me')
            assert (await client.post(path, json=body, headers={**csrf(client), 'Idempotency-Key': str(uuid4())})).status_code == 404
            assert runtime.calls == 2
    with_redis(scenario)


@pytest.mark.parametrize('mutation', ['guard', 'reference', 'revision', 'profile_revision', 'history', 'missing', 'confirmation', 'step'])
def test_internal_message_commit_rejects_inconsistent_references_before_any_write(mutation):
    from app.contracts.journey import ConversationTurn, Message, MessageCommit, MessageResult, ProfileDraftView
    from app.contracts.profile import empty_profile_content
    from app.contracts.time import utc_now
    from app.modules.requests.service import CompletionGuard, Permit, RequestScope, ResultReference, validate_message_commit
    user_id = uuid4()
    draft = empty_profile_content()
    response = MessageResult(revision=2, user_message_id=user_id, assistant_message=Message(message_id=uuid4(), text='경험을 알려 주세요.', created_at=utc_now()),
        profile=ProfileDraftView(revision=2, draft=draft, evidence=[], confirmed=None, has_unconfirmed_changes=False,
            missing_for_recommendation=draft.missing_for_recommendation()), notices=[], next_step='continue')
    commit = MessageCommit(response=response, turns=[ConversationTurn(message_id=user_id, text=TEXT)])
    permit = Permit(RequestScope(uuid4(), 'messages', uuid4()), uuid4(), 'a' * 64, 'b' * 64, 1)
    reference = ResultReference('message', user_id, 2)
    guard = CompletionGuard('c' * 64, uuid4(), 'ai-test-v1')
    if mutation == 'guard': guard = None
    elif mutation == 'reference': reference = ResultReference('message', uuid4(), 2)
    elif mutation == 'revision': commit = commit.model_copy(update={'response': response.model_copy(update={'revision': 3})})
    elif mutation == 'profile_revision': commit = commit.model_copy(update={'response': response.model_copy(update={'profile': response.profile.model_copy(update={'revision': 3})})})
    elif mutation == 'history': commit = commit.model_copy(update={'turns': commit.turns + commit.turns})
    elif mutation == 'missing': commit = commit.model_copy(update={'response': response.model_copy(update={'profile': response.profile.model_copy(update={'missing_for_recommendation': []})})})
    elif mutation == 'confirmation': commit = commit.model_copy(update={'response': response.model_copy(update={'profile': response.profile.model_copy(update={'has_unconfirmed_changes': True})})})
    elif mutation == 'step': commit = commit.model_copy(update={'response': response.model_copy(update={'next_step': 'review_profile'})})
    with pytest.raises(AppError, match='VALIDATION_FAILED'):
        validate_message_commit(permit, reference, guard, commit)


@pytest.mark.parametrize('change', ['edit', 'delete', 'withdraw', 'expire', 'revoke'])
@pytest.mark.parametrize('phase', [1, 2])
def test_real_redis_result_is_discarded_when_state_changes_during_generation(change, phase):
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        runtime.pause_call = phase
        body = MessageCreate(text=TEXT, transcription_id=None, base_revision=1)
        task = asyncio.create_task(service.send(issued.session, identity, journey.journey_id, str(uuid4()), body))
        await asyncio.wait_for(runtime.started.wait(), 3)
        if change == 'edit':
            await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        elif change == 'delete':
            await journeys.end(issued.session, journey.journey_id)
        elif change == 'withdraw':
            await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
        elif change == 'expire':
            resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
            await redis.hset(resource + ':lifecycle', mapping={'created_ms': 0, 'last_ms': 0})
        else:
            await redis.delete(journeys.store.session_key(issued.session.digest))
        runtime.finish.set()
        with pytest.raises(AppError) as error:
            await task
        assert error.value.code == {'edit': 'VERSION_CONFLICT', 'delete': 'NOT_FOUND', 'withdraw': 'CONSENT_REQUIRED', 'expire': 'NOT_FOUND', 'revoke': 'NOT_FOUND'}[change]
        resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
        assert not await redis.hget(resource + ':lifecycle', 'conversation')
        assert not any(field.startswith('message_result:') for field in await redis.hkeys(resource + ':lifecycle'))
        assert runtime.calls == phase
        if change == 'edit':
            assert (await journeys.profile(issued.session, journey.journey_id)).draft.experiences[0].description == '가상 도서관 경험'
    with_redis(scenario)


@pytest.mark.parametrize('failure', ['unavailable', 'unsupported_fact'])
def test_real_redis_runtime_failure_and_new_request_preserve_old_confirmed_facts(failure):
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        confirmed = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
        before = await journeys.profile(issued.session, journey.journey_id)
        body = MessageCreate(text=TEXT, transcription_id=None, base_revision=3)
        runtime.fail, runtime.corrupt = failure == 'unavailable', failure == 'unsupported_fact'
        with pytest.raises(AppError, match='MODEL_UNAVAILABLE'):
            await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        assert await journeys.profile(issued.session, journey.journey_id) == before
        runtime.fail = False
        runtime.corrupt = False
        result = await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        assert result.revision == 4 and result.profile.has_unconfirmed_changes
        assert result.assistant_message is None and result.next_step == 'review_profile'
        assert (await journeys.resolve_profile(issued.session, confirmed.profile)).content == before.draft
        assert result.profile.draft.experiences[0] == before.draft.experiences[0]
        await journeys.end(issued.session, journey.journey_id)
        resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
        assert await redis.exists(resource, resource + ':lifecycle') == 0
    with_redis(scenario)


def test_real_redis_same_key_pending_and_gpu_busy_cannot_duplicate_message():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        body, key = MessageCreate(text=TEXT, transcription_id=None, base_revision=1), str(uuid4())
        task = asyncio.create_task(service.send(issued.session, identity, journey.journey_id, key, body))
        await asyncio.wait_for(runtime.started.wait(), 3)
        with pytest.raises(AppError, match='REQUEST_IN_PROGRESS'):
            await service.send(issued.session, identity, journey.journey_id, key, body)
        with pytest.raises(AppError, match='INFERENCE_BUSY'):
            await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        runtime.finish.set()
        result = await task
        assert result.revision == 2 and runtime.calls == 2
        turns = await journeys.conversation(issued.session, journey.journey_id, BODY.ai_notice_version)
        assert len(turns) == 1 and turns[0].message_id == result.user_message_id
    with_redis(scenario)


def test_real_redis_timeout_retains_input_state_and_does_not_release_unconfirmed_runtime(monkeypatch):
    monkeypatch.setattr('app.modules.journeys.messages.MESSAGE_TIMEOUT_SECONDS', 0.05)
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        body = MessageCreate(text=TEXT, transcription_id=None, base_revision=1)
        before = await journeys.profile(issued.session, journey.journey_id)
        with pytest.raises(AppError, match='AI_TIMEOUT'):
            await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        assert await journeys.profile(issued.session, journey.journey_id) == before
        with pytest.raises(AppError, match='INFERENCE_BUSY'):
            await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        assert runtime.calls == 1
        assert (await journeys.update_profile(issued.session, journey.journey_id, ready_edit())).revision == 2
    with_redis(scenario)


def test_real_redis_short_remaining_time_skips_second_model_call_and_releases_slot(monkeypatch):
    # 남은 시간이 질문 선택 최소 시간보다 적으면 두 번째 모델 호출을 시작하지 않는다.
    monkeypatch.setattr('app.modules.journeys.messages.QUESTION_MIN_SECONDS', 61)
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        body = MessageCreate(text=TEXT, transcription_id=None, base_revision=1)
        result = await service.send(issued.session, identity, journey.journey_id, str(uuid4()), body)
        assert runtime.calls == 1
        assert result.assistant_message is not None
        assert result.assistant_message.text == GroundedGenerationService.fallback_question(
            missing_fields=result.profile.missing_for_recommendation)
        assert await redis.hget(admission_store.control_key, 'active') is None
        second = MessageCreate(text=TEXT, transcription_id=None, base_revision=result.revision)
        assert (await service.send(issued.session, identity, journey.journey_id, str(uuid4()), second)).revision == result.revision + 1
        assert runtime.calls == 2
    with_redis(scenario)


def test_real_redis_history_does_not_resurrect_experiences_removed_by_manual_edit():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        runtime.include_prior = True
        first = await service.send(issued.session, identity, journey.journey_id, str(uuid4()), MessageCreate(text=TEXT, transcription_id=None, base_revision=1))
        edited = first.profile.draft.model_dump(mode='json'); edited['experiences'] = []
        await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate({'draft': edited, 'base_revision': 2}))
        text = '별도의 가상 이웃 안내 경험입니다.'
        result = await service.send(issued.session, identity, journey.journey_id, str(uuid4()), MessageCreate(text=text, transcription_id=None, base_revision=3))
        assert [item.description for item in result.profile.draft.experiences] == [text]
        assert result.profile.evidence[0].message_ids == [result.user_message_id]
    with_redis(scenario)


@pytest.mark.parametrize('history', ['count', 'bytes'])
def test_real_redis_history_limit_fails_without_another_model_call(history):
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, identity, journey, runtime, service = await setup(admission, admission_store, redis)
        values = [{'message_id': str(uuid4()), 'text': '가' * 2000 if history == 'bytes' else '가상'} for _ in range(2 if history == 'bytes' else 64)]
        resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
        await redis.hset(resource + ':lifecycle', 'conversation', json.dumps(values, ensure_ascii=True))
        with pytest.raises(AppError, match='PAYLOAD_TOO_LARGE'):
            await service.send(issued.session, identity, journey.journey_id, str(uuid4()), MessageCreate(text=TEXT, transcription_id=None, base_revision=1))
        assert runtime.calls == 0 and (await journeys.profile(issued.session, journey.journey_id)).revision == 1
        assert json.loads(await redis.hget(resource + ':lifecycle', 'conversation')) == values
    with_redis(scenario)
