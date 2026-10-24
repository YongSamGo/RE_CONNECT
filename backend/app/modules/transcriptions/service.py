"""전사는 자동 사실 추출과 분리한다. 원본 오디오를 결과 저장소로 보내지 않는다."""

import asyncio
import hashlib
from uuid import UUID

from app.adapters.speech import SpeechAudioTooLongError, SpeechInvalidInputError, SpeechInvalidOutputError, SpeechTimeoutError, SpeechUnavailableError
from app.contracts.journey import Transcription
from app.core.business_errors import AppError
from app.modules.requests.service import input_fingerprint

TRANSCRIPTION_TIMEOUT_SECONDS = 60


class AudioInputProblem(Exception):
    def __init__(self, error):
        self.reason = 'out_of_range' if isinstance(error, SpeechAudioTooLongError) else 'invalid_value'
        super().__init__('녹음의 형식이나 길이를 확인해 주세요')


class TranscriptionService:
    def __init__(self, store, journeys, speech):
        self.store, self.journeys, self.speech = store, journeys, speech

    async def require(self, session, journey, transcription_id):
        record = await self.journeys.load(session, journey)
        return await self.store.read(session, journey, transcription_id, record.guard.ai_notice_version)

    async def create(self, session, identity, journey, key, audio, content_type):
        if identity.subject_id != session.subject_id or identity.account_id != session.user_id:
            raise AppError('NOT_FOUND')
        record = await self.journeys.load(session, journey)
        try:
            self.speech.validate_transcription(audio, content_type=content_type)
        except SpeechInvalidInputError as error:
            raise AudioInputProblem(error) from None
        try:
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError('VALIDATION_FAILED') from None
        media = content_type.split(';', 1)[0].strip().lower()
        digest = input_fingerprint({'audio_sha256': hashlib.sha256(audio).hexdigest(), 'content_type': media})
        permit = await self.store.begin(session, journey, key_id, digest, record.view.revision, record.guard.ai_notice_version)
        if isinstance(permit, Transcription):
            return permit
        try:
            async with asyncio.timeout(TRANSCRIPTION_TIMEOUT_SECONDS):
                transcript = await self.speech.transcribe(audio, content_type=media, identity=identity)
            result = Transcription(transcription_id=permit.transcription_id, text=transcript.text, duration_seconds=transcript.duration_seconds)
            return await self.store.complete(session, journey, permit, result)
        except BaseException as error:
            try:
                await asyncio.shield(self.store.cancel(session, journey, permit))
            except AppError:
                pass
            if isinstance(error, (TimeoutError, SpeechTimeoutError)):
                raise AppError('AI_TIMEOUT') from None
            if isinstance(error, (SpeechUnavailableError, SpeechInvalidOutputError)):
                raise AppError('MODEL_UNAVAILABLE') from None
            if isinstance(error, SpeechInvalidInputError):
                raise AudioInputProblem(error) from None
            raise
