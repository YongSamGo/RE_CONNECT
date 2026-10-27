"""고정 내부 음성 서비스 전송. 실패 시 외부 대체·재시도·오디오 파일 저장은 없다."""

import asyncio
from collections.abc import Callable
import io
import json
import struct
from uuid import uuid4
import wave

import httpx
from pydantic import TypeAdapter, ValidationError

from app.adapters.speech import SpeechAudioTooLongError, SpeechInvalidInputError, SpeechInvalidOutputError, SpeechTimeoutError, SpeechTranscript, SpeechUnavailableError, SpeechTransientUnavailableError
from app.contracts.fields import text as contract_text

SPEECH_ORIGIN = 'http://speech:8001'
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_WAV_BYTES = 16 * 1024 * 1024
_TEXT = TypeAdapter(contract_text(2000, multiline=True))
_TYPES = {'audio/wav', 'audio/webm', 'audio/ogg', 'audio/mp4'}


def _wav(audio: bytes, *, recording: bool) -> bytes:
    """PCM을 검증하고 합성 WAV의 비음성 메타데이터는 재조립으로 제거한다."""
    try:
        if len(audio) < 44 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE' or struct.unpack_from('<I', audio, 4)[0] + 8 != len(audio):
            raise ValueError
        with wave.open(io.BytesIO(audio), 'rb') as source:
            rate, frames = source.getframerate(), source.getnframes()
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getcomptype() != 'NONE' or not 8000 <= rate <= 48000:
                raise ValueError
            if recording and rate == 16000 and frames > 90 * rate:
                raise SpeechAudioTooLongError('녹음 길이가 90초를 초과했습니다')
            if frames < 1 or frames > MAX_WAV_BYTES // 2 or recording and rate != 16000:
                raise ValueError
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError
        if recording:
            return audio
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as target:
            target.setparams((1, 2, rate, frames, 'NONE', 'not compressed'))
            target.writeframes(pcm)
        return buffer.getvalue()
    except (wave.Error, EOFError, ValueError, OSError, struct.error):
        raise SpeechInvalidOutputError('음성 파일의 PCM 형식을 확인하지 못했습니다') from None


class InternalSpeechAdapter:
    def __init__(self, *, timeout_seconds: float = 60, ready_timeout_seconds: float = 2, transport: httpx.AsyncBaseTransport | None = None):
        if not 0 < timeout_seconds <= 60 or not 0 < ready_timeout_seconds <= 2:
            raise ValueError('음성 요청 제한시간 범위를 확인해 주세요')
        self.timeout, self.ready_timeout, self.transport = timeout_seconds, ready_timeout_seconds, transport

    def _client(self, timeout):
        return httpx.AsyncClient(base_url=SPEECH_ORIGIN, transport=self.transport, timeout=timeout, follow_redirects=False,
            trust_env=False, headers={'Accept-Encoding': 'identity'})

    @staticmethod
    def media_type(content_type):
        if not isinstance(content_type, str):
            raise SpeechInvalidInputError('허용한 음성 형식이 아닙니다')
        media = content_type.split(';', 1)[0].strip().lower()
        if media not in _TYPES:
            raise SpeechInvalidInputError('허용한 음성 형식이 아닙니다')
        return media

    def validate_transcription(self, audio: bytes, *, content_type: str) -> None:
        media = self.media_type(content_type)
        if type(audio) is not bytes or not 1 <= len(audio) <= MAX_AUDIO_BYTES:
            raise SpeechInvalidInputError('녹음 크기를 확인해 주세요')
        if media == 'audio/wav':
            try:
                _wav(audio, recording=True)
            except SpeechInvalidOutputError:
                raise SpeechInvalidInputError('녹음 WAV 형식이나 길이를 확인해 주세요') from None
        elif not ((media == 'audio/webm' and audio.startswith(b'\x1aE\xdf\xa3'))
            or (media == 'audio/ogg' and audio.startswith(b'OggS\x00'))
            or (media == 'audio/mp4' and len(audio) >= 12 and audio[4:8] == b'ftyp')):
            raise SpeechInvalidInputError('녹음 시그니처를 확인해 주세요')
        # 압축 음성의 실제 codec/길이/무음은 #31 내부 디코더가 추론 전에 검사해야 한다.

    def validate_synthesis(self, text: str) -> None:
        try:
            _TEXT.validate_python(text)
        except ValidationError:
            raise SpeechInvalidInputError('읽을 문장을 확인해 주세요') from None

    async def _request(self, method, path, *, maximum, request_id=None, on_runtime_ended=None, **kwargs):
        try:
            async with self._client(self.ready_timeout if method == 'GET' else self.timeout) as client:
                async with client.stream(method, path, **kwargs) as response:
                    if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                        raise SpeechInvalidOutputError('압축된 내부 음성 응답은 허용하지 않습니다')
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if len(body) + len(chunk) > maximum:
                            raise SpeechInvalidOutputError('음성 응답 크기를 초과했습니다')
                        body.extend(chunk)
                    terminal = request_id is not None and response.headers.get('X-Speech-Request-ID') == request_id and response.headers.get('X-Speech-Completed') == '1'
                    if terminal and on_runtime_ended is not None:
                        on_runtime_ended()
                    if response.status_code != 200:
                        if response.status_code == 503 and terminal and response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() == 'application/json':
                            try:
                                transient = json.loads(body) == {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}
                            except (ValueError, TypeError):
                                transient = False
                            if transient:
                                raise SpeechTransientUnavailableError('내부 음성 서비스가 일시적으로 준비되지 않았습니다')
                        if response.status_code == 422 and terminal:
                            try:
                                error = json.loads(body)
                            except (ValueError, TypeError):
                                error = None
                            if error == {'code': 'AUDIO_TOO_LONG'}:
                                raise SpeechAudioTooLongError('녹음 길이가 90초를 초과했습니다')
                            if error == {'code': 'AUDIO_INVALID'}:
                                raise SpeechInvalidInputError('녹음 형식을 확인해 주세요')
                        raise SpeechUnavailableError('내부 음성 서비스가 요청을 처리하지 못했습니다')
                    if method != 'GET' and not terminal:
                        raise SpeechInvalidOutputError('현재 음성 연산의 종료를 확인하지 못했습니다')
                    return bytes(body), response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # 연결이 성립되지 않아 이 시도의 요청/추론은 시작하지 않았다.
            if on_runtime_ended is not None:
                on_runtime_ended()
            raise SpeechTransientUnavailableError('내부 음성 서비스에 연결하지 못했습니다') from None
        except (TimeoutError, httpx.TimeoutException):
            raise SpeechTimeoutError('음성 응답 시간이 초과되었습니다') from None
        except httpx.RequestError:
            raise SpeechUnavailableError('내부 음성 서비스에 연결하지 못했습니다') from None

    async def is_ready(self) -> bool:
        try:
            raw, media = await asyncio.wait_for(self._request('GET', '/health/ready', maximum=4096), self.ready_timeout)
            if media != 'application/json':
                return False
            data = json.loads(raw)
            return data == {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': True} and type(data.get('protocol_version')) is int and type(data.get('stt')) is bool and type(data.get('tts')) is bool
        except (SpeechUnavailableError, SpeechInvalidOutputError, SpeechTimeoutError, TimeoutError, ValueError, TypeError):
            return False

    async def transcribe(self, audio: bytes, *, content_type: str, on_runtime_ended: Callable[[], None] | None = None) -> SpeechTranscript:
        self.validate_transcription(audio, content_type=content_type)
        request_id = str(uuid4())
        raw, media = await self._timed_request('POST', '/internal/transcriptions', maximum=32768,
            request_id=request_id, on_runtime_ended=on_runtime_ended, content=audio,
            headers={'Content-Type': self.media_type(content_type), 'X-Speech-Request-ID': request_id})
        try:
            if media != 'application/json':
                raise ValueError
            return SpeechTranscript.model_validate_json(raw)
        except (ValidationError, ValueError):
            raise SpeechInvalidOutputError('전사 응답 형식을 확인하지 못했습니다') from None

    async def synthesize(self, text: str, *, on_runtime_ended: Callable[[], None] | None = None) -> bytes:
        self.validate_synthesis(text)
        request_id = str(uuid4())
        raw, media = await self._timed_request('POST', '/internal/speech', maximum=MAX_WAV_BYTES,
            request_id=request_id, on_runtime_ended=on_runtime_ended, json={'text': _TEXT.validate_python(text)},
            headers={'X-Speech-Request-ID': request_id})
        if media != 'audio/wav':
            raise SpeechInvalidOutputError('합성 음성 형식을 확인하지 못했습니다')
        return _wav(raw, recording=False)

    async def _timed_request(self, *args, **kwargs):
        try:
            return await asyncio.wait_for(self._request(*args, **kwargs), self.timeout)
        except TimeoutError:
            raise SpeechTimeoutError('음성 응답 시간이 초과되었습니다') from None
