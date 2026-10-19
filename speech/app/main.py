"""Compose 내부 전용 HTTP. docs/파일 업로드 스풀/사용자 모델 선택을 제공하지 않는다."""

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from app.audio import AudioRejected, FORMATS, MAX_UPLOAD
from app.stt import LocalSTT, ModelFailure


def create_app(*, loader=LocalSTT.load, operation_timeout=55.0):
    if not 0 < operation_timeout <= 55:
        raise ValueError('음성 연산 제한시간 범위 오류')

    @asynccontextmanager
    async def lifespan(app):
        try:
            app.state.stt = await asyncio.to_thread(loader)
        except Exception:
            app.state.stt = None
        yield
        task = app.state.active_task
        if task is not None:
            try:
                await asyncio.shield(task)
            except Exception:
                app.state.stt = None  # 실패한 런타임을 재사용하지 않고 원문/외부 오류는 기록하지 않는다.
        app.state.stt = None

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.stt = None
    app.state.runtime_lock = asyncio.Lock()
    app.state.active_task = None

    def reply(request_id, status, body, *, ended=True):
        headers = {'Cache-Control': 'no-store'}
        if request_id is not None:
            headers['X-Speech-Request-ID'] = request_id
            if ended:
                headers['X-Speech-Completed'] = '1'
        return JSONResponse(body, status_code=status, headers=headers)

    def request_id(request):
        values = request.headers.getlist('X-Speech-Request-ID')
        if len(values) != 1:
            return None
        try:
            value = str(UUID(values[0]))
            return value if value == values[0] else None
        except (ValueError, TypeError, AttributeError):
            return None

    @app.get('/health/ready')
    async def ready():
        # TTS 적재는 후속 작업이다. STT만 적재하고 전체 준비 성공으로 표시하지 않는다.
        return reply(None, 503, {'protocol_version': 1, 'status': 'not_ready',
            'stt': app.state.stt is not None, 'tts': False})

    @app.post('/internal/transcriptions')
    async def transcribe(request: Request):
        job = request_id(request)
        if job is None:
            return reply(None, 422, {'code': 'AUDIO_INVALID'})
        media = request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if media not in FORMATS:
            return reply(job, 422, {'code': 'AUDIO_INVALID'})
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_UPLOAD:
                        return reply(job, 422, {'code': 'AUDIO_INVALID'})
                    body.extend(chunk)
        except (TimeoutError, RuntimeError, ClientDisconnect):
            return reply(job, 422, {'code': 'AUDIO_INVALID'})
        lock = app.state.runtime_lock
        if app.state.stt is None or lock.locked():
            return reply(job, 503, {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'})
        await lock.acquire()
        # shield + done callback: HTTP task 취소/시간 초과로 native thread의 종료를 가장하지 않는다.
        task = asyncio.create_task(asyncio.to_thread(app.state.stt.transcribe, bytes(body), media))
        app.state.active_task = task
        body.clear()
        def finished(future):
            if not future.cancelled():
                future.exception()  # 연결이 떠난 뒤 발생한 오류도 본문/traceback을 로깅하지 않는다.
                lock.release()
                if app.state.active_task is future:
                    app.state.active_task = None
        task.add_done_callback(finished)
        try:
            result = await asyncio.wait_for(asyncio.shield(task), operation_timeout)
            return reply(job, 200, {'text': result.text, 'duration_seconds': result.duration_seconds})
        except AudioRejected as error:
            return reply(job, 422, {'code': error.code})
        except ModelFailure:
            return reply(job, 503, {'code': 'RUNTIME_UNAVAILABLE'})
        except TimeoutError:
            # 작업이 끝났는지 알 수 없으므로 종료 헤더를 보내지 않는다.
            return reply(job, 503, {'code': 'RUNTIME_UNAVAILABLE'}, ended=False)
        except Exception:
            return reply(job, 503, {'code': 'RUNTIME_UNAVAILABLE'})

    @app.post('/internal/speech')
    async def speech_unavailable(request: Request):
        job = request_id(request)
        return reply(job, 503, {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'})

    return app


app = create_app()
