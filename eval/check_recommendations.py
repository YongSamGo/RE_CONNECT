"""실제 공고로 추천을 돌려 기대값과 대조한다 (W08-08 · #65).

`worker/samples/`(커밋 제외)의 senuri·1365 원본 응답을 실제 정규화기(`normalize_items`)로 바꾸고,
페르소나 8명의 확정 프로필로 실제 추천 필터·정렬(`filter_candidates`·`rank_candidates`)을 DB 없이 돌린다.
두 상태를 비교한다.

- 수집 그대로: 정규화 결과를 그대로 공개본으로 본다.
- 검수 후: `recommendation_review.json`의 검수 값(1365 지역 코드, 공고별 skill_tags·role_tags)을 덧씌운다.

기대값(`expectations`)과 다르거나(`known_missing`에 적은 알려진 결함 제외) 추천 근거가 프로필에 없으면 종료 코드 1이다.
원본 샘플이 없으면 `worker/tools/fetch_source_samples.py`로 받는다(docs/ai/recommendation-eval.md).

사용법 (저장소 최상위에서, 백엔드 가상환경으로):
    backend/.venv/bin/python -I eval/check_recommendations.py
    backend/.venv/bin/python -I eval/check_recommendations.py --list-postings   # 검수 값 작성용 공고 목록
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.contracts.profile import ProfileContent  # noqa: E402
from app.contracts.recommendation import RecommendationFilters  # noqa: E402
from app.contracts.regions import Region  # noqa: E402
from app.contracts.roles import CatalogRole  # noqa: E402
from app.core.business_errors import AppError  # noqa: E402
from app.modules.ingestion.fetch import parse_xml  # noqa: E402
from app.modules.ingestion.normalize import normalize_items  # noqa: E402
from app.modules.opportunities.service import PublicOpportunity  # noqa: E402
from app.modules.recommendations.filters import filter_candidates  # noqa: E402
from app.modules.recommendations.ranking import rank_candidates  # noqa: E402

SAMPLES = ROOT / "worker/samples"
REVIEW = json.loads((ROOT / "eval/recommendation_review.json").read_text(encoding="utf-8"))
# 출처별 (목록 오퍼레이션들, 상세 오퍼레이션, ID 필드)
SOURCES = {"senuri": (("getJobList",), "getJobInfo", "jobId"),
           "volunteer": (("getVltrAreaList", "getVltrSearchWordList"), "getVltrPartcptnItem", "progrmRegistNo")}
# 수집기(runner)는 지역 목록만 쓴다. 키워드 검색 목록은 지역 목록에 있는 필드만 남겨 같은 입력으로 맞춘다.
AREA_LISTING_FIELDS = {"gugunCd", "nanmmbyNm", "progrmBgnde", "progrmEndde", "progrmRegistNo", "progrmSj",
                       "progrmSttusSe", "sidoCd"}
# 0003 마이그레이션의 초기 역할 2개도 role-catalog.json에 들어 있다.
CATALOG = [CatalogRole.model_validate(role) for role in
           json.loads((ROOT / "docs/data/role-catalog.json").read_text(encoding="utf-8"))]


def items(path: Path):
    result = parse_xml(path.read_bytes())
    return result.document.root.findall("body/items/item") if result.document else []


def load_postings(now: datetime) -> dict[str, tuple[PublicOpportunity, dict]]:
    """key("출처:ID") → (수집 그대로의 공개본, 목록 필드). 같은 ID는 가장 최근 응답을 쓴다."""
    postings = {}
    for source, (listing_ops, detail_op, id_field) in SOURCES.items():
        listings, details = {}, {}
        for listing_op in listing_ops:
            for path in sorted((SAMPLES / source).glob(f"*-{listing_op}.xml")):
                for item in items(path):
                    if listing_op == "getVltrSearchWordList":
                        for child in [child for child in item if child.tag not in AREA_LISTING_FIELDS]:
                            item.remove(child)
                    listings[item.findtext(id_field)] = item
        for path in sorted((SAMPLES / source).glob(f"*-{detail_op}.xml")):
            details.update({item.findtext(id_field): item for item in items(path)})
        for external_id, detail in details.items():
            if external_id not in listings:
                continue
            result = normalize_items(source, listings[external_id], detail, checked_at=now)
            if result.status != "candidate":
                continue
            key = source + ":" + external_id
            opportunity = PublicOpportunity.model_validate({
                **result.candidate.content.model_dump(), "id": uuid5(NAMESPACE_URL, "reconnect-eval:" + key),
                "version": 1, "description_truncated": result.candidate.description_truncated,
                "source_checked_at": now, "reviewed_at": now, "change_pending": False})
            fields = {child.tag: child.text for child in listings[external_id]}
            postings[key] = (opportunity, fields)
    return postings


def reviewed(opportunity: PublicOpportunity, fields: dict, key: str) -> PublicOpportunity:
    """운영자 검수 값을 덧씌운다. 검수 값이 없는 항목은 수집 그대로 둔다."""
    update = {}
    region = REVIEW["region_codes"].get(f"{fields.get('sidoCd')}:{fields.get('gugunCd')}")
    if opportunity.activity_region is None and region:
        update["activity_region"] = Region(**region)
    tags = REVIEW["postings"].get(key)
    if tags:
        update["skill_tags"], update["role_tags"] = tags["skill_tags"], tags["role_tags"]
    return opportunity.model_copy(update=update)


def profile(persona_id: str) -> ProfileContent:
    data = json.loads((ROOT / f"eval/personas/{persona_id}.json").read_text(encoding="utf-8"))
    content = {**data["expected_profile"], **REVIEW["confirmations"].get(persona_id, {}).get("answers", {})}
    content["experiences"] = [{**experience, "id": uuid5(NAMESPACE_URL, f"reconnect-eval:{persona_id}:{index}")}
                              for index, experience in enumerate(content["experiences"])]
    return ProfileContent.model_validate(content)


def recommend(content: ProfileContent, opportunities: list[PublicOpportunity], now: datetime):
    try:
        candidates = filter_candidates(content, opportunities, RecommendationFilters(), frozenset(), now)
    except AppError as error:
        return error.code, []
    return None, rank_candidates(content, candidates, CATALOG)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list-postings", action="store_true", help="검수 값 작성용 공고 목록을 출력한다")
    args = parser.parse_args()
    now = datetime.fromisoformat(REVIEW["reference_time"])
    postings = load_postings(now)
    if not postings:
        print("worker/samples/에 정규화되는 원본 샘플이 없습니다. docs/ai/recommendation-eval.md를 보세요.")
        return 2
    if args.list_postings:
        for key, (opportunity, fields) in sorted(postings.items()):
            region = reviewed(opportunity, fields, key).activity_region
            print(key, opportunity.activity_type, "유급" if opportunity.paid else "무급",
                  f"{region.province}/{region.district}" if region else "지역없음", opportunity.title, sep="\t")
        return 0

    titles = {key: opportunity.title for key, (opportunity, _) in postings.items()}
    keys = {opportunity.id: key for key, (opportunity, _) in postings.items()}
    collected = [opportunity for opportunity, _ in postings.values()]
    review = [reviewed(opportunity, fields, key) for key, (opportunity, fields) in postings.items()]
    unknown = sorted(set(REVIEW["postings"]) - set(postings))
    problems = [f"검수 값에 있으나 샘플에 없는 공고: {', '.join(unknown)}"] if unknown else []
    print(f"공고 {len(postings)}건 (기준 시각 {REVIEW['reference_time']}), "
          f"검수 후 지역 있음 {sum(o.activity_region is not None for o in review)}건, "
          f"태그 있음 {sum(bool(o.skill_tags) for o in review)}건\n")

    for persona_id, expected in sorted(REVIEW["expectations"].items()):
        content = profile(persona_id)
        experience_ids = {experience.id for experience in content.experiences}
        _, before = recommend(content, collected, now)
        error, after = recommend(content, review, now)
        got = [keys[item.candidate.opportunity.id] for item in after]
        print(f"## {persona_id}  수집 그대로 {len(before)}건 → 검수 후 {len(got)}건" + (f" ({error})" if error else ""))
        for rank, item in enumerate(after, 1):
            key = keys[item.candidate.opportunity.id]
            print(f"  {rank}. {titles[key]} [{key}] 근거 태그 {item.matched.skill_tags} "
                  f"역할 {item.matched.role_ids} 자격 {item.candidate.eligibility.overall}")
            if not item.matched.experience_ids or not set(item.matched.experience_ids) <= experience_ids:
                problems.append(f"{persona_id}: {key} 추천 근거 경험이 프로필에 없음")
        if before:
            problems.append(f"{persona_id}: 태그가 없는 수집 그대로의 공고가 추천됨")
        for key in expected["must_include"]:
            if key not in got and key in expected.get("known_missing", {}):
                print(f"  알려진 결함 {expected['known_missing'][key]}: {titles.get(key, key)} [{key}] 빠짐")
            elif key not in got:
                problems.append(f"{persona_id}: 나와야 할 공고가 빠짐 — {titles.get(key, key)} [{key}]")
            elif key in expected.get("known_missing", {}):
                problems.append(f"{persona_id}: 알려진 결함 {expected['known_missing'][key]}이 고쳐짐 — known_missing에서 지운다")
        for key in expected["must_not_include"]:
            if key in got:
                problems.append(f"{persona_id}: 나오면 안 되는 공고가 추천됨 — {titles.get(key, key)} [{key}]")
        if expected["count"] is not None and len(got) != expected["count"]:
            problems.append(f"{persona_id}: 추천 {len(got)}건, 기대 {expected['count']}건")
        print()

    for problem in problems:
        print("불일치:", problem)
    print("문제 없음" if not problems else f"불일치 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
