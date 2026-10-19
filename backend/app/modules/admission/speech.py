"""STT·TTS도 LLM과 같은 전역 슬롯·일일 예산을 먼저 요구한다."""

from app.core.business_errors import AppError


class ControlledSpeechAdapter:
    def __init__(self, runtime, admission):
        self._runtime, self._admission = runtime, admission

    async def is_ready(self) -> bool:
        return await self._admission.is_ready() and await self._runtime.is_ready()

    async def transcribe(self, audio, *, content_type, identity=None):
        if identity is None:
            raise AppError('SERVICE_UNAVAILABLE')
        self._runtime.validate_transcription(audio, content_type=content_type)
        return await self._admission.run(identity, 'stt', lambda completion: self._runtime.transcribe(audio,
            content_type=content_type, on_runtime_ended=completion.confirm_ended))

    async def synthesize(self, text, *, identity=None):
        if identity is None:
            raise AppError('SERVICE_UNAVAILABLE')
        self._runtime.validate_synthesis(text)
        return await self._admission.run(identity, 'tts', lambda completion: self._runtime.synthesize(text,
            on_runtime_ended=completion.confirm_ended))
