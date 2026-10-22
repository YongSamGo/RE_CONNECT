"""자격의 OR 전체 판정·선택 필터의 교집합·검수/신선도 경계."""

from contextlib import nullcontext
from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError
import pytest
from sqlalchemy import insert

from app.contracts.profile import ProfileContent, empty_profile_content
from app.contracts.recommendation import RecommendationFilters
from app.modules.opportunities.repository import SqlPublicOpportunityRepository
from app.modules.opportunities.service import PublicOpportunity
from app.modules.recommendations.service import filter_candidates
from app.persistence import OpportunityVersion
from tests.persistence_helpers import NOW, open_test_database, opportunity_values
from tests.test_contracts import opportunity
from tests.test_public_opportunities import seeded


def profile(**changes):
    return ProfileContent.model_validate({**empty_profile_content().model_dump(),
        "experiences": [{"id": uuid4(), "description": "가상 낭독 경험", "duration_note": None, "skill_tags": ["낭독"]}],
        "preferred_regions": [{"province": "seoul", "district": None}], "activity_types": ["volunteering"], **changes})


def public(**changes):
    return PublicOpportunity.model_validate({**opportunity(), "id": uuid4(), "version": 1,
        "activity_type": "volunteering", "activity_region": {"province": "seoul", "district": "yongsan"},
        "requirements": [], "deadline_at": None, "deadline_date": None, "recruitment_status": "open",
        "source_checked_at": NOW, "reviewed_at": NOW, "change_pending": False, "description_truncated": False, **changes})


def selected(*items, person=None, excluded=frozenset(), **filters):
    return filter_candidates(person or profile(), list(items), RecommendationFilters.model_validate(filters), excluded, NOW)


@pytest.mark.parametrize("changes", [
    {"change_pending": True}, {"recruitment_status": "unknown"}, {"recruitment_status": "closed"},
    {"deadline_at": NOW}, {"deadline_date": (NOW - timedelta(days=1)).date()},
    {"source_checked_at": NOW - timedelta(hours=48, microseconds=1)},
    {"source_checked_at": NOW + timedelta(microseconds=1)},
    {"activity_type": "employment"}, {"activity_region": None, "remote_allowed": None},
    {"activity_region": {"province": "incheon", "district": None}, "remote_allowed": False},
])
def test_mandatory_candidate_conditions_are_not_relaxed(changes):
    assert selected(public(**changes)) == []


def test_freshness_exact_boundary_remote_and_date_only_deadline_are_kept():
    assert selected(public(source_checked_at=NOW - timedelta(hours=48)))
    assert selected(public(activity_region=None, remote_allowed=True))
    assert selected(public(deadline_date=NOW.date()))


def test_optional_filters_intersect_with_profile_and_unknown_values_do_not_match():
    item = public(paid=True)
    assert not selected(item, activity_types=["employment"])
    assert not selected(item, regions=[{"province": "gyeonggi", "district": None}])
    assert not selected(item, paid=False)
    assert not selected(item, person=profile(paid_preference="unpaid"), paid=True)
    assert not selected(public(paid=None), paid=False)
    assert selected(item, regions=[{"province": "seoul", "district": "yongsan"}], paid=True)
    assert not selected(public(activity_region={"province": "seoul", "district": None}),
                        person=profile(preferred_regions=[{"province": "seoul", "district": "yongsan"}]))


def test_any_excluded_role_removes_complex_role_opportunity_but_not_public_search():
    item = public(role_tags=["reading_companion", "library_assistant"])
    assert not selected(item, excluded=frozenset({"library_assistant"}))
    assert selected(item)
    assert item.role_tags == ["reading_companion", "library_assistant"]


def certification(value, *, group=None, clarity="clear"):
    return {"id": str(uuid4()), "field": "certification", "operator": "has_all", "value": [value],
            "source_evidence": "가상 원문의 자격 조건", "clarity": clarity, "reference_date": None,
            "group_id": str(group) if group else None, "group_operator": "or" if group else None}


def test_or_group_satisfaction_is_kept_and_only_overall_failure_is_removed():
    group = uuid4()
    conditions = [certification("가상자격A", group=group), certification("가상자격B", group=group)]
    person = profile(certifications=["가상자격A"])
    kept = selected(public(requirements=conditions), person=person)
    assert kept[0].eligibility.overall == "satisfied"
    assert any(c.status == "not_satisfied" for c in kept[0].eligibility.conditions)
    assert not selected(public(requirements=[certification("가상자격B")]), person=person)
    unknown = selected(public(requirements=[certification("가상자격B")]))
    assert unknown[0].eligibility.overall == "unknown"
    assert selected(public())[0].eligibility.no_requirements


@pytest.mark.parametrize("filters", [
    {"activity_types": []}, {"activity_types": ["volunteering", "volunteering"]},
    {"regions": []}, {"paid": "false"}, {"paid": 0}, {"paid": None}, {"regions": None},
    {"activity_types": None}, {"owner_id": str(uuid4())},
])
def test_invalid_filters_are_rejected(filters):
    with pytest.raises(ValidationError):
        RecommendationFilters.model_validate(filters)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_sql_candidates_follow_approved_pointer_and_material_pending_fields(backend):
    with open_test_database(backend) as db:
        add = seeded(db)
        title_only = add(1)
        material = add(2)
        add(3, public=False)
        add(4, recruitment_status="unknown")
        add(5, source_checked_at=NOW - timedelta(hours=49))
        closed_pending = add(6)
        for id, changes in [(title_only, {"title": "변경된 제목만"}), (material, {"paid": True}),
                            (closed_pending, {"recruitment_status": "closed"})]:
            original = dict(db.execute(OpportunityVersion.__table__.select().where(OpportunityVersion.opportunity_id == id)).mappings().one())
            original.update(version=2, review_status="pending", reviewed_at=None, **changes)
            db.execute(insert(OpportunityVersion), original)
        repository = SqlPublicOpportunityRepository(lambda: nullcontext(db))
        candidates = repository.recommendation_candidates(NOW)
        assert {item.id.int for item in candidates} == {1, 2, 6}
        by_id = {item.id: item for item in candidates}
        assert not by_id[title_only].change_pending
        assert by_id[material].change_pending and by_id[closed_pending].change_pending
        # 공개 검색은 개인 제외·신선도로 줄이지 않는다.
        from app.modules.opportunities.service import OpportunitySearch
        assert repository.list(OpportunitySearch(), NOW).total == 5
