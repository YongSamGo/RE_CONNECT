"""새 버전은 pending, 기존 공개본은 불변, 같은 관측 재전송은 중복 없음."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.business_errors import AppError
from app.modules.opportunities.ingestion import IngestionService, RecordOpportunity
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.versions import OpportunitySnapshot, IMPORTANT_FIELDS, changed_fields, content_hash, important_changes
from app.persistence import OpportunityDocument as D, OpportunityVersion as V, OpportunityPublication as P, Source
from tests.ingestion_helpers import ingestion_database
from tests.persistence_helpers import NOW
from tests.test_contracts import opportunity, requirement


def snapshot(**changes):
    return OpportunitySnapshot.model_validate({**opportunity(), "description_truncated": False, **changes})


def service_for(engine):
    return IngestionService(SqlIngestionRepository(engine.begin), clock=lambda: NOW + timedelta(days=1))


def record(source, *, checked_at=NOW, external_id="fictional-id", manual_target=None, **changes):
    return RecordOpportunity(source_id=source, external_id=external_id, snapshot=snapshot(**changes), checked_at=checked_at, manual_target=manual_target)


def approve(engine, result):
    with engine.begin() as db:
        db.execute(update(V).where(V.opportunity_id == result.opportunity_id, V.version == result.version).values(review_status="approved", reviewed_at=NOW))
        db.execute(insert(P), {"opportunity_id": result.opportunity_id, "version": result.version})


def test_canonical_hash_and_explicit_important_fields():
    before = snapshot()
    reordered = OpportunitySnapshot.model_validate(dict(reversed(list(before.model_dump().items()))))
    assert content_hash(before) == content_hash(reordered)
    for name in ("title", "description_text", "description_truncated", "role_tags", "skill_tags"):
        assert name not in IMPORTANT_FIELDS
    assert important_changes(before, snapshot(title="새 제목")) == frozenset()
    assert important_changes(before, snapshot(schedule_text="새 일정")) == {"schedule_text"}
    assert important_changes(before, snapshot(recruitment_status="closed")) == frozenset()
    assert important_changes(snapshot(recruitment_status="closed"), snapshot(recruitment_status="open")) == {"recruitment_status"}
    assert important_changes(snapshot(recruitment_status="open"), snapshot(recruitment_status="unknown")) == {"recruitment_status"}


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_repeated_collection_commits_once_refreshes_only_observed_version_and_ignores_stale(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        service = service_for(engine)
        first = service.record(record(source))
        assert first.outcome == "created" and first.version == 1
        approve(engine, first)
        replay = service.record(record(source, checked_at=NOW + timedelta(minutes=1)))
        assert replay.outcome == "unchanged" and replay.version == 1 and replay.opportunity_id == first.opportunity_id
        changed = service.record(record(source, checked_at=NOW + timedelta(minutes=2), schedule_text="새 일정"))
        assert changed.outcome == "changed" and changed.version == 2
        stale = service.record(record(source, checked_at=NOW + timedelta(seconds=90), title="늦은 응답"))
        assert stale.outcome == "stale" and stale.version == 2
        service.record(record(source, checked_at=NOW + timedelta(minutes=3), schedule_text="새 일정"))
        public = SqlPublicOpportunityRepository(engine.connect).get(first.opportunity_id, NOW)
        assert public.version == 1 and public.change_pending
        assert public.source_checked_at == NOW + timedelta(minutes=1)
        with engine.connect() as db:
            rows = db.execute(select(V.__table__).order_by(V.version)).mappings().all()
            assert len(rows) == 2
            assert rows[0]["review_status"] == "approved" and rows[0]["reviewed_at"] == NOW
            assert rows[1]["review_status"] == "pending" and rows[1]["reviewed_at"] is None
            assert rows[1]["source_checked_at"] == NOW + timedelta(minutes=3)
            assert rows[0]["content_hash"] == content_hash(snapshot())
            assert rows[1]["content_hash"] == content_hash(snapshot(schedule_text="새 일정"))
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            service.record(record(source, checked_at=NOW + timedelta(minutes=3), title="같은 관측의 다른 내용"))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_nonimportant_edit_does_not_hold_but_important_edit_and_reopening_do(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        service = service_for(engine)
        first = service.record(record(source))
        approve(engine, first)
        service.record(record(source, checked_at=NOW + timedelta(minutes=1), title="제목 수정"))
        public_repo = SqlPublicOpportunityRepository(engine.connect)
        assert not public_repo.get(first.opportunity_id, NOW).change_pending
        service.record(record(source, checked_at=NOW + timedelta(minutes=2), title="제목 수정", schedule_text="새 일정"))
        assert public_repo.get(first.opportunity_id, NOW).change_pending
        closed = service.record(record(source, checked_at=NOW + timedelta(minutes=3), title="제목 수정", schedule_text="새 일정", recruitment_status="closed"))
        assert closed.outcome == "closed" and closed.version == 3
        public = public_repo.get(first.opportunity_id, NOW)
        assert public.recruitment_status == "closed" and public.version == 1
        reopened = service.record(record(source, checked_at=NOW + timedelta(minutes=4)))
        assert reopened.version == 4
        assert public_repo.get(first.opportunity_id, NOW).recruitment_status == "closed"
        assert public_repo.get(first.opportunity_id, NOW).change_pending
        # 불변 트리거를 우회하지 않는다. 본문은 새 버전만 가능하다.
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(update(V).where(V.opportunity_id == first.opportunity_id).values(title="덮어쓰기"))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_public_hold_matches_domain_classification_for_each_contract_field(backend, tmp_path):
    examples = {
        "activity_type": "employment", "requirements": [requirement()], "activity_region": None,
        "remote_allowed": True, "schedule_text": "새 일정", "hours_per_week": 1.0,
        "deadline_date": "2026-11-01", "deadline_at": "2026-10-31T01:00:00Z",
        "application_method": "visit", "application_url": "https://example.org/new",
        "application_instructions": "공식 안내에 따라 방문", "required_documents": ["확인 서류"],
        "paid": True, "source_url": "https://example.org/source",
        "title": "새 제목", "description_text": "새 설명", "skill_tags": ["새 역량"],
    }
    with ingestion_database(backend, tmp_path) as (engine, source):
        service = service_for(engine)
        public_repo = SqlPublicOpportunityRepository(engine.connect)
        for index, (field, value) in enumerate(examples.items()):
            key = "field-" + str(index)
            first = service.record(record(source, external_id=key))
            approve(engine, first)
            service.record(record(source, external_id=key, checked_at=NOW + timedelta(minutes=1), **{field: value}))
            expected = bool(important_changes(snapshot(), snapshot(**{field: value})))
            assert public_repo.get(first.opportunity_id, NOW).change_pending is expected, field
        for index, (before, after, expected) in enumerate((("closed", "open", True), ("open", "unknown", True), ("unknown", "open", False))):
            key = "status-" + str(index)
            first = service.record(record(source, external_id=key, recruitment_status=before))
            approve(engine, first)
            service.record(record(source, external_id=key, checked_at=NOW + timedelta(minutes=1), recruitment_status=after))
            assert public_repo.get(first.opportunity_id, NOW).change_pending is expected


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_manual_candidates_require_explicit_match_and_sources_never_merge(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        service = service_for(engine)
        first = service.record(record(source, external_id=None))
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            service.record(record(source, external_id=None, checked_at=NOW + timedelta(minutes=1)))
        matched = service.record(record(source, external_id=None, manual_target=first.opportunity_id, checked_at=NOW + timedelta(minutes=1)))
        assert matched.outcome == "unchanged"
        other = uuid4()
        with engine.begin() as db:
            db.execute(insert(Source), {"id": other, "code": "other-source", "name": "다른 출처", "base_url": "https://example.org"})
        independent = service.record(record(other, external_id=None))
        assert independent.opportunity_id != first.opportunity_id
        with pytest.raises(AppError, match="NOT_FOUND"):
            service.record(record(other, external_id=None, manual_target=first.opportunity_id))
        with pytest.raises(AppError, match="NOT_FOUND"):
            service.record(record(uuid4()))
        with pytest.raises(AppError, match="VALIDATION_FAILED"):
            service.record(record(source, manual_target=first.opportunity_id))
        with pytest.raises(AppError, match="VALIDATION_FAILED"):
            service.record(record(source, checked_at=NOW + timedelta(days=2)))


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_commit_ack_loss_retry_and_partial_insert_failure_do_not_duplicate(backend, tmp_path):
    with ingestion_database(backend, tmp_path) as (engine, source):
        @contextmanager
        def lost_ack():
            with engine.begin() as db:
                yield db
            raise OperationalError("commit", {}, Exception("시험 전용 응답 유실"))
        uncertain = IngestionService(SqlIngestionRepository(lost_ack), clock=lambda: NOW)
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            uncertain.record(record(source))
        result = service_for(engine).record(record(source))
        assert result.version == 1 and result.outcome == "unchanged"
        # DB가 중간에 실패하면 문서·버전을 함께 rollback한다.
        @contextmanager
        def rollback():
            with engine.begin() as db:
                yield db
                raise OperationalError("insert", {}, Exception("시험 전용 트랜잭션 실패"))
        failing = IngestionService(SqlIngestionRepository(rollback), clock=lambda: NOW)
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            failing.record(record(source, external_id="new-id"))
        with engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(D)) == 1
            assert db.scalar(select(func.count()).select_from(V)) == 1


def test_actual_postgresql_parallel_sources_and_versions_have_no_duplicate_or_stale_overwrite(tmp_path):
    with ingestion_database("postgresql", tmp_path) as (engine, source):
        service = service_for(engine)
        barrier = Barrier(12)
        def first(index):
            barrier.wait(timeout=10)
            return service.record(record(source))
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(first, range(12)))
        assert len({value.opportunity_id for value in results}) == 1
        assert sum(value.outcome == "created" for value in results) == 1
        assert all(value.version == 1 for value in results)
        barrier = Barrier(12)
        def changed(index):
            barrier.wait(timeout=10)
            return service.record(record(source, checked_at=NOW + timedelta(minutes=index + 1), title=f"변경 {index}"))
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(changed, range(12)))
        with engine.connect() as db:
            rows = db.execute(select(V.__table__).order_by(V.version)).mappings().all()
            assert [row["version"] for row in rows] == list(range(1, len(rows) + 1))
            assert rows[-1]["title"] == "변경 11"
            assert rows[-1]["source_checked_at"] == NOW + timedelta(minutes=12)
            assert db.scalar(select(func.count()).select_from(D)) == 1
