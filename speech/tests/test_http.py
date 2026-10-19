import asyncio
import threading
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audio import AudioRejected, MAX_UPLOAD
from app.main import create_app
from app.stt import Transcript


def headers():
    return {'Content-Type': 'audio/wav', 'X-Speech-Request-ID': str(uuid4())}


class Runner:
    def transcribe(self, data, media):
        assert media == 'audio/wav'
        return Transcript('가상 시험 응답', 1.0)


def test_owned_job_terminal_headers_and_readiness_do_not_claim_tts_is_loaded():
    with TestClient(create_app(loader=Runner)) as http:
        ready = http.get('/health/ready')
        assert ready.status_code == 503 and ready.json()['stt'] is True and ready.json()['tts'] is False
        request_headers = headers()
        result = http.post('/internal/transcriptions', headers=request_headers, content=b'audio')
        assert result.status_code == 200 and set(result.json()) == {'text', 'duration_seconds'}
        assert result.headers['x-speech-request-id'] == request_headers['X-Speech-Request-ID']
        assert result.headers['x-speech-completed'] == '1' and result.headers['cache-control'] == 'no-store'
        assert http.get('/docs').status_code == 404
        assert http.post('/internal/speech', headers=headers()).json() == {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}


def test_input_size_content_type_and_job_id_fail_before_inference():
    class MustNotRun:
        def transcribe(self, *args):
            pytest.fail('inference must not run')
    with TestClient(create_app(loader=MustNotRun)) as http:
        for request_headers, body in [({}, b'audio'), ({**headers(), 'Content-Type': 'text/plain'}, b'not audio'),
            (headers(), b'x' * (MAX_UPLOAD + 1))]:
            result = http.post('/internal/transcriptions', headers=request_headers, content=body)
            assert result.status_code == 422


@pytest.mark.parametrize('error,code,status', [(AudioRejected('AUDIO_TOO_LONG'), 'AUDIO_TOO_LONG', 422),
    (AudioRejected(), 'AUDIO_INVALID', 422), (ValueError('private input'), 'RUNTIME_UNAVAILABLE', 503)])
def test_worker_error_is_fixed_and_terminal_only_after_actual_worker_returns(error, code, status):
    class Broken:
        def transcribe(self, *args):
            raise error
    with TestClient(create_app(loader=Broken)) as http:
        result = http.post('/internal/transcriptions', headers=headers(), content=b'audio')
        assert result.status_code == status and result.json() == {'code': code}
        assert result.headers['x-speech-completed'] == '1'
        assert not http.app.state.runtime_lock.locked()


@pytest.mark.parametrize('mode', ['timeout', 'cancel'])
def test_native_worker_keeps_busy_after_request_timeout_or_cancellation_until_real_end(mode):
    async def scenario():
        entered, finish = threading.Event(), threading.Event()
        calls = []
        class Blocking:
            def transcribe(self, *args):
                calls.append(1)
                entered.set()
                assert finish.wait(5)
                return Transcript('가상 시험 응답', 1.0)
        app = create_app(loader=Blocking, operation_timeout=0.05)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as http:
                task = asyncio.create_task(http.post('/internal/transcriptions', headers=headers(), content=b'audio'))
                try:
                    assert await asyncio.to_thread(entered.wait, 3)
                    if mode == 'cancel':
                        task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task
                    else:
                        result = await task
                        assert result.status_code == 503 and 'x-speech-completed' not in result.headers
                    assert app.state.runtime_lock.locked()
                    busy = await http.post('/internal/transcriptions', headers=headers(), content=b'audio')
                    assert busy.status_code == 503 and busy.json()['code'] == 'RUNTIME_TEMPORARILY_UNAVAILABLE'
                    assert busy.headers['x-speech-completed'] == '1' and len(calls) == 1
                    worker = app.state.active_task
                    finish.set()
                    await worker
                    await asyncio.sleep(0)
                    assert not app.state.runtime_lock.locked() and app.state.active_task is None
                finally:
                    finish.set()
    asyncio.run(scenario())
