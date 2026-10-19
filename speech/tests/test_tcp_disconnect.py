"""실제 loopback socket의 연결 해제. 모델은 spawn 대역으로 분리한다."""

import asyncio
from functools import partial
import multiprocessing
import socket
import threading
import time
from uuid import uuid4

import httpx
import pytest
import uvicorn

from app.process_runtime import ProcessRuntime
from app.service import create_app
from process_fixtures import BlockingSTT, TTS


def test_real_tcp_disconnect_stops_native_process_without_cancelling_asgi_task():
    context = multiprocessing.get_context('spawn')
    entered, finish = context.Event(), context.Event()
    app = create_app(runtime_factory=lambda: ProcessRuntime(stt_loader=partial(BlockingSTT, entered, finish), tts_loader=TTS))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.01)
        process = app.state.runtime._process
        async def scenario():
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=10) as http:
                task = asyncio.create_task(http.post('/internal/transcriptions', content=b'audio',
                    headers={'Content-Type': 'audio/wav', 'X-Speech-Request-ID': str(uuid4())}))
                assert await asyncio.to_thread(entered.wait, 3)
                task.cancel()  # TCP client만 취소한다. 서버 ASGI task의 cancel()은 호출하지 않는다.
                with pytest.raises(asyncio.CancelledError):
                    await task
                deadline = time.monotonic() + 5
                while process.is_alive():
                    assert time.monotonic() < deadline
                    await asyncio.sleep(.01)
                ready = await http.get('/health/ready')
                assert ready.status_code == 503 and ready.json()['stt'] is False and ready.json()['tts'] is False
                assert process.exitcode is not None
        asyncio.run(scenario())
    finally:
        server.should_exit = True
        thread.join(8)
        listener.close()
        assert not thread.is_alive()
