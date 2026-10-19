"""운영자용 제한 수집 명령. 비밀값·원문·예외 문자열을 출력하지 않는다."""

import argparse
import asyncio
from contextlib import contextmanager
import json
from uuid import UUID

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.contracts.time import utc_now
from app.core.config import get_settings
from app.modules.ingestion.runner import Collector
from app.modules.ingestion.runs import RunRepository
from app.modules.opportunities.ingestion import IngestionService
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.persistence.connection import build_engine


def store_factory(session):
    @contextmanager
    def transaction():
        yield session
    return IngestionService(SqlIngestionRepository(transaction))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=UUID, required=True)
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--due", action="store_true", help="성공 후 6시간/실패 후 15분 스케줄 시각 검사")
    args = parser.parse_args()
    engine = None
    try:
        settings = get_settings()
        if settings.data_go_kr_service_key is None:
            raise ValueError("수집 설정 필요")
        engine = build_engine(settings, poolclass=NullPool)
        collector = Collector(RunRepository(engine, utc_now), store_factory, sessionmaker(engine).begin,
                              settings.data_go_kr_service_key)
        result = asyncio.run(collector.run(args.source, max_requests=args.max_requests,
            max_pages=args.max_pages, rows=args.rows, due=args.due))
        print(json.dumps({"status": result.status, "run_id": str(result.run_id) if result.run_id else None,
                          "failure_code": result.failure_code}))
        return 1 if result.status == "failed" else 0
    except KeyboardInterrupt:
        print('{"status":"cancelled"}')
        return 130
    except Exception:
        print('{"status":"unavailable"}')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
