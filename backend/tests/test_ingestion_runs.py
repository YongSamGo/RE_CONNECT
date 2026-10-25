"""실행/재개/성공 시각/예산. PostgreSQL에서 실제 세션 잠금도 검사한다."""

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import os
import multiprocessing
from pathlib import Path
import time
import threading
from types import SimpleNamespace
from uuid import uuid4
import xml.etree.ElementTree as ET

from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema

from app.collect import store_factory
from app.modules.ingestion.fetch import FetchResult, FetchStatus, VOLUNTEER_REGIONS, parse_xml
from app.modules.ingestion.runner import Collector
from app.modules.ingestion.runs import BASE_URLS, RunRepository, SqlRun, StopRun
from app.modules.opportunities.ingestion import IngestionService
from app.modules.opportunities.ingestion_repository import SqlIngestionRepository
from app.persistence import Base
from app.persistence.operations import IngestionRun as Run, IngestionReview, IngestionState as State, OpportunityDocument, OpportunityPublication, OpportunityVersion, Source
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config


class Clock:
    now = datetime(2026, 1, 10, 3, tzinfo=UTC)

    def __call__(self):
        return self.now


@pytest.fixture(params=["sqlite", "postgresql"])
def setup(request):
    backend = request.param
    url = os.environ.get("PERSISTENCE_TEST_DATABASE_URL") if backend == "postgresql" else "sqlite://"
    if url is None:
        pytest.skip("PostgreSQL 전용 실행 환경 없음")
    admin = None
    schema = "runs_" + uuid4().hex
    if backend == "postgresql":
        admin = create_engine(url, hide_parameters=True, poolclass=NullPool)
        with admin.begin() as db:
            db.execute(CreateSchema(schema))
        engine = create_engine(url, hide_parameters=True, poolclass=NullPool, connect_args={"options": "-c search_path=" + schema})
    else:
        engine = create_engine(url, hide_parameters=True, poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        if backend == "postgresql":
            with engine.begin() as db:
                config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                config.attributes["connection"] = db
                command.upgrade(config, "head")
        else:
            Base.metadata.create_all(engine)
        source_id = uuid4()
        with engine.begin() as db:
            db.execute(insert(Source), {"id": source_id, "code": "senuri", "name": "가상 시험 출처", "base_url": BASE_URLS["senuri"], "enabled": True})
        clock = Clock()
        if backend == "postgresql":
            repo = RunRepository(engine, clock)
        else:
            @contextmanager
            def acquire(identifier, *, due=False):
                with engine.connect() as db:
                    with db.begin():
                        source = db.execute(select(Source.__table__).where(Source.id == identifier)).mappings().one()
                        state = db.execute(select(State.__table__).where(State.source_id == identifier)).mappings().one_or_none()
                        if not source["enabled"] or due and state is not None and state["next_run_at"] is not None and state["next_run_at"] > clock():
                            yield None
                            return
                        if state is None:
                            db.execute(insert(State), {"source_id": identifier, "quota_date": clock().date(), "request_count": 0, "next_page": 1})
                            state = {"next_page": 1, "region_index": 0}
                        run_id = uuid4()
                        db.execute(insert(Run), {"id": run_id, "source_id": identifier, "status": "running", "started_at": clock()})
                    yield SqlRun(db, source, run_id, state, clock)
            repo = SimpleNamespace(acquire=acquire)
        def factory(session):
            @contextmanager
            def transaction():
                yield session
            return IngestionService(SqlIngestionRepository(transaction), clock=clock)
        collector = Collector(repo, factory, sessionmaker(engine).begin, SecretStr("fixture"), clock=clock, fetcher=fake_fetch)
        yield SimpleNamespace(engine=engine, repo=repo, collector=collector, source=source_id, clock=clock, backend=backend, schema=schema)
    finally:
        engine.dispose()
        if admin is not None:
            with admin.begin() as db:
                db.execute(DropSchema(schema, cascade=True))
            admin.dispose()


def envelope(values, total):
    root = ET.Element("response")
    ET.SubElement(ET.SubElement(root, "header"), "resultCode").text = "00"
    body = ET.SubElement(root, "body")
    item = ET.SubElement(ET.SubElement(body, "items"), "item")
    for k, v in values.items():
        ET.SubElement(item, k).text = v
    ET.SubElement(body, "totalCount").text = str(total)
    return parse_xml(ET.tostring(root, encoding="utf-8"))


async def fake_fetch(request, key):
    if request.operation.endswith("_list"):
        return envelope({"jobId": "F" + str(request.page_no), "recrtTitle": "가상 공고", "oranNm": "가상 기관", "workPlcNm": "서울 노원구", "stmNm": "워크넷", "acptMthd": "방문", "toDd": "20261231", "deadline": "접수중"}, 2)
    return envelope({"jobId": request.external_id, "wantedAuthNo": "K" + request.external_id, "wantedTitle": "가상 공고", "plbizNm": "가상 기관", "age": "60"}, 1)


def rows(setup, model):
    with setup.engine.connect() as db:
        return list(db.execute(select(model.__table__)).mappings())


def execute(setup, **kwargs):
    return asyncio.run(setup.collector.run(setup.source, rows=1, **kwargs))


def volunteer_fetcher(setup, *, empty_regions=()):
    with setup.engine.begin() as db:
        db.execute(update(Source).where(Source.id == setup.source).values(
            code="volunteer", base_url=BASE_URLS["volunteer"]))
    calls = []

    async def fetcher(request, key):
        calls.append(request)
        if request.operation == "volunteer_list":
            if request.region_code in empty_regions:
                return parse_xml(b"<response><header><resultCode>00</resultCode></header>"
                                 b"<body><items/><totalCount>0</totalCount></body></response>")
            return envelope({"progrmRegistNo": request.region_code + str(request.page_no),
                             "progrmSj": "가상 봉사", "sidoCd": request.region_code}, 2)
        return envelope({"progrmRegistNo": request.external_id, "progrmSj": "가상 봉사",
                         "mnnstNm": "가상 기관", "adultPosblAt": "Y", "progrmSttusSe": "2",
                         "noticeBgnde": "20260101", "noticeEndde": "20261231"}, 1)

    setup.collector.fetcher = fetcher
    return calls


def test_volunteer_budget_resumes_exact_region_and_page_before_marking_success(setup):
    calls = volunteer_fetcher(setup)
    assert execute(setup, max_requests=2).failure_code == "budget_exhausted"
    state = rows(setup, State)[0]
    assert (state["region_index"], state["next_page"]) == (0, 2)
    assert execute(setup, max_requests=4).failure_code == "budget_exhausted"
    state = rows(setup, State)[0]
    assert (state["region_index"], state["next_page"]) == (1, 2)
    assert rows(setup, Source)[0]["last_success_at"] is None
    assert execute(setup, max_requests=6).status == "succeeded"
    assert [(r.region_code, r.page_no) for r in calls if r.operation.endswith("_list")] == [
        (region, page) for region in VOLUNTEER_REGIONS for page in (1, 2)]
    state = rows(setup, State)[0]
    assert (state["region_index"], state["next_page"], state["request_count"]) == (0, 1, 12)
    assert len(rows(setup, OpportunityVersion)) == 6
    assert rows(setup, Source)[0]["last_success_at"] == setup.clock()


def test_volunteer_page_limit_and_empty_region_advance_without_false_completion(setup):
    calls = volunteer_fetcher(setup, empty_regions=(VOLUNTEER_REGIONS[0], VOLUNTEER_REGIONS[2]))
    assert execute(setup, max_pages=1).failure_code == "incomplete"
    assert rows(setup, State)[0]["region_index"] == 1
    assert rows(setup, Source)[0]["last_success_at"] is None
    assert execute(setup, max_requests=5).status == "succeeded"
    assert [(r.region_code, r.page_no) for r in calls if r.operation.endswith("_list")] == [
        (VOLUNTEER_REGIONS[0], 1), (VOLUNTEER_REGIONS[1], 1),
        (VOLUNTEER_REGIONS[1], 2), (VOLUNTEER_REGIONS[2], 1)]
    assert rows(setup, State)[0]["request_count"] == 6


def test_volunteer_regions_share_daily_quota_and_resume_after_failed_detail(setup):
    volunteer_fetcher(setup)
    with setup.engine.begin() as db:
        db.execute(insert(State), {"source_id": setup.source, "quota_date": setup.clock().date(),
                                  "request_count": 999, "next_page": 2, "region_index": 1})
    assert execute(setup).failure_code == "budget_exhausted"
    state = rows(setup, State)[0]
    assert (state["region_index"], state["next_page"], state["request_count"]) == (1, 2, 1000)
    assert execute(setup).failure_code == "budget_exhausted"
    setup.clock.now += timedelta(days=1)
    assert execute(setup).status == "succeeded"
    assert rows(setup, State)[0]["request_count"] == 6


def test_success_persists_pending_versions_metadata_and_aggregate(setup):
    result = execute(setup, max_requests=4)
    assert result.status == "succeeded"
    run = rows(setup, Run)[0]
    assert (run["fetched_count"], run["created_count"], run["request_count"], run["rejected_count"]) == (2, 2, 4, 0)
    assert rows(setup, Source)[0]["last_success_at"] == setup.clock()
    assert rows(setup, State)[0]["next_page"] == 1
    assert rows(setup, State)[0]["next_run_at"] == setup.clock() + timedelta(hours=6)
    assert len(rows(setup, IngestionReview)) == 2
    assert all(r["review_status"] == "pending" for r in rows(setup, OpportunityVersion))


def test_same_content_retry_is_idempotent_and_due_skips(setup):
    assert execute(setup, max_requests=4).status == "succeeded"
    assert execute(setup, due=True).status == "skipped"
    setup.clock.now += timedelta(hours=1)
    assert execute(setup, max_requests=4).status == "succeeded"
    assert len(rows(setup, OpportunityVersion)) == 2
    assert rows(setup, State)[0]["request_count"] == 8
    assert sum(r["created_count"] for r in rows(setup, Run)) == 2


def test_request_budget_stops_and_resumes_without_false_success(setup):
    result = execute(setup, max_requests=2)
    assert result.failure_code == "budget_exhausted"
    assert rows(setup, Source)[0]["last_success_at"] is None
    assert rows(setup, State)[0]["next_page"] == 2
    assert len(rows(setup, OpportunityVersion)) == 1
    assert execute(setup, max_requests=4).status == "succeeded"
    assert rows(setup, State)[0]["request_count"] == 4
    assert len(rows(setup, OpportunityVersion)) == 2


def test_daily_quota_survives_runs_and_resets_only_on_new_day(setup):
    with setup.engine.begin() as db:
        db.execute(insert(State), {"source_id": setup.source, "quota_date": setup.clock().date(), "request_count": 9999, "next_page": 1})
    assert execute(setup).failure_code == "budget_exhausted"
    assert rows(setup, State)[0]["request_count"] == 10000
    assert execute(setup).failure_code == "budget_exhausted"
    setup.clock.now += timedelta(days=1)
    assert execute(setup, max_requests=4).status == "succeeded"
    assert rows(setup, State)[0]["request_count"] == 4


def test_failed_fetch_keeps_previous_success_and_never_closes_documents(setup):
    assert execute(setup, max_requests=4).status == "succeeded"
    old_success = rows(setup, Source)[0]["last_success_at"]
    async def denied(*args):
        return FetchResult(FetchStatus.HTTP_ERROR, http_status=403)
    setup.collector.fetcher = denied
    setup.clock.now += timedelta(hours=7)
    assert execute(setup).failure_code == "source_unavailable"
    assert rows(setup, Source)[0]["last_success_at"] == old_success
    assert all(r["recruitment_status"] == "open" for r in rows(setup, OpportunityVersion))


def test_metadata_failure_rolls_back_new_version_and_creation_count(setup):
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO ingestion_reviews"):
            raise RuntimeError("fixture metadata failure")
    event.listen(setup.engine, "before_cursor_execute", fail)
    try:
        assert execute(setup).status == "failed"
    finally:
        event.remove(setup.engine, "before_cursor_execute", fail)
    assert rows(setup, OpportunityDocument) == rows(setup, OpportunityVersion) == []
    assert rows(setup, Run)[0]["created_count"] == 0
    assert rows(setup, Source)[0]["last_success_at"] is None


def test_cancellation_preserves_spent_quota_and_failed_run(setup):
    async def main():
        entered = asyncio.Event()
        async def slow(request, key):
            if request.operation.endswith("_detail"):
                entered.set()
                await asyncio.sleep(10)
            return await fake_fetch(request, key)
        setup.collector.fetcher = slow
        task = asyncio.create_task(setup.collector.run(setup.source, rows=1))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(main())
    assert rows(setup, Run)[0]["failure_code"] == "cancelled"
    assert rows(setup, State)[0]["request_count"] == 2
    assert rows(setup, State)[0]["next_page"] == 1
    assert rows(setup, Source)[0]["last_success_at"] is None


def test_disabled_source_never_creates_run(setup):
    with setup.engine.begin() as db:
        db.execute(update(Source).where(Source.id == setup.source).values(enabled=False))
    assert execute(setup).status == "skipped"
    assert rows(setup, Run) == []


def test_postgresql_excludes_same_source_and_recovers_abandoned_run(setup):
    if setup.backend != "postgresql":
        pytest.skip("PostgreSQL 실제 세션 잠금 전용")
    with setup.repo.acquire(setup.source) as first:
        assert first is not None
        with setup.repo.acquire(setup.source) as other:
            assert other is None
        old_id = first.id
    with setup.repo.acquire(setup.source) as recovered:
        assert recovered is not None
        old = next(r for r in rows(setup, Run) if r["id"] == old_id)
        assert old["failure_code"] == "cancelled" and old["status"] == "failed"
        recovered.finish("cancelled")


def test_page_limit_is_incomplete_and_resumable(setup):
    assert execute(setup, max_pages=1).failure_code == "incomplete"
    assert rows(setup, State)[0]["next_page"] == 2
    assert rows(setup, Source)[0]["last_success_at"] is None
    assert execute(setup).status == "succeeded"


def test_observed_outside_region_keeps_old_publication_but_holds_recommendation(setup):
    assert execute(setup, max_requests=4).status == "succeeded"
    with setup.engine.begin() as db:
        db.execute(update(OpportunityVersion).values(review_status="approved", reviewed_at=setup.clock()))
        for doc in db.scalars(select(OpportunityDocument.id)):
            db.execute(insert(OpportunityPublication), {"opportunity_id": doc, "version": 1, "review_status": "approved"})
    async def outside(request, key):
        result = await fake_fetch(request, key)
        if request.operation.endswith("_list"):
            result.document.root.find("body/items/item/workPlcNm").text = "부산 해운대구"
        return result
    setup.collector.fetcher = outside
    setup.clock.now += timedelta(hours=1)
    assert execute(setup, max_requests=4).status == "succeeded"
    versions = rows(setup, OpportunityVersion)
    assert len(versions) == 4
    assert all(v["recruitment_status"] == "unknown" and v["review_status"] == "pending" for v in versions if v["version"] == 2)
    assert all(v["recruitment_status"] == "open" and v["review_status"] == "approved" for v in versions if v["version"] == 1)
    assert all(p["version"] == 1 for p in rows(setup, OpportunityPublication))
    latest = max(rows(setup, Run), key=lambda r: r["started_at"])
    assert latest["rejection_counts"] == {"outside_region": 2}


def test_clock_going_back_does_not_reset_quota(setup):
    with setup.engine.begin() as db:
        db.execute(insert(State), {"source_id": setup.source, "quota_date": setup.clock().date() + timedelta(days=1), "request_count": 9999, "next_page": 1})
    assert execute(setup).failure_code == "configuration"
    assert rows(setup, State)[0]["request_count"] == 9999


def test_short_page_never_becomes_false_completed_collection(setup):
    result = asyncio.run(setup.collector.run(setup.source, rows=2))
    assert result.failure_code == "invalid_payload"
    assert rows(setup, Source)[0]["last_success_at"] is None
    assert rows(setup, OpportunityVersion) == []


def test_different_sources_do_not_share_a_global_lock(setup):
    if setup.backend != "postgresql":
        pytest.skip("PostgreSQL 실제 세션 잠금 전용")
    second = uuid4()
    with setup.engine.begin() as db:
        db.execute(insert(Source), {"id": second, "code": "volunteer", "name": "가상 봉사 출처", "base_url": BASE_URLS["volunteer"], "enabled": True})
    with setup.repo.acquire(setup.source) as first:
        with setup.repo.acquire(second) as other:
            assert first is not None and other is not None
            other.finish("cancelled")
        first.finish("cancelled")


def _hold_source(url, schema, source_id, timestamp, output):
    engine = create_engine(url, hide_parameters=True, poolclass=NullPool, connect_args={"options": "-c search_path=" + schema})
    try:
        repo = RunRepository(engine, lambda: datetime.fromisoformat(timestamp))
        with repo.acquire(source_id) as run:
            if run is None:
                output.send(("error", None))
                return
            output.send(("locked", run.id))
            time.sleep(30)
    except Exception:
        output.send(("error", None))
    finally:
        engine.dispose()
        output.close()


def test_actual_worker_process_death_releases_source_lock(setup):
    if setup.backend != "postgresql":
        pytest.skip("PostgreSQL 실제 프로세스 종료 전용")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_hold_source, args=(setup.engine.url.render_as_string(hide_password=False),
        setup.schema, setup.source, setup.clock().isoformat(), child))
    process.start()
    child.close()
    try:
        assert parent.poll(10), "시험 프로세스 준비 시간 초과"
        status, old_id = parent.recv()
        assert status == "locked"
        with setup.repo.acquire(setup.source) as other:
            assert other is None
        process.terminate()
        process.join(5)
        assert not process.is_alive()
        acquired = False
        for _ in range(50):
            with setup.repo.acquire(setup.source) as recovered:
                if recovered is not None:
                    assert next(r for r in rows(setup, Run) if r["id"] == old_id)["failure_code"] == "cancelled"
                    recovered.finish("cancelled")
                    acquired = True
                    break
            time.sleep(.05)
        assert acquired
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        process.close()
        parent.close()


def test_competing_source_row_lock_has_bounded_storage_wait(setup):
    if setup.backend != "postgresql":
        pytest.skip("PostgreSQL 실제 행 잠금 전용")
    blocker = setup.engine.connect()
    holder = None
    released = threading.Event()
    timer = None

    def release():
        released.set()
        holder.rollback()

    async def fetch_then_lock(request, key):
        nonlocal holder, timer
        result = await fake_fetch(request, key)
        if request.operation.endswith("_detail"):
            holder = blocker.begin()
            blocker.execute(select(Source.id).where(Source.id == setup.source).with_for_update())
            timer = threading.Timer(5, release)
            timer.start()
        return result

    setup.collector.fetcher = fetch_then_lock
    try:
        assert execute(setup).status == "failed"
        assert not released.is_set(), "차단 트랜잭션이 끝나기 전에 저장 잠금 대기를 중단해야 함"
        assert rows(setup, OpportunityVersion) == []
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if holder is not None and holder.is_active:
            holder.rollback()
        blocker.close()
