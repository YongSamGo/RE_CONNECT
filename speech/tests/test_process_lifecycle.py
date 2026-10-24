import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.process_runtime import Outcome, ProcessRuntime
from app.service import WavResponse, bounded_body, create_app, InputRejected


def test_unconfirmed_process_death_preserves_handle_and_never_reports_stopped():
    attempts = []
    class Alive:
        pid = 123
        def is_alive(self):
            return True
        def terminate(self):
            attempts.append('terminate')
        def kill(self):
            attempts.append('kill')
        def join(self, timeout):
            attempts.append(('join', timeout))
    runtime = ProcessRuntime()
    process = runtime._process = Alive()
    assert runtime.stop() is False and runtime._process is process
    assert attempts == ['terminate', ('join', 2), 'kill', ('join', 2)]
    assert runtime.readiness == {'stt': False, 'tts': False}


def test_stop_before_start_does_not_start_a_late_model_process():
    runtime = ProcessRuntime()
    assert runtime.stop()
    runtime.start()
    assert runtime._process is None and not any(runtime.readiness.values())


def test_missing_cleanup_ack_erases_received_wav_and_does_not_claim_completion(monkeypatch):
    runtime = ProcessRuntime()
    messages = iter([b'{"wav":true}', b'private-wave', b'wrong-ack'])
    runtime._connection = SimpleNamespace(send_bytes=lambda value: None, recv_bytes=lambda limit: next(messages))
    runtime._process = SimpleNamespace(is_alive=lambda: True)
    runtime._loaded = {'stt': True, 'tts': True}
    monkeypatch.setattr(runtime, 'stop', lambda: False)
    result = runtime.execute('tts', 'public text')
    assert result.value is None and result.code == 'RUNTIME_UNAVAILABLE' and result.ended is False


def test_unknown_end_has_no_terminal_header_and_retains_lock():
    class Unknown:
        readiness = {'stt': True, 'tts': True}
        def start(self):
            pass
        def stop(self):
            return True
        def execute(self, *args):
            self.readiness = {'stt': False, 'tts': False}
            return Outcome(code='RUNTIME_UNAVAILABLE', ended=False)
    with TestClient(create_app(runtime_factory=Unknown)) as http:
        result = http.post('/internal/speech', json={'text': '공개 가상 문장'},
            headers={'X-Speech-Request-ID': '00000000-0000-0000-0000-000000000001'})
        assert result.status_code == 503 and 'x-speech-completed' not in result.headers
        assert http.app.state.runtime_lock.locked()


@pytest.mark.parametrize('mode', ['success', 'disconnect'])
def test_response_audio_is_erased_after_send_or_disconnect(mode):
    async def scenario():
        audio, finished = bytearray(b'public synthetic wav'), []
        response = WavResponse(audio, {}, lambda: finished.append(True))
        async def send(message):
            if message['type'] == 'http.response.body':
                assert bytes(message['body']) == b'public synthetic wav'
                if mode == 'disconnect':
                    raise asyncio.CancelledError
        if mode == 'disconnect':
            with pytest.raises(asyncio.CancelledError):
                await response({'type': 'http'}, None, send)
        else:
            await response({'type': 'http'}, None, send)
        assert not any(audio) and finished == [True] and response.body == b''
    asyncio.run(scenario())


def test_body_overflow_and_client_disconnect_reject_before_model():
    async def scenario():
        for disconnect in (False, True):
            async def stream():
                yield b'public'
                if disconnect:
                    raise RuntimeError('input disconnected')
                yield b'too long'
            request = SimpleNamespace(headers={}, stream=stream)
            with pytest.raises(InputRejected):
                await bounded_body(request, 8)
    asyncio.run(scenario())
