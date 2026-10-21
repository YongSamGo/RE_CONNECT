"""빈 DB upgrade/downgrade·스키마 일치·실제 SQL 불변 트리거를 검증한다."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Uuid, String, column, inspect, insert, select, table, update
from sqlalchemy.exc import IntegrityError

from app.persistence import ApplicationDraft, Base, OpportunityVersion, ProfileVersion
from app.persistence.base import UTCDateTime
from tests.persistence_helpers import open_test_database
from tests.test_member_models import NOW, saved_draft, seed


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(params=["sqlite", "postgresql"])
def empty_db(request):
    with open_test_database(request.param) as connection:
        yield connection


def test_empty_database_roundtrip_and_metadata_match(empty_db):
    config = migration_config(empty_db)
    command.upgrade(config, "head")
    assert set(inspect(empty_db).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    context = MigrationContext.configure(empty_db)
    assert compare_metadata(context, Base.metadata) == []
    command.downgrade(config, "base")
    assert set(inspect(empty_db).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert empty_db.execute(select(ProfileVersion.__table__)).all() == []


def test_additional_revision_preserves_existing_rows_and_blocks_bulk_overwrite(empty_db):
    config = migration_config(empty_db)
    command.upgrade(config, "0001_persistent_schema")
    # 0001의 실제 열만 사용해 업그레이드 전 자료를 만든다. 최신 ORM 기본값은 아직 없는 열을 INSERT한다.
    legacy_users = table('users', column('id', Uuid()), column('kakao_subject', String()), column('role', String()),
        column('status', String()), column('created_at', UTCDateTime()))
    owner, _, profile_id, document_id = seed(empty_db, users=legacy_users)
    empty_db.execute(insert(ApplicationDraft), saved_draft(owner, profile_id, document_id))
    command.upgrade(config, "head")
    assert empty_db.execute(select(ProfileVersion.version)).scalar_one() == 1
    for statement in (
        update(ProfileVersion).values(ciphertext=b"changed" * 10),
        update(ApplicationDraft).values(profile_version=99),
        update(OpportunityVersion).values(title="내용 덮어쓰기"),
    ):
        with pytest.raises(IntegrityError), empty_db.begin_nested():
            empty_db.execute(statement)
    # 검수·확인 시각과 종료 방향의 변경은 새 콘텐츠 버전 없이 허용한다.
    empty_db.execute(update(OpportunityVersion).values(review_status="approved", reviewed_at=NOW, recruitment_status="closed"))
    with pytest.raises(IntegrityError), empty_db.begin_nested():
        empty_db.execute(update(OpportunityVersion).values(recruitment_status="open"))
    command.downgrade(config, "0001_persistent_schema")
    empty_db.execute(update(OpportunityVersion).values(title="추가 트리거 다운그레이드 확인"))
