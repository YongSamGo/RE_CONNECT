"""eligibility_cases.json의 기대 판정이 rules와 맞는지 다시 계산해 검사한다.

평가 데이터(페르소나 기대 프로필·공고 조건·기대 판정)를 고친 뒤 실행한다. 판정이 하나라도 다르거나
데이터 구조가 어긋나면 종료 코드 1이다. 표준 라이브러리만 쓴다.

이 스크립트는 rules 문장을 그대로 옮긴 기준 구현이다. 서비스의 자격 비교(#58)는 이 결과와 같아야 하지만,
이 파일을 서비스 코드로 가져다 쓰지는 않는다.

사용법 (저장소 최상위에서):
    python eval/check_eligibility.py
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import date
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
LABEL_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/YongSamGo/RE_CONNECT/eval")

SATISFIED, NOT_SATISFIED, UNKNOWN = "satisfied", "not_satisfied", "unknown"
# 등급만 다른 같은 종목: 끝의 N급·기능사·산업기사·기사·기능장·기술사를 뗀 이름이 같다
GRADE_SUFFIX = re.compile(r"(\s*[1-3]급|기능사|산업기사|기사|기능장|기술사)$")
ALLOWED_OPERATORS = {
    "age": {"gte", "lte", "between"},
    "residence_region": {"in"},
    "certification": {"has_all", "has_any"},
    "completed_course": {"has_all", "has_any"},
    "weekday": {"includes_all", "includes_any"},
    "hours_per_week": {"gte", "lte"},
    "other": {None},
}


def all_of(results: list[str]) -> str:
    if NOT_SATISFIED in results:
        return NOT_SATISFIED
    return UNKNOWN if UNKNOWN in results else SATISFIED


def any_of(results: list[str]) -> str:
    if SATISFIED in results:
        return SATISFIED
    return NOT_SATISFIED if all(r == NOT_SATISFIED for r in results) else UNKNOWN


def match_name(held: list[str] | None, required: str) -> str:
    if held is None:
        return UNKNOWN
    if not held:
        return NOT_SATISFIED
    if required in held:
        return SATISFIED
    if any(required in name or name in required for name in held):
        return UNKNOWN
    if any(GRADE_SUFFIX.sub("", name) == GRADE_SUFFIX.sub("", required) for name in held):
        return UNKNOWN
    return NOT_SATISFIED


def compare(op: str, actual: float, value) -> bool:
    if op == "gte":
        return actual >= value
    if op == "lte":
        return actual <= value
    if op == "between":
        return value[0] <= actual <= value[1]
    raise ValueError(f"지원하지 않는 연산: {op}")


def judge(requirement: dict, profile: dict, reference_year: int) -> str:
    field, op, value = requirement["field"], requirement["operator"], requirement["value"]
    if field not in ALLOWED_OPERATORS or op not in ALLOWED_OPERATORS[field]:
        raise ValueError("허용되지 않은 조건·연산")
    if requirement["clarity"] == "needs_review" or op is None:
        return UNKNOWN

    if field == "age":
        birth_year = profile["birth_year"]
        reference_date = requirement["reference_date"]
        if birth_year is None or reference_date is None:
            return UNKNOWN
        reference_year = date.fromisoformat(reference_date).year
        # 출생연도만 있으면 만 나이는 (기준연도 - 출생연도 - 1) 또는 (기준연도 - 출생연도)
        results = [compare(op, age, value) for age in (reference_year - birth_year - 1, reference_year - birth_year)]
        return SATISFIED if all(results) else NOT_SATISFIED if not any(results) else UNKNOWN

    if field == "residence_region":
        region = profile["residence_region"]
        if region is None:
            return UNKNOWN
        results = [
            NOT_SATISFIED if region["province"] != allowed["province"]
            else SATISFIED if allowed["district"] is None
            else UNKNOWN if region["district"] is None
            else SATISFIED if region["district"] == allowed["district"] else NOT_SATISFIED
            for allowed in value
        ]
        return any_of(results)

    if field in ("certification", "completed_course"):
        held = profile["certifications" if field == "certification" else "completed_courses"]
        results = [match_name(held, name) for name in value]
        return all_of(results) if op == "has_all" else any_of(results)

    if field == "weekday":
        available = profile["available_weekdays"]
        if available is None:
            return UNKNOWN
        included = [day in available for day in value]
        ok = all(included) if op == "includes_all" else any(included)
        return SATISFIED if ok else NOT_SATISFIED

    if field == "hours_per_week":
        hours = profile["hours_per_week"]
        if hours is None:
            return UNKNOWN
        return SATISFIED if compare(op, hours, value) else NOT_SATISFIED

    raise ValueError(f"지원하지 않는 조건: {field} {op}")


def judge_posting(posting: dict, profile: dict, reference_year: int) -> tuple[str, dict[str, str]]:
    label_of = {uid: label for label, uid in posting["labels"].items()}
    conditions: dict[str, str] = {}
    independent: list[str] = []
    groups: dict[str, tuple[str, list[str]]] = {}
    for requirement in posting["requirements"]:
        group_id, operator = requirement["group_id"], requirement["group_operator"]
        if (group_id is None) != (operator is None) or (group_id is not None and operator not in ("and", "or")):
            raise ValueError("그룹 식별자와 연산자가 맞지 않음")
        if group_id in groups and groups[group_id][0] != operator:
            raise ValueError("같은 그룹의 연산자가 다름")
        result = judge(requirement, profile, reference_year)
        # labels가 깨졌으면 UUID를 그대로 키로 써서 아래 비교에서 "조건 라벨이 다름"으로 보고되게 한다
        conditions[label_of.get(requirement["id"], requirement["id"])] = result
        if requirement["group_id"]:
            groups.setdefault(requirement["group_id"], (requirement["group_operator"], []))[1].append(result)
        else:
            independent.append(result)
    group_results = [any_of(rs) if operator == "or" else all_of(rs) for operator, rs in groups.values()]
    return all_of(independent + group_results), conditions


def check_structure(data: dict, persona_ids: list[str]) -> list[str]:
    problems = []
    for posting in data["postings"]:
        ids = {r["id"] for r in posting["requirements"]} | {r["group_id"] for r in posting["requirements"] if r["group_id"]}
        labels = posting["labels"]
        if set(labels.values()) != ids:
            problems.append(f"{posting['id']}: labels의 UUID가 조건 id·group_id와 다름")
        for label, uid in labels.items():
            if uid != str(uuid.uuid5(LABEL_NAMESPACE, label)):
                problems.append(f"{posting['id']}: {label}의 UUID가 라벨에서 만든 고정값과 다름")
    expected_pairs = {(p, j["id"]) for p in persona_ids for j in data["postings"]}
    actual_pairs = [(c["persona"], c["posting"]) for c in data["cases"]]
    if len(actual_pairs) != len(set(actual_pairs)):
        problems.append("cases에 같은 (페르소나, 공고) 쌍이 두 번 이상 있음")
    for persona, posting in sorted(expected_pairs - set(actual_pairs)):
        problems.append(f"cases에 {persona} × {posting}이 없음")
    for persona, posting in sorted(set(actual_pairs) - expected_pairs):
        problems.append(f"cases의 {persona} × {posting}은 없는 페르소나·공고")
    return problems


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글 출력
    data = json.loads((EVAL_DIR / "eligibility_cases.json").read_text(encoding="utf-8"))
    profiles = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))["expected_profile"]
        for path in sorted((EVAL_DIR / "personas").glob("P*.json"))
    }
    reference_year = int(data["reference_date"][:4])
    postings = {posting["id"]: posting for posting in data["postings"]}

    problems = check_structure(data, sorted(profiles))
    for case in data["cases"]:
        if case["persona"] not in profiles or case["posting"] not in postings:
            continue
        overall, conditions = judge_posting(postings[case["posting"]], profiles[case["persona"]], reference_year)
        where = f"{case['persona']} × {case['posting']}"
        if set(conditions) != set(case["conditions"]):
            problems.append(f"{where}: 조건 라벨이 공고와 다름")
            continue
        for label, result in conditions.items():
            if case["conditions"][label] != result:
                problems.append(f"{where} {label}: 기대 {case['conditions'][label]}, 계산 {result}")
        if case["overall"] != overall:
            problems.append(f"{where} 전체: 기대 {case['overall']}, 계산 {overall}")

    for problem in problems:
        print(problem)
    print(f"\n사례 {len(data['cases'])}건 검사: 불일치·구조 문제 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
