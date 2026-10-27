import asyncio
import json
from functools import partial
import multiprocessing
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audio import MAX_UPLOAD
from app.main import create_app
from app.process_runtime import ProcessRuntime
from process_fixtures import STT, TTS, BrokenSTT, BlockingSTT


def headers(media='audio/wav'):
    return {'Content-Type': media, 'X-Speech-Request-ID': str(uuid4())}


def factory(stt=STT, tts=TTS):
    return lambda: ProcessRuntime(stt_loader=stt, tts_loader=tts)


def test_loaded_both_models_and_owned_job_terminal_headers():
    with TestClient(create_app(runtime_factory=factory())) as http:
        assert http.get('/health/ready').json() == dict(protocol_version=1, status='ready', stt=True, tts=True)
        request_headers = headers()
        result = http.post('/internal/transcriptions', headers=request_headers, content=b'audio')
        assert result.status_code == 200 and set(result.json()) == {'text', 'duration_seconds'}
        assert result.headers['x-speech-request-id'] == request_headers['X-Speech-Request-ID']
        assert result.headers['x-speech-completed'] == '1' and result.headers['cache-control'] == 'no-store'
        result = http.post('/internal/speech', headers=headers('application/json'), json={'text': '공개 가상 문장'})
        assert result.status_code == 200 and result.headers['content-type'] == 'audio/wav'
        assert result.content[:4] == b'RIFF' and result.headers['x-speech-completed'] == '1'
        assert not http.app.state.runtime_lock.locked()
        assert http.get('/docs').status_code == 404


def test_partial_model_loading_is_never_reported_as_whole_service_ready():
    with TestClient(create_app(runtime_factory=factory(tts=None))) as http:
        ready = http.get('/health/ready')
        assert ready.status_code == 503 and ready.json() == dict(protocol_version=1, status='not_ready', stt=True, tts=False)
        result = http.post('/internal/speech', headers=headers('application/json'), json={'text': '문장'})
        assert result.status_code == 503 and result.json() == {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}


def test_input_size_content_type_and_job_id_fail_before_inference():
    with TestClient(create_app(runtime_factory=factory())) as http:
        for request_headers, body in [({}, b'audio'), ({**headers(), 'Content-Type': 'text/plain'}, b'not audio'),
            (headers(), b'x' * (MAX_UPLOAD + 1))]:
            result = http.post('/internal/transcriptions', headers=request_headers, content=body)
            assert result.status_code == 422
        for payload in ({'text': ''}, {'text': 'x' * 2001}, {'text': 'a\x00b'}, {'text': '<|im_end|>'},
            {'text': 'ok', 'speaker': 'other'}, {'text': 'ok', 'url': 'https://example.test'}, ['wrong'], None):
            result = http.post('/internal/speech', headers=headers('application/json'), json=payload)
            assert result.status_code == 422 and result.json() == {'code': 'TEXT_INVALID'}
        for raw in (b'{"text":"one","text":"two"}', b'x' * 32769, b'not-json'):
            assert http.post('/internal/speech', headers=headers('application/json'), content=raw).status_code == 422
        assert http.post('/internal/speech', headers={**headers('application/json'), 'Content-Encoding': 'gzip'}, content=b'body').status_code == 422
        escaped = json.dumps({'text': '😀' * 2000}, ensure_ascii=True).encode()
        assert len(escaped) > 16384
        assert http.post('/internal/speech', headers=headers('application/json'), content=escaped).status_code == 200


@pytest.mark.parametrize('code,status', [('AUDIO_TOO_LONG', 422), ('RUNTIME_UNAVAILABLE', 503)])
def test_worker_error_is_fixed_and_acknowledged_after_cleanup(code, status):
    with TestClient(create_app(runtime_factory=factory(stt=partial(BrokenSTT, code)))) as http:
        result = http.post('/internal/transcriptions', headers=headers(), content=b'audio')
        assert result.status_code == status and result.json() == {'code': code}
        assert result.headers['x-speech-completed'] == '1'
        assert not http.app.state.runtime_lock.locked() and 'private' not in result.text


@pytest.mark.parametrize('mode', ['timeout', 'cancel', 'crash',
    pytest.param('kill', marks=pytest.mark.skipif(os.name == 'nt', reason='POSIX SIGTERM 무시와 SIGKILL 시험'))])
def test_native_process_is_dead_before_slot_release_after_timeout_cancel_or_crash(mode):
    async def scenario():
        context = multiprocessing.get_context('spawn')
        entered, finish = context.Event(), context.Event()
        app = create_app(runtime_factory=factory(stt=partial(BlockingSTT, entered, finish, ignore_terminate=mode == 'kill')),
            operation_timeout=0.2 if mode in ('timeout', 'kill') else 5)
        async with app.router.lifespan_context(app):
            process = app.state.runtime._process
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as http:
                task = asyncio.create_task(http.post('/internal/transcriptions', headers=headers(), content=b'audio'))
                try:
                    assert await asyncio.to_thread(entered.wait, 3)
                    assert (await asyncio.wait_for(http.get('/health/ready'), 1)).status_code == 200
                    if mode not in ('timeout', 'kill'):
                        for path, media, body in [('/internal/transcriptions', 'audio/wav', b'audio'),
                            ('/internal/speech', 'application/json', b'{"text":"test"}')]:
                            busy = await http.post(path, headers=headers(media), content=body)
                            assert busy.status_code == 503 and busy.json()['code'] == 'RUNTIME_TEMPORARILY_UNAVAILABLE'
                    if mode == 'cancel':
                        task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task
                        await app.state.cleanup_task
                    else:
                        if mode == 'crash':
                            process.terminate()
                        result = await task
                        assert result.status_code == 503 and result.headers['x-speech-completed'] == '1'
                    assert not process.is_alive() and process.exitcode is not None
                    if mode == 'kill':
                        assert process.exitcode == -9
                    assert not app.state.runtime_lock.locked() and app.state.active_task is None
                    ready = await http.get('/health/ready')
                    assert ready.status_code == 503 and not ready.json()['stt'] and not ready.json()['tts']
                finally:
                    finish.set()
    asyncio.run(scenario())


def test_asgi_disconnect_message_stops_process_even_without_cancelling_endpoint_task():
    async def scenario():
        context = multiprocessing.get_context('spawn')
        entered, finish = context.Event(), context.Event()
        app = create_app(runtime_factory=factory(stt=partial(BlockingSTT, entered, finish)))
        async with app.router.lifespan_context(app):
            process = app.state.runtime._process
            sent, received_body = [], False
            async def receive():
                nonlocal received_body
                if not received_body:
                    received_body = True
                    return {'type': 'http.request', 'body': b'audio', 'more_body': False}
                assert await asyncio.to_thread(entered.wait, 3)
                return {'type': 'http.disconnect'}
            async def send(message):
                sent.append(message)
            scope = dict(type='http', asgi={'version': '3.0'}, http_version='1.1', method='POST',
                scheme='http', path='/internal/transcriptions', raw_path=b'/internal/transcriptions', query_string=b'',
                headers=[(key.lower().encode(), value.encode()) for key, value in headers().items()])
            await asyncio.wait_for(app(scope, receive, send), 6)
            assert sent[0]['status'] == 503 and not process.is_alive() and process.exitcode is not None
            assert not app.state.runtime_lock.locked() and not any(app.state.runtime.readiness.values())
    asyncio.run(scenario())
