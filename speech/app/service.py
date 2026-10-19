"""STT/TTS 공통 프로세스와 내부 HTTP 수명. 원문을 파일/로그로 내보내지 않는다."""

import asyncio
from contextlib import asynccontextmanager, suppress
import json
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.requests import ClientDisconnect

from app.audio import FORMATS, MAX_UPLOAD
from app.process_runtime import ProcessRuntime, erase
from app.tts import TextRejected, validate_text


class InputRejected(Exception):
    pass


class WavResponse(Response):
    def __init__(self, audio, headers, finished):
        self.audio, self.finished = audio, finished
        super().__init__(memoryview(audio), media_type='audio/wav', headers=headers)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.body.release()
            self.body = b''
            erase(self.audio)
            self.finished()


async def bounded_body(request, maximum):
    body = bytearray()
    try:
        if request.headers.get('Content-Encoding', 'identity').lower() != 'identity':
            raise InputRejected()
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise InputRejected()
                body.extend(chunk)
        return body
    except (TimeoutError, RuntimeError, ClientDisconnect, InputRejected):
        erase(body)
        raise InputRejected() from None
    except BaseException:
        erase(body)
        raise


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputRejected()
        result[key] = value
    return result


def create_app(*, runtime_factory=ProcessRuntime, operation_timeout=50.0):
    # 추가5초는 프로세스 종료 확인과 부모 IPC thread 배출에 사용한다.
    if not 0 < operation_timeout <= 50:
        raise ValueError('음성 연산 제한시간 범위 오류')

    @asynccontextmanager
    async def lifespan(app):
        runtime = runtime_factory()
        app.state.runtime = runtime
        startup = asyncio.create_task(asyncio.to_thread(runtime.start))
        try:
            await asyncio.shield(startup)
            yield
        finally:
            stopped = await asyncio.to_thread(runtime.stop)
            try:
                await asyncio.wait_for(asyncio.shield(startup), 1)
            except TimeoutError:
                stopped = False
            cleanup = app.state.cleanup_task
            if cleanup is not None:
                await asyncio.shield(cleanup)
            task = app.state.active_task
            if task is not None:
                try:
                    outcome = await asyncio.wait_for(asyncio.shield(task), 1)
                    erase(outcome.value)
                except TimeoutError:
                    stopped = False
            if not stopped:
                raise RuntimeError('음성 프로세스의 종료를 확인하지 못했습니다')

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = None
    app.state.runtime_lock = asyncio.Lock()
    app.state.active_task = app.state.cleanup_task = None

    def headers(job, ended=True):
        result = {'Cache-Control': 'no-store'}
        if job is not None:
            result['X-Speech-Request-ID'] = job
            if ended:
                result['X-Speech-Completed'] = '1'
        return result

    def reply(job, status, code, *, ended=True):
        return JSONResponse({'code': code}, status_code=status, headers=headers(job, ended))

    def request_id(request):
        values = request.headers.getlist('X-Speech-Request-ID')
        if len(values) != 1:
            return None
        try:
            value = str(UUID(values[0]))
            return value if value == values[0] else None
        except (ValueError, TypeError, AttributeError):
            return None

    def release(task):
        if app.state.active_task is task:
            app.state.active_task = None
            app.state.runtime_lock.release()

    async def abort(task, value):
        ended = await asyncio.to_thread(app.state.runtime.stop)
        try:
            outcome = await asyncio.wait_for(asyncio.shield(task), 1)
            erase(outcome.value)
        except TimeoutError:
            def late(future):
                erase(future.result().value)
                erase(value)
            task.add_done_callback(late)
            return False
        erase(value)
        if ended:
            release(task)
        return ended

    async def disconnected(request):
        try:
            while True:
                if (await request.receive())['type'] == 'http.disconnect':
                    return
        except Exception:
            return  # 수신 상태가 불명확해도 이미 시작한 연산을 계속 두지 않는다.

    async def perform(job, kind, value, media=None, *, deadline, request):
        runtime, lock = app.state.runtime, app.state.runtime_lock
        if runtime is None or not runtime.readiness[kind] or lock.locked():
            erase(value)
            return reply(job, 503, 'RUNTIME_TEMPORARILY_UNAVAILABLE')
        remaining = min(operation_timeout, deadline - asyncio.get_running_loop().time() - 5)
        if remaining <= 0:
            erase(value)
            return reply(job, 503, 'RUNTIME_TEMPORARILY_UNAVAILABLE')
        await lock.acquire()
        task = asyncio.create_task(asyncio.to_thread(runtime.execute, kind, value, media))
        disconnect = asyncio.create_task(disconnected(request))
        app.state.active_task = task
        try:
            done, _ = await asyncio.wait({task, disconnect}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            if disconnect in done or task not in done:
                raise TimeoutError
            outcome = task.result()
        except (TimeoutError, asyncio.CancelledError) as error:
            cleanup = asyncio.create_task(abort(task, value))
            app.state.cleanup_task = cleanup
            if isinstance(error, asyncio.CancelledError):
                raise
            ended = await asyncio.shield(cleanup)
            return reply(job, 503, 'RUNTIME_UNAVAILABLE', ended=ended)
        finally:
            disconnect.cancel()
            with suppress(asyncio.CancelledError):
                await disconnect
        erase(value)
        if outcome.code is not None:
            if outcome.ended:
                release(task)
            return reply(job, 422 if outcome.code in ('AUDIO_INVALID', 'AUDIO_TOO_LONG', 'TEXT_INVALID') else 503,
                outcome.code, ended=outcome.ended)
        if kind == 'tts':
            # 실제 모델/IPC 원본 정리 ACK 후 응답한다. 부모의 전송 버퍼는 send 후 비운다.
            return WavResponse(outcome.value, headers(job), lambda: release(task))
        release(task)
        return JSONResponse({'text': outcome.value.text, 'duration_seconds': outcome.value.duration_seconds}, headers=headers(job))

    @app.get('/health/ready')
    async def ready():
        runtime = app.state.runtime
        loaded = runtime.readiness if runtime is not None else {'stt': False, 'tts': False}
        ready = all(loaded.values())
        return JSONResponse({'protocol_version': 1, 'status': 'ready' if ready else 'not_ready', **loaded},
            status_code=200 if ready else 503, headers=headers(None))

    @app.post('/internal/transcriptions')
    async def transcribe(request: Request):
        deadline = asyncio.get_running_loop().time() + 55
        job = request_id(request)
        media = request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if job is None or media not in FORMATS:
            return reply(job, 422, 'AUDIO_INVALID')
        try:
            body = await bounded_body(request, MAX_UPLOAD)
        except InputRejected:
            return reply(job, 422, 'AUDIO_INVALID')
        return await perform(job, 'stt', body, media, deadline=deadline, request=request)

    @app.post('/internal/speech')
    async def synthesize(request: Request):
        deadline = asyncio.get_running_loop().time() + 55
        job = request_id(request)
        media = request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if job is None or media != 'application/json':
            return reply(job, 422, 'TEXT_INVALID')
        body = None
        try:
            # 2000자 전부가 JSON surrogate escape로 표현돼도 받을 수 있다.
            body = await bounded_body(request, 32768)
            data = json.loads(body.decode('utf-8'), object_pairs_hook=unique_object)
            if type(data) is not dict or set(data) != {'text'}:
                raise InputRejected()
            validate_text(data['text'])
        except (InputRejected, TextRejected, ValueError, UnicodeError, RecursionError):
            return reply(job, 422, 'TEXT_INVALID')
        finally:
            erase(body)
        return await perform(job, 'tts', data['text'], deadline=deadline, request=request)

    return app
