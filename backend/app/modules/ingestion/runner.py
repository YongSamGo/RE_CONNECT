"""한 출처의 제한된 목록/상세 → 정규화 → pending 저장 실행."""

import asyncio
from dataclasses import dataclass
import re

from sqlalchemy import insert, select, text, update

from app.contracts.time import utc_now
from app.modules.ingestion.fetch import FetchRequest, FetchStatus, VOLUNTEER_REGIONS, fetch
from app.modules.ingestion.normalize import Candidate, normalize_items
from app.modules.ingestion.runs import BASE_URLS, DAILY_LIMITS, StopRun
from app.modules.opportunities.ingestion import RecordOpportunity
from app.modules.opportunities.versions import OpportunitySnapshot
from app.modules.opportunities.versions import snapshot_from_row
from app.persistence.operations import IngestionReview, IngestionRun, OpportunityDocument, OpportunityVersion, Source


@dataclass(frozen=True)
class RunResult:
    status: str
    run_id: object = None
    failure_code: str | None = None


class Collector:
    def __init__(self, repository, store_factory, transaction, key, *, clock=utc_now, fetcher=fetch):
        self.repository, self.store_factory, self.transaction = repository, store_factory, transaction
        self.key, self.clock, self.fetcher = key, clock, fetcher

    async def _fetch(self, run, operation, max_requests, **kwargs):
        run.consume(max_requests)
        result = await self.fetcher(FetchRequest(operation=operation, **kwargs), self.key)
        if result.status != FetchStatus.OK:
            code = {FetchStatus.TIMEOUT: "network", FetchStatus.UNAVAILABLE: "network", FetchStatus.TOO_LARGE: "response_limit",
                    FetchStatus.UNSAFE_XML: "parse", FetchStatus.INVALID_RESPONSE: "parse", FetchStatus.CONFIGURATION: "configuration"}.get(result.status, "source_unavailable")
            raise StopRun(code)
        if result.document is None:
            raise StopRun("invalid_payload")
        return result.document

    def _save(self, run, candidate, snapshot):
        with self.transaction() as db:
            self._limits(db)
            return self._save_session(db, run, candidate, snapshot)

    @staticmethod
    def _limits(db):
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = 5000"))
            db.execute(text("SET LOCAL lock_timeout = 1000"))

    def _save_session(self, db, run, candidate, snapshot):
        store = self.store_factory(db)
        result = store.record(RecordOpportunity(source_id=run.source["id"], external_id=candidate.external_id,
            snapshot=snapshot, checked_at=candidate.source_checked_at))
        if result.outcome == "created":
            db.execute(update(IngestionRun).where(IngestionRun.id == run.id).values(created_count=IngestionRun.created_count + 1))
        elif result.outcome in {"changed", "closed"}:
            db.execute(update(IngestionRun).where(IngestionRun.id == run.id).values(changed_count=IngestionRun.changed_count + 1))
        if result.outcome == "stale":
            return result
        # 버전과 검수 메타데이터를 같은 트랜잭션으로 게시한다.
        pending = db.scalar(select(OpportunityVersion.review_status).where(
            OpportunityVersion.opportunity_id == result.opportunity_id, OpportunityVersion.version == result.version).with_for_update())
        if pending != "pending":
            return result
        values = {"review_reasons": list(candidate.review_reasons), "unmapped_fields": [list(v) for v in candidate.unmapped_fields]}
        exists = db.scalar(select(IngestionReview.version).where(IngestionReview.opportunity_id == result.opportunity_id, IngestionReview.version == result.version))
        if exists is None:
            db.execute(insert(IngestionReview), {"opportunity_id": result.opportunity_id, "version": result.version, **values})
        else:
            db.execute(update(IngestionReview).where(IngestionReview.opportunity_id == result.opportunity_id, IngestionReview.version == result.version).values(**values))
        return result

    def _hold_existing(self, run, identifier):
        # 성공한 원문이 기존 공고와 맞지 않으면 이전 공개본은 보존하되 추천/생성은 검수 대기로 둔다.
        with self.transaction() as db:
            self._limits(db)
            db.scalar(select(Source.id).where(Source.id == run.source["id"]).with_for_update())
            row = db.execute(select(OpportunityVersion.__table__).join(OpportunityDocument,
                OpportunityVersion.opportunity_id == OpportunityDocument.id).where(
                OpportunityDocument.source_id == run.source["id"], OpportunityDocument.external_id == identifier
                ).order_by(OpportunityVersion.version.desc()).limit(1)).mappings().one_or_none()
            if row is None or row["recruitment_status"] != "open":
                return
            snapshot = snapshot_from_row(row)
            # 복사한 값은 이전 검증본이다. 현재 원문을 검증했다고 주장하거나 임의 마감으로 바꾸지 않는다.
            snapshot = OpportunitySnapshot.model_validate({**snapshot.model_dump(), "recruitment_status": "unknown"})
            candidate = Candidate(identifier, snapshot, snapshot.description_truncated, self.clock(),
                                  ("normalization_held_prior_content",))
            result = self._save_session(db, run, candidate, snapshot)
        if result.outcome in {"changed", "closed"}:
            run.counts.changed_count += 1

    async def run(self, source_id, *, max_requests=25, max_pages=10, rows=10, due=False):
        if not 1 <= max_requests <= 10000 or not 1 <= max_pages <= 100 or not 1 <= rows <= 100:
            raise ValueError("수집 실행 범위 오류")
        with self.repository.acquire(source_id, due=due) as run:
            if run is None:
                return RunResult("skipped")
            try:
                source = run.source["code"]
                if source not in DAILY_LIMITS or run.source["base_url"] != BASE_URLS[source] or not self.key.get_secret_value().strip():
                    raise StopRun("configuration")
                async with asyncio.timeout(600):
                    for _ in range(max_pages):
                        page = run.page
                        region = VOLUNTEER_REGIONS[run.region_index] if source == "volunteer" else None
                        document = await self._fetch(run, source + "_list", max_requests,
                                                     page_no=page, num_rows=rows, region_code=region)
                        items = document.root.findall("body/items/item")
                        run.counts.fetched_count += len(items)
                        run.progress()
                        expected = min(rows, max(0, document.total_count - (page - 1) * rows))
                        if len(items) != expected:
                            raise StopRun("invalid_payload")
                        seen = set()
                        for item in items:
                            values = item.findall("jobId" if source == "senuri" else "progrmRegistNo")
                            identifier = values[0].text if len(values) == 1 else None
                            pattern = r"[A-Z0-9]{1,30}" if source == "senuri" else r"[0-9]{1,12}"
                            if not isinstance(identifier, str) or re.fullmatch(pattern, identifier) is None or identifier in seen:
                                run.reject("invalid_identifier")
                                continue
                            seen.add(identifier)
                            detail = await self._fetch(run, source + "_detail", max_requests, external_id=identifier)
                            details = detail.root.findall("body/items/item")
                            if len(details) != 1:
                                raise StopRun("invalid_payload")
                            normalized = normalize_items(source, item, details[0], checked_at=self.clock())
                            if normalized.status != "candidate":
                                self._hold_existing(run, identifier)
                                run.reject(normalized.reason)
                                continue
                            candidate = normalized.candidate
                            if candidate is None or candidate.external_id != identifier or candidate.review_status != "pending":
                                raise StopRun("invalid_payload")
                            snapshot = OpportunitySnapshot.model_validate({**candidate.content.model_dump(), "description_truncated": candidate.description_truncated})
                            result = self._save(run, candidate, snapshot)
                            if result.outcome == "created":
                                run.counts.created_count += 1
                            elif result.outcome in {"changed", "closed"}:
                                run.counts.changed_count += 1
                        if page * rows >= document.total_count:
                            if source == "volunteer" and run.region_index < len(VOLUNTEER_REGIONS) - 1:
                                run.checkpoint(1, region_index=run.region_index + 1)
                                continue
                            run.checkpoint(1, region_index=0)
                            run.finish()
                            return RunResult("succeeded", run.id)
                        run.checkpoint(page + 1)
                    raise StopRun("incomplete")
            except asyncio.CancelledError:
                run.finish("cancelled")
                raise
            except StopRun as exc:
                run.finish(exc.code)
                return RunResult("failed", run.id, exc.code)
            except TimeoutError:
                run.finish("cancelled")
                return RunResult("failed", run.id, "cancelled")
            except Exception:
                run.finish("source_unavailable")
                return RunResult("failed", run.id, "source_unavailable")
