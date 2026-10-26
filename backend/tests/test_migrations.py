"""빈 DB upgrade/downgrade·스키마 일치·실제 SQL 불변 트리거를 검증한다."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from sqlalchemy import Date, Integer, Uuid, String, column, inspect, insert, select, table, update
from sqlalchemy.exc import IntegrityError

from app.persistence import ApplicationDraft, Base, OpportunityVersion, ProfileVersion, Source
from app.persistence.base import UTCDateTime
from tests.persistence_helpers import open_test_database
from tests.test_member_models import NOW, saved_draft, seed


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_migration_graph_has_a_single_head():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


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


@pytest.mark.parametrize("existing_revision", ["0006_deletion_generations", "0004_manual_evidence"])
def test_member_and_ingestion_branches_upgrade_without_losing_existing_source(empty_db, existing_revision):
    config = migration_config(empty_db)
    command.upgrade(config, existing_revision)
    source_id = uuid4()
    empty_db.execute(insert(Source), {
        "id": source_id, "code": "fictional-branch-merge", "name": "가상 출처",
        "base_url": "https://example.org", "enabled": True,
    })

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert empty_db.execute(select(Source.name).where(Source.id == source_id)).scalar_one() == "가상 출처"
    assert compare_metadata(MigrationContext.configure(empty_db), Base.metadata) == []


def test_region_cursor_upgrade_preserves_budget_and_resets_only_national_volunteer_page(empty_db):
    from app.persistence.operations import IngestionState
    config = migration_config(empty_db)
    command.upgrade(config, "0007_member_ingestion")
    legacy = table("ingestion_states", column("source_id", Uuid()), column("quota_date", Date()),
                   column("request_count", Integer()), column("next_page", Integer()))
    ids = {}
    for code in ("volunteer", "senuri"):
        ids[code] = uuid4()
        empty_db.execute(insert(Source), {"id": ids[code], "code": code, "name": "가상 출처",
                                          "base_url": "https://example.org", "enabled": True})
        empty_db.execute(insert(legacy), {"source_id": ids[code], "quota_date": NOW.date(),
                                         "request_count": 123, "next_page": 17})
    command.upgrade(config, "head")
    for code, identifier in ids.items():
        state = empty_db.execute(select(IngestionState.__table__).where(
            IngestionState.source_id == identifier)).mappings().one()
        assert state["region_index"] == 0 and state["request_count"] == 123
        assert state["quota_date"] == NOW.date()
        assert state["next_page"] == (1 if code == "volunteer" else 17)
    with pytest.raises(IntegrityError), empty_db.begin_nested():
        empty_db.execute(update(IngestionState).values(region_index=3))
    command.downgrade(config, "0007_member_ingestion")
    assert len(empty_db.execute(select(legacy)).all()) == 2
    command.upgrade(config, "head")
    assert compare_metadata(MigrationContext.configure(empty_db), Base.metadata) == []


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
