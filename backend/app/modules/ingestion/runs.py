"""PostgreSQL 세션 잠금과 출처별 영속 예산. 네트워크 I/O 동안 DB 트랜잭션은 열지 않는다."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
from uuid import uuid4

from sqlalchemy import case, insert, select, text, update

from app.contracts.time import kst_date, to_utc
from app.persistence.operations import IngestionRun as Run, IngestionState as State, Source


DAILY_LIMITS = {"senuri": 10000, "volunteer": 1000}
BASE_URLS = {"senuri": "https://apis.data.go.kr/B552474/SenuriService",
             "volunteer": "https://apis.data.go.kr/1741000/volunteerPartcptnService"}


class StopRun(Exception):
    def __init__(self, code):
        if code not in {"network", "parse", "response_limit", "source_unavailable", "cancelled", "invalid_payload", "budget_exhausted", "incomplete", "configuration"}:
            raise ValueError("수집 실패 코드 오류")
        self.code = code
        super().__init__(code)


@dataclass
class Counts:
    fetched_count: int = 0
    created_count: int = 0
    changed_count: int = 0
    rejected_count: int = 0
    request_count: int = 0
    rejection_counts: dict = field(default_factory=dict)


class SqlRun:
    def __init__(self, connection, source, run_id, state, clock):
        self.connection, self.source, self.id, self.clock = connection, source, run_id, clock
        self.page = state["next_page"]
        self.region_index = state["region_index"]
        self.counts = Counts()

    def consume(self, max_requests):
        now = to_utc(self.clock())
        if self.counts.request_count >= max_requests:
            raise StopRun("budget_exhausted")
        with self.connection.begin():
            enabled = self.connection.scalar(select(Source.enabled).where(Source.id == self.source["id"]))
            if not enabled:
                raise StopRun("source_unavailable")
            state = self.connection.execute(select(State.__table__).where(State.source_id == self.source["id"])).mappings().one()
            today = kst_date(now)
            if today < state["quota_date"]:
                raise StopRun("configuration")
            used = state["request_count"] if today == state["quota_date"] else 0
            if used >= DAILY_LIMITS[self.source["code"]]:
                raise StopRun("budget_exhausted")
            self.connection.execute(update(State).where(State.source_id == self.source["id"]).values(quota_date=today, request_count=used + 1))
            # 요청 전에 commit한다. 중단된 요청도 한도에서 다시 돌려주지 않는다.
            self.connection.execute(update(Run).where(Run.id == self.id).values(request_count=self.counts.request_count + 1))
        self.counts.request_count += 1

    def progress(self):
        with self.connection.begin():
            self.connection.execute(update(Run).where(Run.id == self.id).values(**vars(self.counts)))

    def reject(self, code):
        allowed = {"invalid_identifier", "invalid_item_structure", "invalid_source_value", "hidden_characters", "invalid_date", "invalid_date_range", "outside_region", "official_link_unknown", "application_method_unknown", "not_senior_target", "required_field_missing", "invalid_contract", "mapping_value_too_long", "detail_missing", "identifier_mismatch", "unsupported_source"}
        code = code if code in allowed else "invalid_payload"
        self.counts.rejected_count += 1
        self.counts.rejection_counts[code] = self.counts.rejection_counts.get(code, 0) + 1
        self.progress()

    def checkpoint(self, page, *, region_index=None):
        region_index = self.region_index if region_index is None else region_index
        with self.connection.begin():
            self.connection.execute(update(State).where(State.source_id == self.source["id"]).values(
                next_page=page, region_index=region_index))
        self.page = page
        self.region_index = region_index

    def finish(self, code=None):
        now = to_utc(self.clock())
        with self.connection.begin():
            started = self.connection.scalar(select(Run.started_at).where(Run.id == self.id))
            now = max(now, started)
            self.connection.execute(update(Run).where(Run.id == self.id).values(
                status="succeeded" if code is None else "failed", failure_code=code, finished_at=now,
                **vars(self.counts)))
            self.connection.execute(update(State).where(State.source_id == self.source["id"]).values(
                next_run_at=now + (timedelta(hours=6) if code is None else timedelta(minutes=15))))
            if code is None:
                previous = self.connection.scalar(select(Source.last_success_at).where(Source.id == self.source["id"]))
                self.connection.execute(update(Source).where(Source.id == self.source["id"]).values(last_success_at=max(now, previous) if previous else now))


class RunRepository:
    def __init__(self, engine, clock):
        if engine.dialect.name != "postgresql":
            raise ValueError("실행 잠금은 PostgreSQL에서만 지원합니다")
        self.engine, self.clock = engine, clock

    @contextmanager
    def acquire(self, source_id, *, due=False):
        connection = self.engine.connect()
        key = int.from_bytes(hashlib.sha256(b"reconnect:ingestion:" + source_id.bytes).digest()[:8], "big", signed=True)
        locked = False
        try:
            with connection.begin():
                connection.execute(text("SET statement_timeout = 5000"))
                connection.execute(text("SET lock_timeout = 1000"))
                locked = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if not locked:
                yield None
                return
            now = to_utc(self.clock())
            with connection.begin():
                source = connection.execute(select(Source.__table__).where(Source.id == source_id)).mappings().one_or_none()
                if source is None or not source["enabled"]:
                    yield None
                    return
                state = connection.execute(select(State.__table__).where(State.source_id == source_id)).mappings().one_or_none()
                if state is None:
                    next_run = source["last_success_at"] + timedelta(hours=6) if source["last_success_at"] else None
                    connection.execute(insert(State), {"source_id": source_id, "quota_date": kst_date(now), "request_count": 0, "next_page": 1, "next_run_at": next_run})
                    state = {"next_page": 1, "region_index": 0, "next_run_at": next_run}
                if due and state["next_run_at"] is not None and state["next_run_at"] > now:
                    yield None
                    return
                # 같은 세션 잠금을 얻었으므로 과거 running은 소유 연결이 이미 종료된 실행이다.
                connection.execute(update(Run).where(Run.source_id == source_id, Run.status == "running").values(
                    status="failed", failure_code="cancelled", finished_at=case((Run.started_at > now, Run.started_at), else_=now)))
                run_id = uuid4()
                connection.execute(insert(Run), {"id": run_id, "source_id": source_id, "status": "running", "started_at": now})
            yield SqlRun(connection, source, run_id, state, self.clock)
        finally:
            # 예외·취소·unlock 실패 시에도 pool로 잠금 세션을 돌려주지 않는다.
            connection.invalidate()
            connection.close()
