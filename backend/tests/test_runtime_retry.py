"""실제 Redis 예산/lease와 전송 대역의 안전한 재시도 경계."""

import asyncio

import httpx
import pytest

from app.adapters.internal_speech import InternalSpeechAdapter
from app.adapters.llm import LLMUnavailableError, UntrustedTurn
from app.adapters.speech import SpeechInvalidOutputError, SpeechTransientUnavailableError, SpeechUnavailableError
from app.core.business_errors import AppError
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.retry import retry_once
from app.modules.admission.service import RuntimeCompletion
from app.modules.admission.speech import ControlledSpeechAdapter
from tests.test_admission import identity, with_redis
from tests.test_internal_speech import terminal, wav
from tests.test_ollama_adapter import Extracted, chat_response, make_adapter


def temporary(request, **changes):
    return terminal(request, status=503, data={'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}, **changes)


@pytest.mark.parametrize('changes,expected,ended', [
    ({}, SpeechTransientUnavailableError, True),
    ({'matching': False}, SpeechUnavailableError, False),
    ({'completed': False}, SpeechUnavailableError, False),
    ({'media': 'text/plain'}, SpeechUnavailableError, True),
])
def test_only_explicit_current_terminal_json_error_is_transient(changes, expected, ended):
    completion = RuntimeCompletion()
    async def handler(request):
        return temporary(request, **changes)
    with pytest.raises(expected) as caught:
        asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).synthesize('표시 문장',
            on_runtime_ended=completion.confirm_ended))
    assert type(caught.value) is expected
    assert completion.ended is ended


@pytest.mark.parametrize('data', [{'code': 'MODEL_MISSING'}, {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE', 'detail': 'private'}, []])
def test_unknown_or_extra_error_fields_are_not_treated_as_transient(data):
    async def handler(request):
        return terminal(request, status=503, data=data)
    with pytest.raises(SpeechUnavailableError) as caught:
        asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).synthesize('표시 문장'))
    assert type(caught.value) is SpeechUnavailableError
    assert 'private' not in str(caught.value)


def test_transient_type_without_terminal_evidence_does_not_retry():
    async def scenario():
        completion, calls = RuntimeCompletion(), []
        async def operation(attempt):
            calls.append(1)
            raise SpeechTransientUnavailableError('일시 오류')
        with pytest.raises(SpeechTransientUnavailableError):
            await retry_once(completion, operation, SpeechTransientUnavailableError)
        assert calls == [1] and not completion.ended
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['stt', 'tts', 'llm'])
@pytest.mark.parametrize('failure', [httpx.ConnectError, httpx.ConnectTimeout])
def test_real_redis_connection_retry_counts_one_budget_and_releases_final_lease(kind, failure):
    async def scenario(admission, store, redis):
        calls = []
        async def handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise failure('private details', request=request)
            if kind == 'llm':
                return chat_response('{"skills": [], "years": null}')
            return terminal(request, data={'text': '가상 전사', 'duration_seconds': 1}) if kind == 'stt' else terminal(request, content=wav())
        if kind == 'llm':
            output = await ControlledLLMAdapter(make_adapter(handler), admission).generate_structured(
                identity=identity(), instructions='고정 지침', untrusted_turns=[UntrustedTurn(role='user', text='가상 입력')], output_model=Extracted)
            assert output.skills == []
        else:
            adapter = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(handler)), admission)
            output = await adapter.transcribe(wav(), content_type='audio/wav', identity=identity()) if kind == 'stt' else await adapter.synthesize('표시 문장', identity=identity())
            assert output
            assert calls[0].headers['X-Speech-Request-ID'] != calls[1].headers['X-Speech-Request-ID']
        assert len(calls) == 2
        state = await redis.hgetall(store.control_key)
        assert state['global'] == '1' and 'active' not in state
        limits = [int(value) for key, value in state.items() if key.startswith('limit:')]
        assert limits and set(limits) == {1}
    with_redis(scenario)


@pytest.mark.parametrize('kind', ['stt', 'tts'])
def test_real_redis_terminal_temporary_error_retries_only_once(kind):
    async def scenario(admission, store, redis):
        calls = []
        async def handler(request):
            calls.append(request)
            return temporary(request)
        adapter = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(handler)), admission)
        with pytest.raises(SpeechTransientUnavailableError):
            if kind == 'stt':
                await adapter.transcribe(wav(), content_type='audio/wav', identity=identity())
            else:
                await adapter.synthesize('표시 문장', identity=identity())
        assert len(calls) == 2
        assert calls[0].headers['X-Speech-Request-ID'] != calls[1].headers['X-Speech-Request-ID']
        assert await redis.hget(store.control_key, 'global') == '1'
        assert await redis.hget(store.control_key, 'active') is None
    with_redis(scenario)


@pytest.mark.parametrize('mode', ['cancel', 'deadline'])
def test_real_redis_second_attempt_unknown_completion_keeps_slot_and_shared_deadline(mode):
    async def scenario(admission, store, redis):
        second, calls = asyncio.Event(), []
        async def handler(request):
            calls.append(request)
            if len(calls) == 1:
                await asyncio.sleep(0.025)
                return temporary(request)
            second.set()
            await asyncio.Event().wait()
        class ShortDeadline:
            async def run(self, actor, kind, operation):
                return await admission.run(actor, kind, operation, timeout_seconds=0.08)
        adapter = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(handler)), ShortDeadline())
        task = asyncio.create_task(adapter.synthesize('표시 문장', identity=identity()))
        await asyncio.wait_for(second.wait(), 2)
        if mode == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(AppError, match='AI_TIMEOUT'):
                await task
        assert len(calls) == 2 and await redis.hget(store.control_key, 'global') == '1'
        assert await redis.hget(store.control_key, 'active')
        with pytest.raises(AppError, match='INFERENCE_BUSY'):
            await admission.run(identity(), 'llm', lambda completion: asyncio.sleep(0))
    with_redis(scenario)


def test_real_redis_first_attempt_late_callback_cannot_end_second_attempt():
    async def scenario(admission, store, redis):
        second, callbacks = asyncio.Event(), []
        async def operation(attempt):
            callbacks.append(attempt.confirm_ended)
            if len(callbacks) == 1:
                attempt.confirm_ended()
                raise SpeechTransientUnavailableError('일시 오류')
            second.set()
            callbacks[0]()  # 이전 작업의 늦은 종료 통지는 최신 작업과 별개다.
            await asyncio.Event().wait()
        task = asyncio.create_task(admission.run(identity(), 'tts',
            lambda completion: retry_once(completion, operation, SpeechTransientUnavailableError)))
        await asyncio.wait_for(second.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(callbacks) == 2 and await redis.hget(store.control_key, 'active')
        assert await redis.hget(store.control_key, 'global') == '1'
    with_redis(scenario)


@pytest.mark.parametrize('kind', ['tts', 'llm'])
def test_real_redis_generic_503_is_not_retried_or_claimed_terminated(kind):
    async def scenario(admission, store, redis):
        calls = []
        async def handler(request):
            calls.append(request)
            return httpx.Response(503, json={'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'})
        with pytest.raises(SpeechUnavailableError if kind == 'tts' else LLMUnavailableError):
            if kind == 'tts':
                await ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(handler)), admission).synthesize('표시 문장', identity=identity())
            else:
                await ControlledLLMAdapter(make_adapter(handler), admission).generate_structured(identity=identity(),
                    instructions='x', untrusted_turns=[UntrustedTurn(role='user', text='x')], output_model=Extracted)
        assert len(calls) == 1 and await redis.hget(store.control_key, 'active')
    with_redis(scenario)


def test_real_redis_terminal_invalid_output_is_not_retried_but_releases():
    async def scenario(admission, store, redis):
        calls = []
        async def handler(request):
            calls.append(request)
            return terminal(request, content=b'invalid wave')
        with pytest.raises(SpeechInvalidOutputError):
            await ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(handler)), admission).synthesize('표시 문장', identity=identity())
        assert len(calls) == 1 and await redis.hget(store.control_key, 'active') is None
    with_redis(scenario)
