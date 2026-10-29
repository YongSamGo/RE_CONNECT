"""운영자용 제한 수집 명령. 비밀값·원문·예외 문자열을 출력하지 않는다."""

import argparse
import asyncio
from contextlib import contextmanager
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.contracts.time import utc_now
from app.core.config import get_settings
from app.modules.ingestion.runner import Collector
from app.modules.ingestion.runs import DAILY_LIMITS
from app.modules.ingestion.runs import RunRepository
from app.modules.opportunities.ingestion import IngestionService
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.persistence.connection import build_engine
from app.persistence.operations import Source


def store_factory(session):
    @contextmanager
    def transaction():
        yield session
    return IngestionService(SqlIngestionRepository(transaction))


def enabled_sources(engine):
    """주기 실행 대상. 출처 UUID를 스케줄 설정에 적지 않도록 DB의 활성 출처를 코드 순서로 읽는다.

    수동 입력 출처(`manual_*`)도 활성이지만 API 수집 대상이 아니므로 수집기가 다루는 코드만 고른다.
    """
    with engine.connect() as db:
        return list(db.scalars(select(Source.id).where(Source.enabled.is_(True), Source.code.in_(DAILY_LIMITS))
                               .order_by(Source.code, Source.id)))


async def run_due(collector, source_ids, **limits):
    """활성 출처를 차례로 `--due` 실행한다. 한 출처가 실패해도 나머지 출처는 계속 확인한다."""
    results = []
    for source_id in source_ids:
        try:
            result = await collector.run(source_id, due=True, **limits)
            entry = {"status": result.status, "run_id": str(result.run_id) if result.run_id else None,
                     "failure_code": result.failure_code}
        except Exception:
            entry = {"status": "unavailable", "run_id": None, "failure_code": None}
        results.append({"source_id": str(source_id), **entry})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source", type=UUID)
    target.add_argument("--all-due", action="store_true", help="활성 출처 전체를 차례로 --due 실행(주기 실행용)")
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
        limits = {"max_requests": args.max_requests, "max_pages": args.max_pages, "rows": args.rows}
        if args.all_due:
            results = asyncio.run(run_due(collector, enabled_sources(engine), **limits))
            print(json.dumps({"results": results}))
            return 1 if any(r["status"] in ("failed", "unavailable") for r in results) else 0
        result = asyncio.run(collector.run(args.source, due=args.due, **limits))
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
