"""운영 상태용 출처별 수집 요약 조회. 공고·개인 본문은 읽지 않는다."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

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
            return [self._summary(db, source) for source in sources]

    @staticmethod
    def _summary(db, source) -> SourceRunSummary:
        of_source = Run.source_id == source.id
        latest = db.execute(
            select(Run.status, Run.failure_code, Run.finished_at)
            .where(of_source, Run.status != "running")
            .order_by(Run.started_at.desc(), Run.id.desc())
            .limit(1)
        ).one_or_none()
        running = db.scalar(select(func.count()).select_from(Run).where(of_source, Run.status == "running")) > 0
        last_succeeded = db.scalar(select(func.max(Run.started_at)).where(of_source, Run.status == "succeeded"))
        failures = select(func.count()).select_from(Run).where(of_source, Run.status == "failed")
        if last_succeeded is not None:
            failures = failures.where(Run.started_at > last_succeeded)
        return SourceRunSummary(
            source_id=source.id,
            name=source.name,
            last_success_at=source.last_success_at,
            last_finished_status=latest.status if latest is not None else None,
            last_failure_code=latest.failure_code if latest is not None else None,
            last_finished_at=latest.finished_at if latest is not None else None,
            running=running,
            consecutive_failures=db.scalar(failures),
        )
