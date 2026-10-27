"""운영 상태용 출처별 수집 요약 조회. 공고·개인 본문은 읽지 않는다.

출처 수와 관계없이 쿼리 4번으로 끝낸다. 장애 중에도 상태 확인 제한시간 안에 답하기 위해서다.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, or_, select

from app.persistence.operations import IngestionRun as Run, Source

# 운영 화면에 보여 줄 수 있는 출처 수. 넘으면 잘라 보여 주지 않고 조회 실패로 본다.
MAX_SOURCES = 100


@dataclass(frozen=True)
class SourceRunSummary:
    source_id: UUID
    name: str
    last_success_at: datetime | None
    # 마지막으로 끝난 실행. 실행 중인 것은 `running`으로 따로 센다.
    last_finished_status: str | None
    last_failure_code: str | None
    last_finished_at: datetime | None
    running: bool
    # 마지막 성공 이후 끝난 실패 실행 수. 성공이 없으면 전체 실패 수.
    consecutive_failures: int


class SqlSourceStatusRepository:
    def __init__(self, connect):
        self.connect = connect

    def list(self) -> list[SourceRunSummary]:
        with self.connect() as db:
            sources = db.execute(
                select(Source.id, Source.name, Source.last_success_at)
                .where(Source.enabled.is_(True))
                .order_by(Source.code)
                .limit(MAX_SOURCES + 1)
            ).all()
            if len(sources) > MAX_SOURCES:
                raise ValueError("운영 상태로 보여 줄 출처 수를 넘었습니다")
            if not sources:
                return []
            ids = [source.id for source in sources]
            of_sources = Run.source_id.in_(ids)

            totals = (
                select(
                    Run.source_id,
                    func.max(case((Run.status == "succeeded", Run.started_at))).label("last_succeeded"),
                    func.max(case((Run.status == "running", 1), else_=0)).label("running"),
                )
                .where(of_sources)
                .group_by(Run.source_id)
                .subquery()
            )
            running = {row.source_id: bool(row.running) for row in db.execute(select(totals.c.source_id, totals.c.running))}

            failures = dict(db.execute(
                select(Run.source_id, func.count())
                .join(totals, totals.c.source_id == Run.source_id)
                .where(of_sources, Run.status == "failed",
                       or_(totals.c.last_succeeded.is_(None), Run.started_at > totals.c.last_succeeded))
                .group_by(Run.source_id)
            ).all())

            ordered = (
                select(
                    Run.source_id, Run.status, Run.failure_code, Run.finished_at,
                    func.row_number().over(partition_by=Run.source_id, order_by=(Run.started_at.desc(), Run.id.desc())).label("position"),
                )
                .where(of_sources, Run.status != "running")
                .subquery()
            )
            latest = {
                row.source_id: row
                for row in db.execute(
                    select(ordered.c.source_id, ordered.c.status, ordered.c.failure_code, ordered.c.finished_at)
                    .where(ordered.c.position == 1)
                )
            }

        summaries = []
        for source in sources:
            last = latest.get(source.id)
            summaries.append(SourceRunSummary(
                source_id=source.id,
                name=source.name,
                last_success_at=source.last_success_at,
                last_finished_status=last.status if last is not None else None,
                last_failure_code=last.failure_code if last is not None else None,
                last_finished_at=last.finished_at if last is not None else None,
                running=running.get(source.id, False),
                consecutive_failures=failures.get(source.id, 0),
            ))
        return summaries
