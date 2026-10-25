"""버전 저장의 실제 commit·다중 연결 시험용 격리 DB."""

from contextlib import contextmanager
import os
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.schema import CreateSchema, DropSchema

from app.persistence import Source
from tests.test_migrations import migration_config


@contextmanager
def ingestion_database(backend, tmp_path):
    url = "sqlite:///" + (tmp_path / "ingestion.db").as_posix() if backend == "sqlite" else os.environ.get("PERSISTENCE_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("실제 PostgreSQL 동시성/commit은 CI 통합 잡에서 실행")
    schema = "test_" + uuid4().hex
    admin = create_engine(url, echo=False, hide_parameters=True)
    if backend == "postgresql":
        with admin.begin() as db:
            db.execute(CreateSchema(schema))
        engine = create_engine(url, echo=False, hide_parameters=True, connect_args={"options": f"-csearch_path={schema}"}, pool_size=12, max_overflow=0)
    else:
        engine = admin
    try:
        with engine.begin() as db:
            command.upgrade(migration_config(db), "head")
            source_id = uuid4()
            db.execute(insert(Source), {"id": source_id, "code": "fictional-ingestion", "name": "가상 수집", "base_url": "https://example.org", "enabled": True})
        yield engine, source_id
    finally:
        engine.dispose()
        if backend == "postgresql":
            with admin.begin() as db:
                db.execute(DropSchema(schema, cascade=True))
            admin.dispose()
