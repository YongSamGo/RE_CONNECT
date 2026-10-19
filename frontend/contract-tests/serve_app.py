"""Run the actual app locally for HTTP contract tests, without reading .env."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import uvicorn  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import Settings  # noqa: E402


def main() -> None:
    port = int(sys.argv[1])
    if not 1 <= port <= 65535:
        raise ValueError("Invalid test port")
    settings = Settings(_env_file=None, app_env="test", database_url=None, redis_url=None,
                        request_limit_key=None, inference_control_epoch=None)
    # main.py also constructs its module-level app during import. Use the same
    # explicit settings there; never load a developer's .env for a test server.
    with patch("app.core.config.get_settings", return_value=settings):
        from app.main import create_app
    app = create_app(settings)
    # 실제 SQL 저장소와 라우터를 사용하되 운영 DB·실제 공고에는 연결하지 않는다.
    from app.contracts.time import utc_now
    from app.modules.opportunities.repository import SqlPublicOpportunityRepository
    from app.modules.opportunities.service import PublicOpportunityService
    from app.persistence import Base
    from tests.test_public_opportunities import seeded

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        with engine.begin() as db:
            Base.metadata.create_all(db)
            add = seeded(db)
            for index, method, documents in ((1, "online", None), (2, "phone", []), (3, "mixed", ["공식 신청서"])):
                add(index, application_method=method, required_documents=documents,
                    application_instructions="가상 공고의 공식 안내를 확인해 주세요.",
                    source_checked_at=utc_now(), reviewed_at=utc_now())
            add(4, public=False)
        app.state.opportunity_service = PublicOpportunityService(SqlPublicOpportunityRepository(engine.connect))
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
