"""Fail CI when a required manifest or required job result is absent/non-success."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping


BASE_REQUIRED_JOBS = (
    "detect",
    "secrets",
    "workflow-audit",
    "hidden-text",
    "python",
    "persistence",
    "frontend",
)
REQUIRED_MANIFESTS = (
    "backend/requirements.txt",
    "frontend/package-lock.json",
    "speech/requirements.txt",
    "speech/tts_compat/requirements.txt",
)


def evaluate(needs: Mapping[str, object], event_name: str, missing_manifests: str = "") -> list[str]:
    """Return actionable errors; dependency-review is required only for PR events."""
    errors: list[str] = []
    missing = [item.strip() for item in missing_manifests.split(",") if item.strip()]
    if missing:
        errors.append("필수 매니페스트 누락: " + ", ".join(missing))

    required = list(BASE_REQUIRED_JOBS)
    if event_name == "pull_request":
        required.append("dependency-review")

    for job in required:
        entry = needs.get(job)
        result = entry.get("result") if isinstance(entry, Mapping) else None
        if result != "success":
            errors.append(f"필수 점검 {job} 결과가 success가 아님: {result or 'missing'}")

    # A skipped dependency review is expected on push/schedule/dispatch events.
    review = needs.get("dependency-review")
    review_result = review.get("result") if isinstance(review, Mapping) else None
    if event_name != "pull_request" and review_result not in (None, "skipped", "success"):
        errors.append(f"비 PR dependency-review 결과가 비정상: {review_result}")
    return errors


def main() -> int:
    try:
        needs = json.loads(os.environ["NEEDS"])
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"::error::필수 점검 결과를 읽지 못했습니다: {exc}")
        return 1
    if not isinstance(needs, Mapping):
        print("::error::필수 점검 결과 형식이 객체가 아닙니다.")
        return 1

    errors = evaluate(needs, os.environ.get("EVENT_NAME", ""), os.environ.get("MISSING_REQUIRED_MANIFESTS", ""))
    for job, entry in needs.items():
        result = entry.get("result") if isinstance(entry, Mapping) else "missing"
        print(f"{job}: {result}")
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print("모든 필수 매니페스트와 점검이 정상입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
