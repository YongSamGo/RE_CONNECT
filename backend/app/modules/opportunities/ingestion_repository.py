"""짧은 DB 트랜잭션의 source→document 잠금 순서로 수집 버전을 직렬화한다."""

from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.opportunities.ingestion import RecordOpportunity, RecordResult
from app.modules.opportunities.versions import changed_fields, content_hash, snapshot_from_row
from app.persistence.operations import Source, OpportunityDocument as D, OpportunityVersion as V, OpportunityPublication as P


def pending_version_values(snapshot, checked_at, opportunity_id, version, *, observed_hash=None):
    """새 검수 대기 버전 행. 수집·수동 입력·운영자 수정이 같은 규칙으로 만든다.

    observed_hash는 이 버전의 근거가 된 원문 관측의 해시다. 생략하면 이 내용 자체가 관측 결과다.
    """
    values = snapshot.model_dump(mode="json")
    region = values.pop("activity_region")
    return {
        **values, "activity_province": region["province"] if region else None,
        "activity_district": region["district"] if region else None,
        "deadline_date": snapshot.deadline_date, "deadline_at": snapshot.deadline_at,
        "opportunity_id": opportunity_id, "version": version, "review_status": "pending",
        "reviewed_at": None, "source_checked_at": checked_at,
        "content_hash": content_hash(snapshot), "observed_hash": observed_hash or content_hash(snapshot),
        "created_at": utc_now(),
    }


class SqlIngestionRepository:
    def __init__(self, transaction):
        self.transaction = transaction

    @staticmethod
    def _values(command, opportunity_id, version, observed_hash=None):
        return pending_version_values(command.snapshot, command.checked_at, opportunity_id, version, observed_hash=observed_hash)

    @staticmethod
    def _manual_candidates(db, command):
        content = command.snapshot
        return db.scalars(select(D.id).join(V, V.opportunity_id == D.id).where(
            D.source_id == command.source_id, D.external_id.is_(None),
            V.source_url == content.source_url, V.organization_name == content.organization_name,
            V.title == content.title, V.deadline_date.is_not_distinct_from(content.deadline_date),
            V.deadline_at.is_not_distinct_from(content.deadline_at),
        ).distinct().limit(2)).all()

    def record(self, command: RecordOpportunity) -> RecordResult:
        try:
            with self.transaction() as db:
                # 외부 I/O를 잠금 안에서 하지 않는다. 같은 출처의 생성·수정·수동 대조를 함께 보호한다.
                source = db.scalar(select(Source.id).where(Source.id == command.source_id).with_for_update())
                if source is None:
                    raise AppError("NOT_FOUND")
                if command.external_id is not None:
                    document = db.execute(select(D.__table__).where(D.source_id == source, D.external_id == command.external_id).with_for_update()).mappings().one_or_none()
                elif command.manual_target is not None:
                    document = db.execute(select(D.__table__).where(D.id == command.manual_target, D.source_id == source, D.external_id.is_(None)).with_for_update()).mappings().one_or_none()
                    if document is None:
                        raise AppError("NOT_FOUND")
                else:
                    if self._manual_candidates(db, command):
                        # 모집 시작일이 계약에 없으므로 같은 후보를 자동 병합하지 않는다.
                        # 운영자가 기존 자료/기간을 대조하고 manual_target을 명시해야 한다.
                        raise AppError("VERSION_CONFLICT")
                    document = None
                if document is None:
                    id = uuid4()
                    db.execute(insert(D), {"id": id, "source_id": source, "external_id": command.external_id})
                    db.execute(insert(V), self._values(command, id, 1))
                    return RecordResult(id, 1, "created")
                id = document["id"]
                latest = db.execute(select(V.__table__).where(V.opportunity_id == id).order_by(V.version.desc()).limit(1)).mappings().one_or_none()
                if latest is None:
                    raise AppError("SERVICE_UNAVAILABLE")
                if command.checked_at < latest["source_checked_at"]:
                    return RecordResult(id, latest["version"], "stale")
                before = snapshot_from_row(latest)
                # 원문 관측이 그대로면 운영자가 고친 최신 버전(지역·조건 등)을 수집 결과로 되돌리지 않는다.
                observed = content_hash(command.snapshot)
                if observed == latest["observed_hash"]:
                    if latest["recruitment_status"] == command.snapshot.recruitment_status:
                        db.execute(update(V).where(V.opportunity_id == id, V.version == latest["version"]).values(source_checked_at=command.checked_at))
                        return RecordResult(id, latest["version"], "unchanged")
                    if command.snapshot.recruitment_status != "closed":
                        # 종료만 반영된 뒤 같은 원문으로 다시 열렸다. 닫힘→열림은 재검수 대상이므로 새 pending 버전을
                        # 만들되, 내용은 운영자 수정본에 모집 상태만 바꾼다(수집 원문으로 되돌리지 않는다).
                        if command.checked_at == latest["source_checked_at"]:
                            raise AppError("VERSION_CONFLICT")
                        reopened = before.model_copy(update={"recruitment_status": command.snapshot.recruitment_status})
                        version = latest["version"] + 1
                        db.execute(insert(V), pending_version_values(reopened, command.checked_at, id, version, observed_hash=observed))
                        return RecordResult(id, version, "changed")
                # 원문에서 모집 상태만 종료로 바뀌었으면 새 버전 없이 종료만 반영한다(운영자 수정본 유지).
                # 종료를 반영한 뒤에도 관측 해시는 종료 전 원문 그대로라, 관측 당시 상태를 모두 대입해 비교한다.
                status_only = command.snapshot.recruitment_status == "closed" and any(
                    content_hash(command.snapshot.model_copy(update={"recruitment_status": status})) == latest["observed_hash"]
                    for status in ("open", "unknown"))
                if command.external_id is not None:
                    # 수집기는 태그를 만들지 않는다(빈 목록). 운영자가 수정으로 붙인 태그를 이어받아
                    # 다음 수집이 태그를 지우는 새 버전을 만들지 않게 한다. 수동 입력은 태그를 직접 정한다.
                    inherited = command.snapshot.model_copy(update={"role_tags": before.role_tags, "skill_tags": before.skill_tags})
                    command = command.model_copy(update={"snapshot": inherited})
                changes = changed_fields(before, command.snapshot)
                if changes and command.checked_at == latest["source_checked_at"]:
                    raise AppError("VERSION_CONFLICT")
                # 닫는 방향은 기존 공개본에도 즉시 반영한다. 검수 시각·본문·해시는 바꾸지 않는다.
                if command.snapshot.recruitment_status == "closed":
                    public_version = db.scalar(select(P.version).where(P.opportunity_id == id))
                    versions = {latest["version"]}
                    if public_version is not None:
                        versions.add(public_version)
                    db.execute(update(V).where(V.opportunity_id == id, V.version.in_(versions)).values(recruitment_status="closed", source_checked_at=command.checked_at))
                if status_only or not changes or changes == {"recruitment_status"} and command.snapshot.recruitment_status == "closed":
                    db.execute(update(V).where(V.opportunity_id == id, V.version == latest["version"]).values(source_checked_at=command.checked_at))
                    return RecordResult(id, latest["version"], "closed" if changes or status_only else "unchanged")
                version = latest["version"] + 1
                db.execute(insert(V), self._values(command, id, version, observed))
                return RecordResult(id, version, "changed")
        except (SQLAlchemyError, ValidationError):
            raise AppError("SERVICE_UNAVAILABLE") from None
