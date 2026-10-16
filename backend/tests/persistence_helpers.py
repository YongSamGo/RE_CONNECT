"""가상 공고의 최소 저장 그래프. 운영 데이터·연결 정보는 사용하지 않는다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4
from contextlib import contextmanager
import os

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.schema import CreateSchema, DropSchema

from app.contracts.opportunity import OpportunityContent
from app.persistence import OpportunityDocument, OpportunityVersion, Source
from tests.test_contracts import opportunity

NOW = datetime(2026, 10, 17, tzinfo=UTC)
OPPORTUNITY_ID = UUID("b54ad372-bab6-4cb5-b0d6-0a809ab60b28")


@contextmanager
def open_test_database(backend):
    url = "sqlite://" if backend == "sqlite" else os.environ.get("PERSISTENCE_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("PostgreSQL 실행 환경 없음. CI의 DB/Redis 통합 잡에서 실행한다")
    # HTTP 동기 라우터의 worker thread에서도 같은 시험 트랜잭션을 순차 조회한다.
    # 연결을 동시에 공유하지 않으며 SQLite 시험에만 thread 소유 제약을 해제한다.
    engine = create_engine(url, echo=False, hide_parameters=True, connect_args={"check_same_thread": False} if backend == "sqlite" else {})
    if backend == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    try:
        with engine.begin() as connection:
            schema = "test_" + uuid4().hex
            if backend == "postgresql":
                connection.execute(CreateSchema(schema))
                connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            try:
                yield connection
            finally:
                if backend == "postgresql":
                    connection.execute(DropSchema(schema, cascade=True))
    finally:
        engine.dispose()


def opportunity_values(opportunity_id=OPPORTUNITY_ID, version=1, **updates):
    content = OpportunityContent.model_validate(opportunity())
    values = content.model_dump(mode="json")
    region = values.pop("activity_region")
    return {
        **values, "activity_province": region["province"], "activity_district": region["district"],
        "deadline_date": content.deadline_date, "deadline_at": content.deadline_at,
        "opportunity_id": opportunity_id, "version": version, "description_truncated": False,
        "review_status": "pending", "source_checked_at": NOW, "reviewed_at": None,
        "content_hash": "a" * 64, **updates,
    }


def seed_opportunity(db, *, opportunity_id=OPPORTUNITY_ID, external_id="fictional-external"):
    source_id = uuid4()
    db.execute(insert(Source), {"id": source_id, "code": "fictional-source", "name": "가상 출처", "base_url": "https://example.org/api"})
    db.execute(insert(OpportunityDocument), {"id": opportunity_id, "source_id": source_id, "external_id": external_id})
    db.execute(insert(OpportunityVersion), opportunity_values(opportunity_id))
    return source_id, opportunity_id
