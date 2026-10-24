"""FastAPI 앱 조립.

실행: `backend/`에서 `python -m app`. 테스트는 `create_app()`에 가짜 구성 요소를 넘겨 만든다.
구체 구현(DB·Redis·Ollama·음성 서비스)은 여기서만 고르고, 모듈은 Protocol로 받는다.
"""

from collections.abc import Mapping
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI

from app.adapters.ollama import OllamaLLMAdapter
from app.adapters.kakao import KakaoAdapter
from app.adapters.internal_speech import InternalSpeechAdapter
from app.adapters.redis import RedisProbe, build_redis
from app.core.config import Settings, get_settings
from app.core.errors import UnhandledErrorMiddleware, register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.core.safe_logging import RequestLogMiddleware
from app.modules.operations import router as operations
from app.modules.operations.readiness import (
    COMPONENTS,
    Component,
    NotConfiguredProbe,
    ReadinessProbe,
    ReadinessService,
)
from app.modules.regions import router as regions
from app.modules.consents import router as consents
from app.modules.consents.repository import RedisConsentStore, SQLConsentStore, RoutedConsentStore
from app.modules.consents.service import ConsentService, UnavailableConsentStore
from app.modules.consents.notices import published_catalog
from app.modules.sessions import router as sessions
from app.modules.auth import router as auth
from app.modules.auth.service import OAuthService, UnavailableFlowStore
from app.modules.auth.repository import RedisFlowStore
from app.modules.auth.accounts import SqlAccountRepository, UnavailableAccountRepository
from app.modules.auth.member_store import RedisMemberStore, UnavailableMemberStore
from app.modules.auth.members import MemberService
from app.modules.auth.member_cleanup import RedisMemberCleanup, UnavailableMemberCleanup
from app.modules.deletions import router as deletions
from app.modules.deletions.journal import FileDeletionJournal, UnavailableDeletionJournal
from app.modules.deletions.repository import SqlDeletionRepository, UnavailableDeletionRepository
from app.modules.deletions.service import DeletionService
from app.core.encryption import ContentCipher, EncryptionKeyRing, EncryptionUnavailable
from app.modules.saved_profiles import router as saved_profiles
from app.modules.saved_profiles.repository import SqlProfileRepository
from app.modules.saved_profiles.service import SavedProfileService
from app.modules.saved_drafts import router as saved_drafts
from app.modules.saved_drafts.repository import SqlDraftRepository
from app.modules.saved_drafts.service import SavedDraftService
from app.modules.save_intents import router as save_intents
from app.modules.save_intents.repository import RedisSaveIntentStore, UnavailableSaveIntentStore
from app.modules.save_intents.service import SaveIntentService
from app.modules.save_intents.policy import SqlSaveIntentPolicy, UnavailableSaveIntentPolicy
from app.core.business_errors import AppError
from sqlalchemy.orm import sessionmaker
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import SessionService, UnavailableSessionStore
from app.modules.sessions.middleware import RequestSecurityMiddleware
from app.modules.requests.repository import RedisRequestStore
from app.modules.requests.service import RequestService, UnavailableRequestStore
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.speech import ControlledSpeechAdapter
from app.modules.admission.repository import RedisAdmissionStore
from app.modules.admission.service import AdmissionService, UnavailableAdmissionService
from app.modules.opportunities import router as opportunities
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService, UnavailableOpportunityRepository
from app.modules.opportunities.ingestion import IngestionService, UnavailableIngestionRepository
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.modules.journeys import router as journeys
from app.modules.journeys.repository import RedisJourneyStore
from app.modules.journeys.service import JourneyService, UnavailableJourneyStore
from app.modules.journeys.messages import JourneyMessageService
from app.modules.eligibility import router as eligibility
from app.modules.eligibility.service import EligibilityService
from app.modules.roles import router as roles
from app.modules.roles.repository import SQLRoleCatalog, UnavailableRoleCatalog
from app.modules.roles.service import RoleService
from app.modules.recommendations import router as recommendations
from app.modules.recommendations.service import RecommendationService
from app.modules.drafts import router as drafts
from app.modules.drafts.repository import RedisDraftStore, UnavailableDraftStore
from app.modules.drafts.service import DraftService
from app.modules.transcriptions.repository import RedisTranscriptionStore, UnavailableTranscriptionStore
from app.modules.transcriptions.service import TranscriptionService
from app.modules.speech import router as speech
from app.modules.speech.service import SpeechService
from app.persistence.connection import DatabaseProbe, build_engine

API_PREFIX = "/api/v1"


def build_llm_adapter(settings: Settings) -> OllamaLLMAdapter:
    return OllamaLLMAdapter(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        num_predict=settings.ollama_num_predict,
        num_ctx=settings.ollama_num_ctx,
        think=settings.ollama_think,
        max_response_bytes=settings.ollama_max_response_bytes,
        ready_timeout_seconds=settings.health_check_timeout_seconds,
    )


def create_app(
    settings: Settings | None = None,
    readiness_probes: Mapping[Component, ReadinessProbe] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    docs_enabled = settings.docs_enabled
    notice_catalog = published_catalog(settings)

    engine = build_engine(settings) if settings.database_url is not None else None
    redis_client = build_redis(settings) if settings.redis_url is not None else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if redis_client is not None:
                await redis_client.aclose()
            if engine is not None:
                await asyncio.to_thread(engine.dispose)

    app = FastAPI(
        title="다시잇다 API",
        lifespan=lifespan,
        # 운영에서는 API 문서 화면과 스키마를 열지 않는다. 계약 원본은 docs/api/openapi.yaml이다.
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    admission = UnavailableAdmissionService()
    admission_store = None
    if redis_client is not None and settings.request_limit_key is not None and settings.inference_control_epoch is not None:
        try:
            admission_store = RedisAdmissionStore(redis_client, epoch=settings.inference_control_epoch)
            admission = AdmissionService(admission_store, identity_key=bytes.fromhex(settings.request_limit_key.get_secret_value()))
        except ValueError:
            # 설정 원문·비밀키를 예외/로그로 내보내지 않고 기능만 중단한다.
            admission = UnavailableAdmissionService()
    app.state.admission_service = admission
    llm_adapter = ControlledLLMAdapter(build_llm_adapter(settings), admission)
    app.state.llm_adapter = llm_adapter
    speech_adapter = ControlledSpeechAdapter(InternalSpeechAdapter(), admission)
    app.state.speech_adapter = speech_adapter

    app.state.db_engine = engine
    app.state.redis = redis_client
    session_store = RedisSessionStore(redis_client) if redis_client is not None else UnavailableSessionStore()
    app.state.session_service = SessionService(session_store)
    anonymous_consents = RedisConsentStore(redis_client, session_key=session_store.key) if redis_client is not None else UnavailableConsentStore()
    member_consents = SQLConsentStore(engine) if engine is not None else UnavailableConsentStore()
    app.state.notice_catalog = notice_catalog
    app.state.consent_service = ConsentService(
        RoutedConsentStore(anonymous_consents, member_consents),
        ai_version=settings.ai_notice_version, storage_version=settings.storage_notice_version,
    )
    request_store = RedisRequestStore(redis_client, session_key=session_store.key) if redis_client is not None else UnavailableRequestStore()
    app.state.request_service = RequestService(request_store)
    journey_store = UnavailableJourneyStore()
    if redis_client is not None and admission_store is not None and isinstance(admission, AdmissionService):
        journey_store = RedisJourneyStore(redis_client, session_key=session_store.key, resource_key=request_store.resource_key,
                                         control_key=admission_store.control_key, epoch=settings.inference_control_epoch)
    app.state.journey_service = JourneyService(journey_store, app.state.consent_service, admission)
    transcription_store = RedisTranscriptionStore(redis_client, session_key=session_store.key, resource_key=request_store.resource_key) if redis_client is not None else UnavailableTranscriptionStore()
    app.state.transcription_service = TranscriptionService(transcription_store, app.state.journey_service, speech_adapter)
    app.state.journey_message_service = JourneyMessageService(app.state.journey_service, app.state.request_service, llm_adapter, app.state.transcription_service)
    app.state.opportunity_service = PublicOpportunityService(SqlPublicOpportunityRepository(engine.connect) if engine is not None else UnavailableOpportunityRepository())
    app.state.opportunity_ingestion_service = IngestionService(SqlIngestionRepository(engine.begin) if engine is not None else UnavailableIngestionRepository())
    kakao = None
    if (settings.public_origin is not None and settings.kakao_rest_api_key is not None
            and settings.kakao_client_secret is not None and settings.kakao_app_id is not None
            and settings.kakao_rest_api_key.get_secret_value().strip() and settings.kakao_client_secret.get_secret_value().strip()):
        kakao = KakaoAdapter(settings.kakao_rest_api_key, settings.kakao_client_secret, settings.kakao_app_id,
                             settings.public_origin + API_PREFIX + "/auth/kakao/callback")
    async def transition(session):
        hook = getattr(app.state, "session_transition_hook", None)
        if hook is not None:
            await hook(session)
        else:
            for name in ('journey_service', 'save_intent_service'):
                service = getattr(app.state, name, None)
                if service is not None and not getattr(service, 'session_transition_managed', False):
                    raise AppError("SERVICE_UNAVAILABLE")

    app.state.member_service = MemberService(
        SqlAccountRepository(sessionmaker(engine).begin) if engine is not None else UnavailableAccountRepository(),
        RedisMemberStore(redis_client) if redis_client is not None else UnavailableMemberStore(),
        app.state.session_service, transition=transition)
    app.state.save_intent_service = SaveIntentService(
        RedisSaveIntentStore(redis_client, session_key=session_store.key, resource_key=request_store.resource_key)
            if redis_client is not None else UnavailableSaveIntentStore(),
        app.state.member_service, app.state.consent_service,
        SqlSaveIntentPolicy(sessionmaker(engine).begin) if engine is not None else UnavailableSaveIntentPolicy())
    app.state.member_service.save_intents = app.state.save_intent_service
    try:
        cipher = ContentCipher(EncryptionKeyRing.from_settings(settings))
    except EncryptionUnavailable:
        cipher = None
    app.state.saved_profile_service = SavedProfileService(SqlProfileRepository(cipher), app.state.member_service,
        app.state.consent_service, app.state.save_intent_service, app.state.journey_service)
    app.state.journey_service.stored_profiles = app.state.saved_profile_service
    app.state.oauth_service = OAuthService(RedisFlowStore(redis_client) if redis_client is not None else UnavailableFlowStore(), kakao,
                                          app.state.member_service)
    app.state.eligibility_service = EligibilityService(app.state.journey_service, app.state.opportunity_service)
    app.state.role_service = RoleService(app.state.journey_service, SQLRoleCatalog(engine.connect) if engine is not None else UnavailableRoleCatalog())
    app.state.recommendation_service = RecommendationService(app.state.journey_service, app.state.opportunity_service, app.state.role_service)
    draft_store = RedisDraftStore(redis_client, session_key=session_store.key, resource_key=request_store.resource_key) if redis_client is not None else UnavailableDraftStore()
    app.state.draft_service = DraftService(draft_store, app.state.journey_service, app.state.opportunity_service, llm_adapter)
    app.state.saved_draft_service = SavedDraftService(SqlDraftRepository(app.state.saved_profile_service.repository),
        app.state.member_service, app.state.consent_service, app.state.save_intent_service, app.state.journey_service, app.state.draft_service)
    app.state.draft_service.stored_drafts = app.state.saved_draft_service
    app.state.deletion_service = DeletionService(
        SqlDeletionRepository(sessionmaker(engine).begin) if engine is not None else UnavailableDeletionRepository(),
        FileDeletionJournal(settings.deletion_journal_directory)
            if settings.app_env == 'development' and settings.deletion_journal_directory is not None else UnavailableDeletionJournal(),
        app.state.member_service, app.state.save_intent_service.policy,
        RedisMemberCleanup(app.state.member_service.store) if redis_client is not None else UnavailableMemberCleanup())
    app.state.speech_service = SpeechService(app.state.journey_service, app.state.draft_service, app.state.opportunity_service,
        app.state.consent_service, app.state.request_service, speech_adapter)
    probes: dict[Component, ReadinessProbe] = {component: NotConfiguredProbe() for component in COMPONENTS}
    if engine is not None:
        probes["db"] = DatabaseProbe(engine)
    if redis_client is not None:
        probes["redis"] = RedisProbe(redis_client)
    probes["llm"] = llm_adapter
    probes['speech'] = speech_adapter
    probes.update(readiness_probes or {})
    app.state.settings = settings
    app.state.readiness_service = ReadinessService(probes, settings.health_check_timeout_seconds)

    register_error_handlers(app)
    # 나중에 더한 미들웨어가 바깥에 선다. 처리하지 못한 예외의 500 응답에도 X-Request-ID가 붙는다.
    app.add_middleware(RequestSecurityMiddleware)
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(operations.router)
    # 공개 API 라우터는 API_PREFIX 아래에 더한다.
    app.include_router(regions.router, prefix=API_PREFIX)
    app.include_router(sessions.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(save_intents.router, prefix=API_PREFIX)
    app.include_router(saved_profiles.router, prefix=API_PREFIX)
    app.include_router(saved_drafts.router, prefix=API_PREFIX)
    app.include_router(deletions.router, prefix=API_PREFIX)
    app.include_router(consents.router, prefix=API_PREFIX)
    app.include_router(opportunities.router, prefix=API_PREFIX)
    app.include_router(journeys.router, prefix=API_PREFIX)
    app.include_router(eligibility.router, prefix=API_PREFIX)
    app.include_router(roles.router, prefix=API_PREFIX)
    app.include_router(recommendations.router, prefix=API_PREFIX)
    app.include_router(drafts.router, prefix=API_PREFIX)
    app.include_router(speech.router, prefix=API_PREFIX)

    return app


app = create_app()
