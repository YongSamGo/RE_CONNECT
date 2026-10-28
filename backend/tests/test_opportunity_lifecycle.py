"""마감 KST 경계·48시간·수집 실패·일시 누락에서 잘못 종료/추천하지 않는다."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.contracts.opportunity import OpportunityContent
from app.modules.opportunities.lifecycle import CollectionState, assess_lifecycle, record_collection_attempt
from tests.test_contracts import opportunity

NOW = datetime(2026, 10, 17, 0, tzinfo=UTC)


def assess(*, checked=NOW, now=NOW, **updates):
    return assess_lifecycle(OpportunityContent.model_validate(opportunity(**updates)), source_checked_at=checked, now=now)


@pytest.mark.parametrize("delay,allowed", [
    (timedelta(hours=48, microseconds=-1), True),
    (timedelta(hours=48), True),
    (timedelta(hours=48, microseconds=1), False),
])
def test_exact_48_hour_boundary(delay, allowed):
    result = assess(checked=NOW - delay)
    assert result.recommendation_allowed is allowed
    assert result.recruitment_status == "open"
    assert result.hold_reasons == (() if allowed else ("stale",))


@pytest.mark.parametrize("now,status,unconfirmed", [
    ("2026-10-16T14:59:59+00:00", "open", False),
    ("2026-10-16T15:00:00+00:00", "open", True),
    ("2026-10-17T14:59:59.999999+00:00", "open", True),
    ("2026-10-17T15:00:00+00:00", "closed", False),
])
def test_date_only_deadline_uses_korean_date_without_inventing_time(now, status, unconfirmed):
    instant = datetime.fromisoformat(now)
    result = assess(now=instant, checked=instant, deadline_date="2026-10-17")
    assert result.recruitment_status == status
    assert result.deadline_time_unconfirmed is unconfirmed


@pytest.mark.parametrize("delta,closed", [(timedelta(microseconds=-1), False), (timedelta(), True), (timedelta(microseconds=1), True)])
def test_precise_deadline_is_exclusive_instant(delta, closed):
    result = assess(now=NOW + delta, checked=NOW + delta, deadline_date="2026-10-17", deadline_at=NOW)
    assert (result.recruitment_status == "closed") is closed
    assert not result.deadline_time_unconfirmed


def test_closed_is_not_reopened_by_freshness_or_future_deadline():
    result = assess(recruitment_status="closed")
    assert result.recruitment_status == "closed"
    assert not result.recommendation_allowed


def test_unknown_status_is_not_opened_by_freshness():
    result = assess(recruitment_status="unknown")
    assert result.hold_reasons == ("recruitment_unknown",)


@pytest.mark.parametrize("checked,reason", [(None, "never_checked"), (NOW + timedelta(seconds=1), "future_check")])
def test_unverified_or_future_check_blocks_recommendation(checked, reason):
    result = assess(checked=checked)
    assert not result.recommendation_allowed
    assert result.hold_reasons == (reason,)
    assert result.recruitment_status == "open"


def test_naive_clock_and_check_are_rejected():
    with pytest.raises(ValueError):
        assess(now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        assess(checked=NOW.replace(tzinfo=None))


def test_failed_collection_preserves_success_and_does_not_close_missing_posting():
    initial = CollectionState(last_attempt_at=None, last_success_at=None, last_result="never")
    success = record_collection_attempt(initial, attempted_at=NOW, succeeded=True)
    failed = record_collection_attempt(success, attempted_at=NOW + timedelta(hours=6), succeeded=False)
    assert failed.last_success_at == NOW
    assert failed.last_result == "failed"
    assert success.last_result == "success"
    # 실패·누락으로 확인 시각을 새로 만들지 않는다. 48시간 초과 시 추천만 보류한다.
    missing = assess(now=NOW + timedelta(hours=49), checked=NOW)
    assert missing.recruitment_status == "open"
    assert missing.hold_reasons == ("stale",)


def test_successful_source_run_does_not_refresh_unseen_postings():
    previous = CollectionState(last_attempt_at=NOW, last_success_at=NOW, last_result="success")
    latest = record_collection_attempt(previous, attempted_at=NOW + timedelta(hours=49), succeeded=True)
    assert latest.last_success_at == NOW + timedelta(hours=49)
    assert not assess(now=latest.last_success_at, checked=NOW).recommendation_allowed


def test_first_failure_does_not_create_success_timestamp():
    initial = CollectionState(last_attempt_at=None, last_success_at=None, last_result="never")
    assert record_collection_attempt(initial, attempted_at=NOW, succeeded=False).last_success_at is None


@pytest.mark.parametrize("attempted", [NOW, NOW - timedelta(hours=1)])
def test_old_or_duplicate_run_does_not_replace_newer_state(attempted):
    previous = CollectionState(last_attempt_at=NOW, last_success_at=NOW, last_result="success")
    with pytest.raises(ValueError):
        record_collection_attempt(previous, attempted_at=attempted, succeeded=False)


def test_non_boolean_success_and_inconsistent_timestamps_are_rejected():
    initial = CollectionState(last_attempt_at=None, last_success_at=None, last_result="never")
    with pytest.raises(ValueError):
        record_collection_attempt(initial, attempted_at=NOW, succeeded="false")
    with pytest.raises(ValidationError):
        CollectionState(last_attempt_at=NOW, last_success_at=NOW + timedelta(seconds=1), last_result="failed")
