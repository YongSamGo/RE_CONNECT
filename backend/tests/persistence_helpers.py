"""가상 공고의 최소 저장 그래프. 운영 데이터·연결 정보는 사용하지 않는다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import insert

from app.contracts.opportunity import OpportunityContent
from app.persistence import OpportunityDocument, OpportunityVersion, Source
from tests.test_contracts import opportunity

NOW = datetime(2026, 10, 17, tzinfo=UTC)
OPPORTUNITY_ID = UUID("b54ad372-bab6-4cb5-b0d6-0a809ab60b28")


def opportunity_values(opportunity_id=OPPORTUNITY_ID, version=1, **updates):
    content = OpportunityContent.model_validate(opportunity())
    values = content.model_dump(mode="json")
    region = values.pop("activity_region")
    return {
        **values, "activity_province": region["province"], "activity_district": region["district"],
        "deadline_date": content.deadline_date, "deadline_at": content.deadline_at,
        "opportunity_id": opportunity_id, "version": version, "description_truncated": False,
        "review_status": "pending", "source_checked_at": NOW, "reviewed_at": None,
        "content_hash": "a" * 64, **updates,
    }


def seed_opportunity(db, *, opportunity_id=OPPORTUNITY_ID, external_id="fictional-external"):
    source_id = uuid4()
    db.execute(insert(Source), {"id": source_id, "code": "fictional-source", "name": "가상 출처", "base_url": "https://example.org/api"})
    db.execute(insert(OpportunityDocument), {"id": opportunity_id, "source_id": source_id, "external_id": external_id})
    db.execute(insert(OpportunityVersion), opportunity_values(opportunity_id))
    return source_id, opportunity_id
