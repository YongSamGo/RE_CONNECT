"""내부 음성 전송·출력 검증·실제 Redis 공통 슬롯. 모델 품질 시험은 아니다."""

import asyncio
import io
import json
import struct
from uuid import uuid4
import wave

import httpx
import pytest

from app.adapters.internal_speech import InternalSpeechAdapter, MAX_AUDIO_BYTES
from app.adapters.speech import SpeechInvalidInputError, SpeechInvalidOutputError, SpeechTimeoutError, SpeechUnavailableError
from app.core.business_errors import AppError
from app.modules.admission.service import Lease
from app.modules.admission.speech import ControlledSpeechAdapter
from tests.test_admission import identity, with_redis


def wav(frames=160, rate=16000, channels=1, width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setparams((channels, width, rate, frames, 'NONE', 'not compressed'))
        output.writeframes(b'\x01' * frames * channels * width)
    return buffer.getvalue()


def terminal(request, *, content=None, data=None, status=200, completed=True, matching=True, media=None):
    headers = {'X-Speech-Completed': '1' if completed else '0',
        'X-Speech-Request-ID': request.headers['X-Speech-Request-ID'] if matching else str(uuid4()),
        'Content-Type': media or ('application/json' if data is not None else 'audio/wav')}
    return httpx.Response(status, content=content if content is not None else json.dumps(data).encode(), headers=headers)


def test_stt_request_is_binary_bounded_internal_and_uses_current_job_terminal_evidence():
    calls, ended = [], []
    async def handler(request):
        calls.append(request)
        return terminal(request, data={'text': '가상 음성 경험입니다.', 'duration_seconds': 1.25})
    adapter = InternalSpeechAdapter(transport=httpx.MockTransport(handler))
    audio = wav()
    result = asyncio.run(adapter.transcribe(audio, content_type='audio/wav', on_runtime_ended=lambda: ended.append(True)))
    assert result.text == '가상 음성 경험입니다.' and result.duration_seconds == 1.25
    assert len(ended) == 1 and len(calls) == 1
    request = calls[0]
    assert str(request.url) == 'http://speech:8001/internal/transcriptions'
    assert request.content == audio and request.headers['content-type'] == 'audio/wav'
    assert request.headers['accept-encoding'] == 'identity'
    assert 'model' not in request.headers and 'cookie' not in request.headers


def test_tts_only_sends_text_and_discards_non_audio_wav_metadata():
    original = wav(rate=24000)
    decorated = original + b'JUNK' + struct.pack('<I', 6) + b'secret'
    decorated = decorated[:4] + struct.pack('<I', len(decorated) - 8) + decorated[8:]
    calls = []
    async def handler(request):
        calls.append(request)
        return terminal(request, content=decorated)
    output = asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).synthesize('확인한 표시 문장입니다.'))
    assert output == original and b'secret' not in output
    assert json.loads(calls[0].content) == {'text': '확인한 표시 문장입니다.'}
    assert str(calls[0].url) == 'http://speech:8001/internal/speech'


@pytest.mark.parametrize('data', [
    {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': True},
    {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': False},
    {'protocol_version': True, 'status': 'ready', 'stt': True, 'tts': True},
    {'protocol_version': 1, 'status': 'ready', 'stt': 1, 'tts': True},
    {'status': 'ready'}, [], {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': True, 'extra': 'unverified'},
])
def test_ready_requires_both_models_and_exact_protocol(data):
    async def handler(request):
        assert str(request.url) == 'http://speech:8001/health/ready'
        return httpx.Response(200, json=data)
    expected = data == {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': True} and isinstance(data, dict) and type(data.get('protocol_version')) is int and type(data.get('stt')) is bool
    assert asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).is_ready()) is expected


@pytest.mark.parametrize('audio,media', [(b'', 'audio/wav'), (b'bad', 'audio/webm'), (wav(rate=44100), 'audio/wav'),
    (wav(channels=2), 'audio/wav'), (wav(width=1), 'audio/wav'), (wav(frames=90 * 16000 + 1), 'audio/wav'),
    (b'OggS\x00' + b'x' * MAX_AUDIO_BYTES, 'audio/ogg'), (wav(), 'image/png')],
    ids=['empty', 'bad-signature', 'high-rate', 'stereo', 'sample-width', 'too-long', 'too-large', 'wrong-media'])
def test_invalid_recording_is_rejected_before_transport(audio, media):
    calls = []
    adapter = InternalSpeechAdapter(transport=httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(SpeechInvalidInputError):
        asyncio.run(adapter.transcribe(audio, content_type=media))
    assert not calls


def test_90_second_wav_and_recognized_compressed_signatures_have_only_transport_validation():
    adapter = InternalSpeechAdapter()
    adapter.validate_transcription(wav(frames=90 * 16000), content_type='audio/wav')
    for data, media in [(b'\x1aE\xdf\xa3data', 'audio/webm; codecs=opus'), (b'OggS\x00data', 'audio/ogg'), (b'\x00\x00\x00\x18ftypisom', 'audio/mp4')]:
        adapter.validate_transcription(data, content_type=media)
    # 압축 decoder/무음/실제 재생시간 검증의 성공으로 계산하지 않는다.


@pytest.mark.parametrize('text', ['', ' ', 'x' * 2001, 'hidden\x00body', True])
def test_invalid_speech_text_is_rejected_before_transport(text):
    calls = []
    adapter = InternalSpeechAdapter(transport=httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(SpeechInvalidInputError):
        asyncio.run(adapter.synthesize(text))
    assert not calls


@pytest.mark.parametrize('changes', [{'completed': False}, {'matching': False}, {'media': 'text/html'}, {'data': {'text': 'x', 'duration_seconds': 91}},
    {'data': {'text': 'x', 'duration_seconds': 1, 'owner_id': 'forged'}}, {'data': {'text': '', 'duration_seconds': 1}}])
def test_invalid_or_unmatched_transcription_never_exposes_a_model_body(changes):
    ended = []
    async def handler(request):
        return terminal(request, **{'data': {'text': 'private raw text', 'duration_seconds': 1}, **changes})
    adapter = InternalSpeechAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(SpeechInvalidOutputError) as error:
        asyncio.run(adapter.transcribe(wav(), content_type='audio/wav', on_runtime_ended=lambda: ended.append(True)))
    assert 'private raw text' not in str(error.value)
    assert bool(ended) == (changes.get('completed', True) and changes.get('matching', True))


def test_internal_redirect_is_not_followed_and_proxy_environment_is_ignored(monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://untrusted.invalid:9999')
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={'Location': 'https://outside.invalid/audio'})
    adapter = InternalSpeechAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(SpeechUnavailableError):
        asyncio.run(adapter.synthesize('화면 문장'))
    assert len(calls) == 1 and calls[0].url.host == 'speech'


def test_response_byte_limit_and_content_encoding_fail_without_releasing_an_unfinished_job(monkeypatch):
    monkeypatch.setattr('app.adapters.internal_speech.MAX_WAV_BYTES', 128)
    for encoded in [False, True]:
        ended = []
        async def handler(request):
            response = terminal(request, content=wav(frames=1024))
            if encoded:
                return httpx.Response(200, headers={**response.headers, 'Content-Encoding': 'gzip'}, stream=httpx.ByteStream(b'not decoded'))
            return response
        with pytest.raises(SpeechInvalidOutputError):
            asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).synthesize('문장', on_runtime_ended=lambda: ended.append(True)))
        assert not ended


def test_timeout_and_cancellation_do_not_claim_the_remote_runtime_has_stopped():
    async def scenario():
        ended = []
        async def slow(request):
            await asyncio.sleep(1)
            return terminal(request, content=wav())
        adapter = InternalSpeechAdapter(timeout_seconds=0.01, transport=httpx.MockTransport(slow))
        with pytest.raises(SpeechTimeoutError):
            await adapter.synthesize('문장', on_runtime_ended=lambda: ended.append(True))
        task = asyncio.create_task(adapter.synthesize('문장', on_runtime_ended=lambda: ended.append(True)))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not ended
    asyncio.run(scenario())


def test_actual_redis_slot_is_shared_by_speech_and_llm_and_only_matching_terminal_releases():
    async def scenario(admission, store, redis):
        started, finish = asyncio.Event(), asyncio.Event()
        async def blocking(request):
            started.set()
            await finish.wait()
            return terminal(request, data={'text': '가상 전사', 'duration_seconds': 1})
        speech = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(blocking)), admission)
        actor = identity()
        task = asyncio.create_task(speech.transcribe(wav(), content_type='audio/wav', identity=actor))
        await asyncio.wait_for(started.wait(), 3)
        for operation in [speech.synthesize('문장', identity=actor), admission.run(actor, 'llm', lambda completion: asyncio.sleep(0))]:
            with pytest.raises(AppError, match='INFERENCE_BUSY'):
                await operation
        finish.set()
        assert (await task).text == '가상 전사' and await redis.hget(store.control_key, 'active') is None
        async def malformed(request):
            return terminal(request, content=b'private bad wav')
        broken = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(malformed)), admission)
        with pytest.raises(SpeechInvalidOutputError):
            await broken.synthesize('문장', identity=actor)
        assert await redis.hget(store.control_key, 'active') is None
        async def no_terminal(request):
            return terminal(request, content=wav(), matching=False)
        conservative = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(no_terminal)), admission)
        with pytest.raises(SpeechInvalidOutputError):
            await conservative.synthesize('문장', identity=actor)
        active = await redis.hget(store.control_key, 'active')
        assert active
        with pytest.raises(AppError, match='INFERENCE_BUSY'):
            await speech.transcribe(wav(), content_type='audio/wav', identity=actor)
        await store.release(Lease(active))  # 시험에서만 런타임 정지 확인을 대체한다.
        assert await redis.hget(store.control_key, 'global') == '3'
    with_redis(scenario)


def test_subject_and_preflight_are_required_before_speech_admission():
    async def scenario(admission, store, redis):
        adapter = ControlledSpeechAdapter(InternalSpeechAdapter(), admission)
        with pytest.raises(AppError, match='SERVICE_UNAVAILABLE'):
            await adapter.synthesize('문장')
        with pytest.raises(SpeechInvalidInputError):
            await adapter.transcribe(b'not audio', content_type='audio/wav', identity=identity())
        assert await redis.hget(store.control_key, 'global') == '0'
    with_redis(scenario)
