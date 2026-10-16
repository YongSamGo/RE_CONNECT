"""공개 포인터만 읽는 실제 DB 목록/상세·검색·마감 경계."""

from contextlib import nullcontext
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import insert

from app.core.config import Settings
from app.main import create_app
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import OpportunitySearch, PublicOpportunityService
from app.persistence import Base, OpportunityDocument, OpportunityPublication, OpportunityVersion, Source
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import NOW, open_test_database, opportunity_values


def seeded(db):
    Base.metadata.create_all(db)
    source = uuid4()
    db.execute(insert(Source), {"id": source, "code": "fictional-public", "name": "가상 출처", "base_url": "https://example.org"})
    def add(number, *, public=True, version=1, **changes):
        id = UUID(int=number)
        db.execute(insert(OpportunityDocument), {"id": id, "source_id": source, "external_id": str(number)})
        values = opportunity_values(id, version, **{"review_status": "approved" if public else "pending", "reviewed_at": NOW if public else None, "deadline_date": None, "deadline_at": None, **changes})
        db.execute(insert(OpportunityVersion), values)
        if public:
            db.execute(insert(OpportunityPublication), {"opportunity_id": id, "version": version})
        return id
    return add


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_public_pointer_deadline_unknown_hidden_and_internal_field_boundaries(backend):
    with open_test_database(backend) as db:
        add = seeded(db)
        live = add(1)
        unknown = add(2, recruitment_status="unknown")
        closed = add(3, recruitment_status="closed")
        dated = add(4, deadline_date=(NOW - timedelta(days=1)).date())
        timed = add(5, deadline_at=NOW)
        private = add(6, public=False)
        same_day = add(7, deadline_date=(NOW + timedelta(hours=9)).date())
        future = add(8, deadline_at=NOW + timedelta(seconds=1))
        stale = add(9, source_checked_at=NOW - timedelta(hours=49))
        hidden = add(10, public=False, review_status="hidden")
        rejected = add(11, public=False, review_status="rejected")
        db.execute(insert(OpportunityVersion), opportunity_values(live, 2, title="공개하면 안 되는 새 검수 원문"))
        repository = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        page = repository.list(OpportunitySearch(), NOW)
        assert {item.id for item in page.items} == {live, unknown, same_day, future, stale}
        detail = repository.get(live, NOW)
        assert detail.version == 1 and detail.change_pending
        assert detail.title != "공개하면 안 되는 새 검수 원문"
        assert repository.get(private, NOW) is None
        assert repository.get(hidden, NOW) is None and repository.get(rejected, NOW) is None
        assert repository.get(uuid4(), NOW) is None
        for id in (closed, dated, timed):
            assert repository.get(id, NOW).recruitment_status == "closed"
        assert repository.get(unknown, NOW).recruitment_status == "unknown"
        fields = set(detail.model_dump())
        assert not fields & {"source_id", "external_id", "content_hash", "review_status", "opportunity_id"}
        db.execute(OpportunityPublication.__table__.delete().where(OpportunityPublication.opportunity_id == live))
        assert repository.get(live, NOW) is None


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_deadline_order_uses_kst_day_precise_time_then_stable_id_and_nulls_last(backend):
    with open_test_database(backend) as db:
        add = seeded(db)
        # UTC 16시는 다음 한국 날짜다. 날짜만 있는 같은 날은 시각을 꾸며 내보내지 않는다.
        date_only = add(2, deadline_date=(NOW + timedelta(days=1)).date())
        earlier = add(4, deadline_at=NOW + timedelta(hours=16))
        later = add(3, deadline_at=NOW + timedelta(hours=17))
        tied = add(5, deadline_at=NOW + timedelta(hours=17))
        no_deadline = add(1)
        repository = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        page = repository.list(OpportunitySearch(), NOW)
        assert [value.id for value in page.items] == [earlier, later, tied, date_only, no_deadline]
        assert repository.get(date_only, NOW).deadline_at is None


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_literal_bound_search_tags_roles_filters_and_page_order(backend):
    with open_test_database(backend) as db:
        add = seeded(db)
        ids = [add(i, title=f"가상 공고 {i}", activity_province="seoul", activity_district="yongsan", deadline_date=(NOW + timedelta(days=i)).date()) for i in range(1, 25)]
        add(25, title="100%_지원", organization_name="가상기관", activity_province="gyeonggi", activity_district="suwon", skill_tags=["길찾기"], role_tags=["guide_role"], description_text="교통 안내")
        db.execute(insert(RoleDefinition), {"id": "guide_role", "name": "길안내 역할", "description": "가상 역할", "skill_tags": [], "aliases": [], "experience_rules": []})
        repository = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        first = repository.list(OpportunitySearch(page_size=20), NOW)
        assert first.total == 25 and [item.id for item in first.items] == ids[:20]
        second = repository.list(OpportunitySearch(page=2), NOW)
        assert [item.id for item in second.items] == ids[20:] + [UUID(int=25)]
        assert repository.list(OpportunitySearch(page=10**30), NOW).items == []
        for q in ("100%_", "가상기관", "길찾기", "guide_role", "교통 안내", "길안내 역할"):
            page = repository.list(OpportunitySearch(q=q), NOW)
            assert [item.id for item in page.items] == [UUID(int=25)]
        for q in ("' OR 1=1 --", "\\", "[", '"'):
            assert repository.list(OpportunitySearch(q=q), NOW).total == 0
        assert repository.list(OpportunitySearch(q="%_"), NOW).total == 1
        assert repository.list(OpportunitySearch(province="seoul", district="yongsan"), NOW).total == 24
        assert repository.list(OpportunitySearch(province="gyeonggi", district="suwon"), NOW).total == 1
        employment_count = repository.list(OpportunitySearch(activity_type="employment"), NOW).total
        volunteering_count = repository.list(OpportunitySearch(activity_type="volunteering"), NOW).total
        assert employment_count + volunteering_count == 25


@pytest.mark.parametrize("query", ["district=yongsan", "province=seoul&district=suwon", "q=", "q=%20", "q=" + "x" * 101, "page=0", "page_size=21", "activity_type=other", "owner_id=other", "q=%E2%80%AE"], ids=["province-required", "district-mismatch", "empty", "blank", "long", "page", "size", "type", "extra", "hidden"])
def test_http_rejects_invalid_filters_before_database(query):
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get("/api/v1/opportunities?" + query)
        assert response.status_code == 422 and response.json()["code"] == "VALIDATION_FAILED"
        if query == "district=yongsan":
            assert response.json()["fields"] == [{"path": "province", "reason": "required_with"}]


def test_database_failure_is_safe_503_and_invalid_id_is_422():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/opportunities").status_code == 503
        assert client.get("/api/v1/opportunities/" + str(uuid4())).status_code == 503
        assert client.get("/api/v1/opportunities/not-a-uuid").status_code == 422


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_database_http_survives_unavailable_ai_redis_and_returns_contract(backend):
    with open_test_database(backend) as db:
        add = seeded(db)
        id = add(1)
        repository = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        app = create_app(Settings(_env_file=None))
        app.state.opportunity_service = PublicOpportunityService(repository)
        with TestClient(app) as client:
            response = client.get("/api/v1/opportunities")
            assert response.status_code == 200 and response.json()["total"] == 1
            assert response.headers["cache-control"] == "no-store"
            response = client.get("/api/v1/opportunities/" + str(id))
            assert response.status_code == 200 and response.json()["id"] == str(id)
            assert response.json()["source_url"].startswith("https://")
            assert "review_status" not in response.json() and "set-cookie" not in response.headers
            missing = client.get("/api/v1/opportunities/" + str(uuid4()))
            assert missing.status_code == 404 and missing.json()["code"] == "NOT_FOUND"
