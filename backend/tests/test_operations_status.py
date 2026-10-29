"""운영자 상태 조회 (W07-04). 정상 집계와 장애·형식 오류·정보 노출 시나리오를 함께 검사한다.

관련 보안약점: 부적절한 인가, 오류 메시지 정보 노출. 경로는 운영자 권한·MFA(#52)와 함께 연다.
"""

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import re
from sqlalchemy import delete, event, insert

from app.adapters.internal_speech import InternalSpeechAdapter
from app.contracts.time import utc_now
from app.main import create_app
from app.modules.admission.repository import _ACQUIRE
from app.modules.admission.service import GLOBAL_DAILY_LIMIT, SHARED_SLOTS
from app.modules.operations.repository import SourceRunSummary, SqlSourceStatusRepository
from app.modules.operations.status import BoundSlotReader, Operations, OperationsService, kst_day_index
from app.persistence.operations import IngestionRun as Run, Source
from tests.conftest import FakeProbe
from tests.ingestion_helpers import ingestion_database
from tests.test_admission import identity, with_redis

NOW = datetime(2026, 10, 15, 4, 20, tzinfo=UTC)
SECRET = "postgresql://reconnect:secret-value@db:5432"
OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"


@dataclass
class Reading:
    ready: bool = True
    day: int | None = kst_day_index(NOW)
    global_count: int | None = 132
    lease: str | None = "0123456789abcdef"


class FakeSlots:
    def __init__(self, reading=None, error=None):
        self.reading, self.error = reading or Reading(), error

    async def read(self):
        if self.error is not None:
            raise self.error
        return self.reading


class FakeSpeech:
    def __init__(self, states=None, error=None):
        self.states, self.error = states if states is not None else {"stt": True, "tts": True}, error

    async def model_readiness(self):
        if self.error is not None:
            raise self.error
        return self.states


class FakeSources:
    def __init__(self, summaries=None, error=None):
        self.summaries, self.error = summaries if summaries is not None else [summary()], error

    def list(self):
        if self.error is not None:
            raise self.error
        return self.summaries


class BrokenProbe:
    async def is_ready(self):
        raise ConnectionError(SECRET)


class SlowProbe:
    async def is_ready(self):
        await asyncio.sleep(5)
        return True


def summary(**changes) -> SourceRunSummary:
    base = SourceRunSummary(
        source_id=uuid4(), name="가상 시험 출처", last_success_at=NOW - timedelta(hours=1),
        last_finished_status="succeeded", last_failure_code=None, last_finished_at=NOW - timedelta(hours=1),
        running=False, consecutive_failures=0)
    return replace(base, **changes)


def service(**changes) -> OperationsService:
    parts = dict(db=FakeProbe(), redis=FakeProbe(), inference_control=FakeProbe(), llm=FakeProbe(),
                 speech=FakeSpeech(), slots=FakeSlots(), sources=FakeSources(), timeout_seconds=0.2, clock=lambda: NOW)
    parts.update(changes)
    return OperationsService(**parts)


def check(**changes) -> Operations:
    return asyncio.run(service(**changes).check())


def test_all_components_ok_report_counts_without_bodies():
    source = summary()
    result = check(sources=FakeSources([source])).model_dump(mode="json")

    assert result == {
        "sources": [{
            "source_id": str(source.source_id), "name": "가상 시험 출처",
            "last_run_at": "2026-10-15T03:20:00Z", "last_success_at": "2026-10-15T03:20:00Z",
            "last_status": "success", "last_failure_code": None, "running": False,
            "consecutive_failures": 0, "stale": False,
        }],
        "models": {"llm": "ok", "stt": "ok", "tts": "ok"},
        "stores": {"db": "ok", "redis": "ok"},
        "limits": {"inference_today": 132, "inference_daily_limit": GLOBAL_DAILY_LIMIT, "slots_in_use": 1, "slots_total": SHARED_SLOTS},
        "checked_at": "2026-10-15T04:20:00Z",
    }


@pytest.mark.parametrize(("status", "code", "expected"), [
    ("succeeded", None, "success"),
    ("failed", "budget_exhausted", "partial"),
    ("failed", "incomplete", "partial"),
    ("failed", "network", "failed"),
    ("failed", "configuration", "failed"),
    (None, None, None),
])
def test_last_status_maps_finished_run(status, code, expected):
    source = check(sources=FakeSources([summary(last_finished_status=status, last_failure_code=code)])).sources[0]

    assert source.last_status == expected
    assert source.last_failure_code == (None if status == "succeeded" else code)


def test_running_run_is_reported_separately_from_last_finished_status():
    source = check(sources=FakeSources([summary(running=True, last_finished_status="failed", last_failure_code="parse",
                                                consecutive_failures=3)])).sources[0]

    assert (source.running, source.last_status, source.last_failure_code, source.consecutive_failures) == (True, "failed", "parse", 3)


@pytest.mark.parametrize(("age", "stale"), [
    (timedelta(hours=48), False),
    (timedelta(hours=48, microseconds=1), True),
    (timedelta(hours=1), False),
])
def test_stale_uses_strictly_more_than_48_hours(age, stale):
    assert check(sources=FakeSources([summary(last_success_at=NOW - age)])).sources[0].stale is stale


def test_source_that_never_succeeded_is_stale():
    source = check(sources=FakeSources([summary(last_success_at=None, last_finished_status=None, last_finished_at=None)])).sources[0]

    assert source.stale is True
    assert source.last_run_at is None


def test_redis_failure_keeps_200_shape_with_null_limits():
    result = check(redis=FakeProbe(ready=False), inference_control=FakeProbe(ready=False), slots=FakeSlots(error=ConnectionError(SECRET)))

    assert result.stores.redis == "fail"
    assert result.limits is None
    assert result.models.model_dump() == {"llm": "fail", "stt": "fail", "tts": "fail"}
    assert result.sources is not None


def test_db_failure_keeps_other_parts_with_null_sources():
    result = check(db=FakeProbe(ready=False), sources=FakeSources(error=ConnectionError(SECRET)))

    assert result.stores.db == "fail"
    assert result.sources is None
    assert result.limits is not None


def test_inference_control_not_ready_fails_every_model_even_if_runtime_is_up():
    result = check(inference_control=FakeProbe(ready=False), slots=FakeSlots(Reading(ready=False)))

    assert result.models.model_dump() == {"llm": "fail", "stt": "fail", "tts": "fail"}
    assert result.limits is None


def test_stt_and_tts_are_reported_separately():
    result = check(speech=FakeSpeech({"stt": True, "tts": False}))

    assert result.models.model_dump() == {"llm": "ok", "stt": "ok", "tts": "fail"}


@pytest.mark.parametrize("states", [{}, {"stt": 1, "tts": "yes"}, None])
def test_malformed_speech_states_are_fail(states):
    result = check(speech=FakeSpeech(states if states is not None else {}, error=None if states is not None else ValueError()))

    assert (result.models.stt, result.models.tts) == ("fail", "fail")


def test_previous_day_count_reads_as_zero_before_first_run_today():
    result = check(slots=FakeSlots(Reading(day=kst_day_index(NOW) - 1, global_count=480, lease=None)))

    assert result.limits.model_dump() == {"inference_today": 0, "inference_daily_limit": GLOBAL_DAILY_LIMIT,
                                          "slots_in_use": 0, "slots_total": SHARED_SLOTS}


def test_kst_day_boundary_matches_redis_day_index():
    before = datetime(2026, 10, 14, 14, 59, 59, tzinfo=UTC)  # KST 10-14 23:59:59

    assert kst_day_index(before + timedelta(seconds=1)) == kst_day_index(before) + 1


@pytest.mark.parametrize("reading", [Reading(day=None), Reading(global_count=None)])
def test_unreadable_counters_are_null_not_zero(reading):
    assert check(slots=FakeSlots(reading)).limits is None


def test_missing_infrastructure_reports_null_without_guessing():
    result = check(slots=None, sources=None)

    assert result.limits is None and result.sources is None


def test_slow_component_times_out_as_fail():
    result = check(llm=SlowProbe(), db=SlowProbe())

    assert (result.models.llm, result.stores.db) == ("fail", "fail")


def test_errors_never_reach_response_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    result = check(db=BrokenProbe(), redis=BrokenProbe(), inference_control=BrokenProbe(), llm=BrokenProbe(),
                   speech=FakeSpeech(error=ConnectionError(SECRET)), slots=FakeSlots(error=ConnectionError(SECRET)),
                   sources=FakeSources(error=ConnectionError(SECRET)))

    body = result.model_dump_json()
    assert "secret" not in body and "postgresql" not in body
    assert "secret" not in caplog.text and "postgresql" not in caplog.text
    assert "type=ConnectionError" in caplog.text


def test_invalid_stored_source_value_is_not_partially_shown():
    result = check(sources=FakeSources([summary(), summary(last_failure_code="unknown_code", last_finished_status="failed")]))

    assert result.sources is None


def contract_block() -> str:
    # 표준 라이브러리로 Operations 스키마 블록만 읽는다 (test_business_errors와 같은 방식).
    text = OPENAPI.read_text(encoding="utf-8")
    return text.split("    Operations:\n", 1)[1].split("    ComponentState:\n", 1)[0]


def required_lists(block: str) -> list[set[str]]:
    return [{name.strip() for name in found.split(",")} for found in re.findall(r"required: \[([^\]]*)\]", block)]


def test_response_model_matches_contract_fields():
    block = contract_block()
    source_model = Operations.model_fields["sources"].annotation.__args__[0].__args__[0]
    required = required_lists(block)

    assert set(Operations.model_fields) in required
    assert set(source_model.model_fields) in required
    assert "name: { type: string, minLength: 1, maxLength: 200 }" in block
    assert ("enum: [network, parse, response_limit, source_unavailable, cancelled, invalid_payload, "
            "budget_exhausted, incomplete, configuration, null]") in block
    assert "        sources:\n          type: [array, 'null']" in block
    assert "        limits:\n          type: [object, 'null']" in block


def test_operations_route_is_not_exposed_before_operator_authorization(client):
    # 부적절한 인가: 운영자 권한·MFA(#52) 전에는 경로 자체가 없어야 한다.
    for path in ("/admin/operations", "/api/v1/admin/operations"):
        assert client.get(path).status_code == 404
    assert isinstance(client.app.state.operations_service, OperationsService)


def test_global_daily_limit_constant_is_used_by_redis_script():
    assert "__GLOBAL_DAILY_LIMIT__" not in _ACQUIRE
    assert f"tonumber(v[3]) >= {GLOBAL_DAILY_LIMIT} then" in _ACQUIRE


def test_actual_redis_slot_reading_tracks_count_and_occupancy():
    async def scenario(admission, store, client):
        operations = service(inference_control=admission, slots=BoundSlotReader(store, admission.identity_key_id),
                             timeout_seconds=2.0, clock=utc_now)
        assert (await operations.check()).limits.model_dump() == {
            "inference_today": 0, "inference_daily_limit": GLOBAL_DAILY_LIMIT, "slots_in_use": 0, "slots_total": SHARED_SLOTS}

        started, finish = asyncio.Event(), asyncio.Event()

        async def hold(completion):
            started.set()
            await finish.wait()
            completion.confirm_ended()
            return "ok"

        task = asyncio.create_task(admission.run(identity(), "llm", hold))
        await started.wait()
        during = await operations.check()
        finish.set()
        await task
        after = await operations.check()

        assert (during.limits.inference_today, during.limits.slots_in_use, during.models.llm) == (1, 1, "ok")
        assert (after.limits.inference_today, after.limits.slots_in_use) == (1, 0)

        # 제어 해시의 세대가 바뀌면 숫자를 믿지 않는다.
        await client.hset(store.control_key, "epoch", "changed")
        changed = await operations.check()
        assert changed.limits is None and changed.models.llm == "fail"

    with_redis(scenario)


# --- 출처별 수집 요약 (SQLite·PostgreSQL, 마이그레이션 적용) ---

@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path):
    with ingestion_database(request.param, tmp_path) as (engine, default_source):
        with engine.begin() as db:
            db.execute(delete(Source).where(Source.id == default_source))
        yield engine


def add_source(db, code, *, enabled=True, last_success_at=None):
    source_id = uuid4()
    db.execute(insert(Source), {"id": source_id, "code": code, "name": f"가상 {code}", "base_url": "https://example.org",
                                "enabled": enabled, "last_success_at": last_success_at})
    return source_id


def add_run(db, source_id, minutes, status, code=None):
    started = NOW - timedelta(minutes=minutes)
    db.execute(insert(Run), {"id": uuid4(), "source_id": source_id, "status": status, "started_at": started,
                             "finished_at": None if status == "running" else started + timedelta(seconds=30), "failure_code": code})


def test_repository_counts_failures_since_last_success_and_running(engine):
    with engine.begin() as db:
        source = add_source(db, "a-source", last_success_at=NOW - timedelta(minutes=89))
        add_run(db, source, 120, "failed", "network")
        add_run(db, source, 90, "succeeded")
        add_run(db, source, 60, "failed", "parse")
        add_run(db, source, 30, "failed", "budget_exhausted")
        add_run(db, source, 5, "running")

    [row] = SqlSourceStatusRepository(engine.connect).list()

    assert row.source_id == source
    assert (row.last_finished_status, row.last_failure_code, row.running, row.consecutive_failures) == ("failed", "budget_exhausted", True, 2)
    assert row.last_finished_at == NOW - timedelta(minutes=30) + timedelta(seconds=30)
    assert row.last_success_at == NOW - timedelta(minutes=89)


def test_repository_without_runs_and_without_success(engine):
    with engine.begin() as db:
        fresh = add_source(db, "b-fresh")
        failing = add_source(db, "c-failing")
        add_run(db, failing, 20, "failed", "network")
        add_run(db, failing, 10, "failed", "network")

    rows = {row.source_id: row for row in SqlSourceStatusRepository(engine.connect).list()}

    assert (rows[fresh].last_finished_status, rows[fresh].running, rows[fresh].consecutive_failures) == (None, False, 0)
    assert rows[failing].consecutive_failures == 2


def test_repository_query_count_does_not_grow_with_sources(engine):
    with engine.begin() as db:
        for index in range(5):
            source = add_source(db, f"q-{index}")
            add_run(db, source, 30, "succeeded")
            add_run(db, source, 10, "failed", "network")
    statements = []

    def count(*args):
        statements.append(args)

    event.listen(engine, "before_cursor_execute", count)
    try:
        rows = SqlSourceStatusRepository(engine.connect).list()
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert [row.consecutive_failures for row in rows] == [1] * 5
    assert len(statements) <= 4


def test_repository_excludes_disabled_sources(engine):
    with engine.begin() as db:
        add_source(db, "d-disabled", enabled=False)
        enabled = add_source(db, "e-enabled")

    assert [row.source_id for row in SqlSourceStatusRepository(engine.connect).list()] == [enabled]


def test_repository_refuses_to_truncate_source_list(engine, monkeypatch):
    monkeypatch.setattr("app.modules.operations.repository.MAX_SOURCES", 1)
    with engine.begin() as db:
        add_source(db, "f-one")
        add_source(db, "g-two")

    with pytest.raises(ValueError):
        SqlSourceStatusRepository(engine.connect).list()


# --- 음성 서비스 STT·TTS 개별 준비 상태 ---

def speech_ready(handler) -> dict:
    return asyncio.run(InternalSpeechAdapter(transport=httpx.MockTransport(handler)).model_readiness())


def ready_response(data, status=200, **headers):
    return lambda request: httpx.Response(status, content=json.dumps(data).encode(),
                                          headers={"Content-Type": "application/json", **headers})


@pytest.mark.parametrize(("data", "status", "expected"), [
    ({"protocol_version": 1, "status": "ready", "stt": True, "tts": True}, 200, {"stt": True, "tts": True}),
    ({"protocol_version": 1, "status": "not_ready", "stt": True, "tts": False}, 503, {"stt": True, "tts": False}),
    ({"protocol_version": 1, "status": "not_ready", "stt": False, "tts": True}, 503, {"stt": False, "tts": True}),
    ({"protocol_version": 1, "status": "not_ready", "stt": False, "tts": False}, 503, {"stt": False, "tts": False}),
])
def test_speech_model_readiness_splits_stt_and_tts(data, status, expected):
    assert speech_ready(ready_response(data, status)) == expected


@pytest.mark.parametrize(("data", "status"), [
    ({"protocol_version": 1, "status": "ready", "stt": True, "tts": True}, 503),
    ({"protocol_version": 1, "status": "not_ready", "stt": True, "tts": False}, 200),
    ({"protocol_version": 1, "status": "ready", "stt": True, "tts": False}, 503),
    ({"protocol_version": 2, "status": "ready", "stt": True, "tts": True}, 200),
    ({"protocol_version": True, "status": "ready", "stt": True, "tts": True}, 200),
    ({"protocol_version": 1, "status": "ready", "stt": 1, "tts": 1}, 200),
    ({"protocol_version": 1, "status": "ready", "stt": True, "tts": True, "detail": SECRET}, 200),
    ({"protocol_version": 1, "status": "loading", "stt": False, "tts": False}, 503),
    ([True, True], 200),
    ({"protocol_version": 1, "status": "ready", "stt": True, "tts": True}, 500),
])
def test_speech_model_readiness_rejects_protocol_mismatch(data, status):
    assert speech_ready(ready_response(data, status)) == {"stt": False, "tts": False}


def test_speech_model_readiness_rejects_encoding_media_and_oversize():
    data = {"protocol_version": 1, "status": "ready", "stt": True, "tts": True}
    assert speech_ready(ready_response(data, **{"Content-Encoding": "gzip"})) == {"stt": False, "tts": False}
    assert speech_ready(lambda request: httpx.Response(200, content=json.dumps(data).encode(), headers={"Content-Type": "text/plain"})) == {"stt": False, "tts": False}
    big = dict(data, padding="x" * 5000)
    assert speech_ready(ready_response(big)) == {"stt": False, "tts": False}


def test_speech_model_readiness_connection_error_is_not_ready():
    def refuse(request):
        raise httpx.ConnectError(SECRET)

    assert speech_ready(refuse) == {"stt": False, "tts": False}
