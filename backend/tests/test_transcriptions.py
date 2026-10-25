"""전사 결과 소유권·미승인 원문 분리·원본 무파일 처리와 실제 Redis 완료 경계."""

import asyncio
import json
import tempfile
from uuid import uuid4

import httpx
import pytest

from app.adapters.internal_speech import InternalSpeechAdapter, MAX_AUDIO_BYTES
from app.contracts.journey import MessageCreate, Transcription
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.speech import ControlledSpeechAdapter
from app.modules.journeys.audio_upload import InvalidAudioUpload, parse_audio_upload
from app.modules.transcriptions.repository import RedisTranscriptionStore
from app.modules.transcriptions.service import TranscriptionService
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_internal_speech import terminal, wav
from tests.test_journeys import BODY, real_services
from tests.test_journey_messages import Runtime as MessageRuntime
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.journeys.messages import JourneyMessageService
from app.modules.requests.service import RequestService
from tests.test_profile_confirmation import ready_edit

ORIGINAL = '원래 전사에는 확인하지 않은 표현이 있습니다.'
EDITED = '가상 도서관에서 자료 정리를 도왔어요.'


class Runtime:
    def __init__(self):
        self.calls, self.started, self.finish = 0, None, None
        self.fail = False
        self.input_error = None

    async def handle(self, request):
        self.calls += 1
        if self.started:
            self.started.set()
            await self.finish.wait()
        if self.fail:
            return terminal(request, data={'private_error': '음성 원문'}, status=503)
        if self.input_error:
            return terminal(request, data={'code': self.input_error}, status=422)
        return terminal(request, data={'text': ORIGINAL, 'duration_seconds': 1.25})


async def setup(admission, admission_store, redis):
    issued, sessions, journeys, _, requests, identity = await real_services(admission, admission_store, redis)
    journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
    runtime = Runtime()
    speech = ControlledSpeechAdapter(InternalSpeechAdapter(transport=httpx.MockTransport(runtime.handle)), admission)
    store = RedisTranscriptionStore(redis, session_key=journeys.store.session_key, resource_key=requests.resource_key)
    service = TranscriptionService(store, journeys, speech)
    return issued, sessions, journeys, requests, journey, identity, runtime, service


def multipart(audio=b'audio', *, headers=None, boundary='test-boundary', final=True):
    headers = headers or b'Content-Disposition: form-data; name="audio"; filename="../../ignored.wav"\r\nContent-Type: audio/wav'
    return b'--' + boundary.encode() + b'\r\n' + headers + b'\r\n\r\n' + audio + b'\r\n--' + boundary.encode() + b'--' + (b'\r\n' if final else b'')


def test_memory_only_single_part_parser_preserves_exact_binary_and_ignores_file_paths(monkeypatch):
    def no_spool(*args, **kwargs):
        raise AssertionError('음성을 spool하면 안 됩니다')
    monkeypatch.setattr(tempfile, 'SpooledTemporaryFile', no_spool)
    for final in [False, True]:
        audio = wav()
        parsed, media = parse_audio_upload(multipart(audio, final=final), 'multipart/form-data; boundary="test-boundary"')
        assert parsed == audio and media == 'audio/wav'
    parsed, _ = parse_audio_upload(multipart(b'x' * MAX_AUDIO_BYTES), 'multipart/form-data; boundary=test-boundary')
    assert len(parsed) == MAX_AUDIO_BYTES
    with pytest.raises(AppError, match='PAYLOAD_TOO_LARGE'):
        parse_audio_upload(multipart(b'x' * (MAX_AUDIO_BYTES + 1)), 'multipart/form-data; boundary=test-boundary')


@pytest.mark.parametrize('case', ['duplicate-name', 'extra-part', 'extra-header', 'transfer-encoding', 'folded-header', 'duplicate-header',
    'wrong-field', 'extended-filename', 'bad-boundary', 'duplicate-boundary', 'empty', 'unterminated', 'preamble', 'epilogue', 'large-header'])
def test_restricted_upload_parser_rejects_ambiguous_or_unexpected_parts(case):
    headers = b'Content-Disposition: form-data; name="audio"; filename="recording.wav"\r\nContent-Type: audio/wav'
    content_type = 'multipart/form-data; boundary=test-boundary'
    raw = multipart(wav(), headers=headers)
    if case == 'duplicate-name':
        raw = multipart(wav(), headers=headers.replace(b'name="audio"', b'name="audio"; name="other"'))
    elif case == 'extra-part':
        raw = raw.replace(b'\r\n--test-boundary--', b'\r\n--test-boundary\r\nContent-Disposition: form-data; name="owner_id"\r\n\r\nforged\r\n--test-boundary--')
    elif case in {'extra-header', 'transfer-encoding', 'duplicate-header'}:
        extra = {'extra-header': b'X-Owner-ID: forged', 'transfer-encoding': b'Content-Transfer-Encoding: base64', 'duplicate-header': b'Content-Type: audio/wav'}[case]
        raw = multipart(wav(), headers=headers + b'\r\n' + extra)
    elif case == 'folded-header':
        raw = multipart(wav(), headers=headers.replace(b'name="audio"', b'\r\n name="audio"'))
    elif case == 'wrong-field':
        raw = multipart(wav(), headers=headers.replace(b'name="audio"', b'name="owner_id"'))
    elif case == 'extended-filename':
        raw = multipart(wav(), headers=headers.replace(b'filename=', b'filename*='))
    elif case == 'bad-boundary':
        content_type = 'multipart/form-data; boundary="bad boundary"'
    elif case == 'duplicate-boundary':
        content_type += '; boundary=other'
    elif case == 'empty':
        raw = multipart(b'')
    elif case == 'unterminated':
        raw = raw[:-8]
    elif case == 'preamble':
        raw = b'preamble' + raw
    elif case == 'epilogue':
        raw += b'epilogue'
    else:
        raw = multipart(wav(), headers=headers + b'\r\nX-Long: ' + b'x' * 4096)
    with pytest.raises(InvalidAudioUpload):
        parse_audio_upload(raw, content_type)


def test_actual_http_transcription_replay_has_no_profile_side_effect_and_only_edited_text_is_extracted(monkeypatch):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, requests, journey, identity, runtime, service = await setup(admission, admission_store, redis)
        app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
        app.state.session_service, app.state.admission_service, app.state.journey_service = sessions, admission, journeys
        app.state.transcription_service = service
        message_runtime = MessageRuntime()
        app.state.journey_message_service = JourneyMessageService(journeys, RequestService(requests), ControlledLLMAdapter(message_runtime, admission), service)
        def no_spool(*args, **kwargs):
            raise AssertionError('음성을 spool하면 안 됩니다')
        monkeypatch.setattr(tempfile, 'SpooledTemporaryFile', no_spool)
        before = await journeys.profile(issued.session, journey.journey_id)
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
            client.cookies.set('__Host-rc_session', issued.token)
            await client.get('/api/v1/me')
            path = f'/api/v1/journeys/{journey.journey_id}/transcriptions'
            files = {'audio': ('../../ignored.wav', wav(), 'audio/wav')}
            assert (await client.post(path, files=files)).status_code == 403
            headers = {**csrf(client), 'Idempotency-Key': str(uuid4())}
            response = await client.post(path, files=files, headers=headers)
            assert response.status_code == 201 and response.headers['cache-control'] == 'no-store'
            result = Transcription.model_validate(response.json())
            assert result.text == ORIGINAL and result.duration_seconds == 1.25
            assert await journeys.profile(issued.session, journey.journey_id) == before
            assert not await redis.hget(resource + ':lifecycle', 'conversation')
            ttl = await redis.pttl(resource)
            assert (await client.post(path, files=files, headers=headers)).json() == response.json()
            assert runtime.calls == 1 and 0 < await redis.pttl(resource) <= ttl
            assert (await client.post(path, files={'audio': ('x.wav', wav(frames=161), 'audio/wav')}, headers=headers)).status_code == 409
            await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
            assert (await client.post(path, files=files, headers=headers)).json() == response.json()
            message = await client.post(f'/api/v1/journeys/{journey.journey_id}/messages', json={'text': EDITED,
                'transcription_id': str(result.transcription_id), 'base_revision': 2}, headers={**csrf(client), 'Idempotency-Key': str(uuid4())})
            assert message.status_code == 200
            descriptions = [e['description'] for e in message.json()['profile']['draft']['experiences']]
            assert EDITED in descriptions and ORIGINAL not in descriptions
            turns = json.loads(await redis.hget(resource + ':lifecycle', 'conversation'))
            assert [turn['text'] for turn in turns] == [EDITED]
            other = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            with pytest.raises(AppError, match='NOT_FOUND'):
                await app.state.journey_message_service.send(issued.session, identity, other.journey_id, str(uuid4()),
                    MessageCreate(text=EDITED, transcription_id=result.transcription_id, base_revision=1))
            stored = await redis.hgetall(resource + ':lifecycle')
            assert not any('ignored.wav' in value or 'RIFF' in value for value in stored.values())
            from app.modules.consents.models import ConsentCreate
            from app.modules.consents.service import ConsentActor
            other_session = await sessions.issue()
            await journeys.consents.grant(ConsentActor(other_session.session.subject_id, session_digest=other_session.session.digest),
                ConsentCreate(purpose='ai_processing', notice_version=BODY.ai_notice_version))
            with pytest.raises(AppError, match='NOT_FOUND'):
                await service.require(other_session.session, journey.journey_id, result.transcription_id)
            await journeys.end(issued.session, journey.journey_id)
            assert not await redis.exists(resource + ':lifecycle')
            with pytest.raises(AppError, match='NOT_FOUND'):
                await service.require(issued.session, journey.journey_id, result.transcription_id)
    with_redis(scenario)


@pytest.mark.parametrize('change', ['edit', 'delete', 'withdraw', 'expire', 'revoke', 'generation'])
def test_late_transcription_cannot_commit_after_state_changes(change):
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, journey, identity, runtime, service = await setup(admission, admission_store, redis)
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(service.create(issued.session, identity, journey.journey_id, str(uuid4()), wav(), 'audio/wav'))
        await asyncio.wait_for(runtime.started.wait(), 3)
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        if change == 'edit':
            await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        elif change == 'delete':
            await journeys.end(issued.session, journey.journey_id)
        elif change == 'withdraw':
            await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
        elif change == 'expire':
            await redis.hset(resource + ':lifecycle', mapping={'created_ms': 0, 'last_ms': 0})
        elif change == 'revoke':
            await redis.delete(journeys.store.session_key(issued.session.digest))
        else:
            await redis.hset(resource + ':lifecycle', 'generation', str(uuid4()))
        runtime.finish.set()
        with pytest.raises(AppError):
            await task
        assert not any(field.startswith('transcription:') for field in await redis.hkeys(resource + ':lifecycle'))
    with_redis(scenario)


def test_pending_replay_cancellation_and_runtime_failure_do_not_leave_a_transcript():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, requests, journey, identity, runtime, service = await setup(admission, admission_store, redis)
        runtime.fail = True
        key = str(uuid4())
        with pytest.raises(AppError, match='MODEL_UNAVAILABLE'):
            await service.create(issued.session, identity, journey.journey_id, key, wav(), 'audio/wav')
        with pytest.raises(AppError, match='REQUEST_ALREADY_COMPLETED'):
            await service.create(issued.session, identity, journey.journey_id, key, wav(), 'audio/wav')
        runtime.fail = False
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        key = str(uuid4())
        task = asyncio.create_task(service.create(issued.session, identity, journey.journey_id, key, wav(), 'audio/wav'))
        await asyncio.wait_for(runtime.started.wait(), 3)
        with pytest.raises(AppError, match='REQUEST_IN_PROGRESS'):
            await service.create(issued.session, identity, journey.journey_id, key, wav(), 'audio/wav')
        with pytest.raises(AppError, match='INFERENCE_BUSY'):
            await service.create(issued.session, identity, journey.journey_id, str(uuid4()), wav(), 'audio/wav')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        assert not any(field.startswith('transcription:') for field in await redis.hkeys(resource + ':lifecycle'))
        assert await redis.hget(admission_store.control_key, 'active')
        assert runtime.calls == 2
    with_redis(scenario)


@pytest.mark.parametrize('code,reason', [('AUDIO_TOO_LONG', 'out_of_range'), ('AUDIO_INVALID', 'invalid_value')])
def test_internal_decoder_rejection_is_a_fixed_audio_field_error_with_terminal_release(code, reason):
    async def scenario(admission, admission_store, redis):
        issued, sessions, _, _, journey, _, runtime, service = await setup(admission, admission_store, redis)
        runtime.input_error = code
        app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
        app.state.session_service, app.state.admission_service, app.state.transcription_service = sessions, admission, service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
            client.cookies.set('__Host-rc_session', issued.token)
            await client.get('/api/v1/me')
            response = await client.post(f'/api/v1/journeys/{journey.journey_id}/transcriptions', files={'audio': ('x.wav', wav(), 'audio/wav')}, headers={**csrf(client), 'Idempotency-Key': str(uuid4())})
            assert response.status_code == 422
            assert response.json()['fields'] == [{'path': 'audio', 'reason': reason}]
            assert await redis.hget(admission_store.control_key, 'active') is None
    with_redis(scenario)


def test_transcription_timeout_has_no_result_and_does_not_unlock_the_gpu(monkeypatch):
    monkeypatch.setattr('app.modules.transcriptions.service.TRANSCRIPTION_TIMEOUT_SECONDS', 0.02)
    async def scenario(admission, admission_store, redis):
        issued, _, _, requests, journey, identity, runtime, service = await setup(admission, admission_store, redis)
        runtime.started, runtime.finish = asyncio.Event(), asyncio.Event()
        with pytest.raises(AppError, match='AI_TIMEOUT'):
            await service.create(issued.session, identity, journey.journey_id, str(uuid4()), wav(), 'audio/wav')
        resource = requests.resource_key(identity.subject_id, journey.journey_id)
        assert not any(field.startswith('transcription:') for field in await redis.hkeys(resource + ':lifecycle'))
        assert await redis.hget(admission_store.control_key, 'active')
    with_redis(scenario)


def test_corrupt_counters_fail_before_any_journal_or_result_write():
    async def scenario(admission, admission_store, redis):
        issued, _, _, requests, journey, identity, runtime, service = await setup(admission, admission_store, redis)
        meta = requests.resource_key(identity.subject_id, journey.journey_id) + ':lifecycle'
        for field in ['transcription_attempts', 'transcription_count']:
            for bad in ['-1', '1.5', '01', 'nan']:
                await redis.hset(meta, field, bad)
                key = str(uuid4())
                with pytest.raises(AppError, match='SERVICE_UNAVAILABLE'):
                    await service.create(issued.session, identity, journey.journey_id, key, wav(), 'audio/wav')
                assert not any(name.startswith(f'transcription-create:{key}:') for name in await redis.hkeys(meta))
            await redis.hdel(meta, field)
        permit = await service.store.begin(issued.session, journey.journey_id, uuid4(), 'a' * 64, 1, BODY.ai_notice_version)
        await redis.hset(meta, 'transcription_count', '1.5')
        with pytest.raises(AppError, match='SERVICE_UNAVAILABLE'):
            await service.store.complete(issued.session, journey.journey_id, permit,
                Transcription(transcription_id=permit.transcription_id, text='가상 전사', duration_seconds=1))
        assert not await redis.hget(meta, f'transcription:{permit.transcription_id}') and runtime.calls == 0
    with_redis(scenario)


def test_http_file_limits_and_format_failures_are_checked_before_model_call():
    async def scenario(admission, admission_store, redis):
        issued, sessions, _, _, journey, _, runtime, service = await setup(admission, admission_store, redis)
        app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
        app.state.session_service, app.state.admission_service, app.state.transcription_service = sessions, admission, service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
            client.cookies.set('__Host-rc_session', issued.token)
            await client.get('/api/v1/me')
            path = f'/api/v1/journeys/{journey.journey_id}/transcriptions'
            for data, media, status, reason in [(wav(frames=90 * 16000 + 1), 'audio/wav', 422, 'out_of_range'),
                (b'not a real recording', 'audio/webm', 422, 'invalid_value'), (b'x' * (MAX_AUDIO_BYTES + 1), 'audio/ogg', 413, None)]:
                response = await client.post(path, files={'audio': ('x.bin', data, media)}, headers={**csrf(client), 'Idempotency-Key': str(uuid4())})
                assert response.status_code == status
                if reason:
                    assert response.json()['fields'] == [{'path': 'audio', 'reason': reason}]
        assert runtime.calls == 0 and await redis.hget(admission_store.control_key, 'global') == '0'
    with_redis(scenario)
