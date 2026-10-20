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
from app.modules.sessions import router as sessions
from app.modules.auth import router as auth
from app.modules.auth.service import OAuthService, UnavailableFlowStore
from app.modules.auth.repository import RedisFlowStore
from app.modules.auth.accounts import SqlAccountRepository, UnavailableAccountRepository
from app.modules.auth.member_store import RedisMemberStore, UnavailableMemberStore
from app.modules.auth.members import MemberService
from app.core.business_errors import AppError
from sqlalchemy.orm import sessionmaker
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import SessionService, UnavailableSessionStore
from app.modules.sessions.middleware import RequestSecurityMiddleware
from app.modules.opportunities import router as opportunities
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunityService, UnavailableOpportunityRepository
from app.modules.opportunities.ingestion import IngestionService, UnavailableIngestionRepository
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
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

    llm_adapter = build_llm_adapter(settings)
    app.state.llm_adapter = llm_adapter

    app.state.db_engine = engine
    app.state.redis = redis_client
    app.state.opportunity_service = PublicOpportunityService(SqlPublicOpportunityRepository(engine.connect) if engine is not None else UnavailableOpportunityRepository())
    app.state.opportunity_ingestion_service = IngestionService(SqlIngestionRepository(engine.begin) if engine is not None else UnavailableIngestionRepository())
    app.state.session_service = SessionService(RedisSessionStore(redis_client) if redis_client is not None else UnavailableSessionStore())
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
        elif getattr(app.state, "journey_service", None) is not None or getattr(app.state, "save_intent_service", None) is not None:
            # 체험/저장 대기 모듈을 합친 뒤 실제 정리 연결 없이 이전 원문을 남기지 않는다.
            raise AppError("SERVICE_UNAVAILABLE")

    app.state.member_service = MemberService(
        SqlAccountRepository(sessionmaker(engine).begin) if engine is not None else UnavailableAccountRepository(),
        RedisMemberStore(redis_client) if redis_client is not None else UnavailableMemberStore(),
        app.state.session_service, transition=transition)
    app.state.oauth_service = OAuthService(RedisFlowStore(redis_client) if redis_client is not None else UnavailableFlowStore(), kakao,
                                          app.state.member_service)
    probes: dict[Component, ReadinessProbe] = {component: NotConfiguredProbe() for component in COMPONENTS}
    if engine is not None:
        probes["db"] = DatabaseProbe(engine)
    if redis_client is not None:
        probes["redis"] = RedisProbe(redis_client)
    probes["llm"] = llm_adapter
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
    app.include_router(opportunities.router, prefix=API_PREFIX)

    return app


app = create_app()
