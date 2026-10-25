"""SEC-02: 회원 구현과 음성 구현의 주체/동의 경계를 통합할 때의 회귀."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.business_errors import AppError
from app.modules.admission.service import InferenceIdentity
from app.modules.sessions.service import Session
from app.modules.speech.service import SpeechService
from app.modules.transcriptions.service import TranscriptionService


@pytest.mark.parametrize('member', [False, True])
def test_matched_speech_actor_uses_the_current_member_consent_generation(member):
    async def scenario():
        owner = uuid4() if member else None
        session = Session(uuid4(), 1, 1, 1, '0' * 64, '1' * 64, owner, 7 if member else None)
        consents = SimpleNamespace(require=AsyncMock(side_effect=AppError('CONSENT_REQUIRED')))
        service = SpeechService(None, None, None, consents, None, None)
        with pytest.raises(AppError, match='CONSENT_REQUIRED'):
            await service.read(session, InferenceIdentity(session.subject_id, '192.0.2.1', owner), str(uuid4()), None)
        actor, purpose = consents.require.call_args.args
        assert purpose == 'ai_processing'
        assert actor.member_id == owner and actor.member_generation == session.user_generation
        assert actor.session_digest == session.digest
    asyncio.run(scenario())


def test_matching_member_transcription_reaches_owned_journey_verification():
    async def scenario():
        owner = uuid4()
        session = Session(uuid4(), 1, 1, 1, '0' * 64, '1' * 64, owner, 7)
        journeys = SimpleNamespace(load=AsyncMock(side_effect=AppError('CONSENT_REQUIRED')))
        service = TranscriptionService(None, journeys, None)
        journey = uuid4()
        with pytest.raises(AppError, match='CONSENT_REQUIRED'):
            await service.create(session, InferenceIdentity(session.subject_id, '192.0.2.1', owner), journey, str(uuid4()), b'', 'audio/wav')
        journeys.load.assert_awaited_once_with(session, journey)
    asyncio.run(scenario())


@pytest.mark.parametrize('operation', ['read', 'transcribe'])
def test_foreign_account_identity_is_rejected_before_dependency_access(operation):
    async def scenario():
        session = Session(uuid4(), 1, 1, 1, '0' * 64, '1' * 64, uuid4(), 7)
        identity = InferenceIdentity(session.subject_id, '192.0.2.1', uuid4())
        with pytest.raises(AppError, match='NOT_FOUND'):
            if operation == 'read':
                await SpeechService(None, None, None, None, None, None).read(session, identity, str(uuid4()), None)
            else:
                await TranscriptionService(None, None, None).create(session, identity, uuid4(), str(uuid4()), b'', 'audio/wav')
    asyncio.run(scenario())
