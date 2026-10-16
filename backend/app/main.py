"""FastAPI 앱 조립.

실행: `backend/`에서 `uvicorn app.main:app`. 테스트는 `create_app()`에 가짜 구성 요소를 넘겨 만든다.
구체 구현(DB·Redis·Ollama·음성 서비스)은 여기서만 고르고, 모듈은 Protocol로 받는다.
"""

from collections.abc import Mapping

from fastapi import FastAPI

from app.adapters.ollama import OllamaLLMAdapter
from app.core.config import Settings, get_settings
from app.core.errors import UnhandledErrorMiddleware, register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.modules.operations import router as operations
from app.modules.operations.readiness import (
    COMPONENTS,
    Component,
    NotConfiguredProbe,
    ReadinessProbe,
    ReadinessService,
)
from app.modules.regions import router as regions

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

    app = FastAPI(
        title="다시잇다 API",
        # 운영에서는 API 문서 화면과 스키마를 열지 않는다. 계약 원본은 docs/api/openapi.yaml이다.
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    llm_adapter = build_llm_adapter(settings)
    app.state.llm_adapter = llm_adapter

    # 각 연결 구현이 생기면(#18 DB·Redis, W04 음성) 해당 probe로 바꾼다.
    probes: dict[Component, ReadinessProbe] = {component: NotConfiguredProbe() for component in COMPONENTS}
    probes["llm"] = llm_adapter
    probes.update(readiness_probes or {})
    app.state.settings = settings
    app.state.readiness_service = ReadinessService(probes, settings.health_check_timeout_seconds)

    register_error_handlers(app)
    # 나중에 더한 미들웨어가 바깥에 선다. 처리하지 못한 예외의 500 응답에도 X-Request-ID가 붙는다.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(operations.router)
    # 공개 API 라우터는 API_PREFIX 아래에 더한다.
    app.include_router(regions.router, prefix=API_PREFIX)

    return app


app = create_app()
