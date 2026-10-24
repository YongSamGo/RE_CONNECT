"""역할 사전 초안(docs/data/role-catalog.json)의 형식과 페르소나 역할 후보를 검사한다.

형식 규칙은 #172의 `CatalogRole` 검증을, 후보 계산은 `match_roles`(경험 하나 안의 사전 태그·별칭 일치)를
표준 라이브러리로 옮긴 것이다. 페르소나 `expected_role_ids`와 다르거나 형식이 틀리면 종료 코드 1이다.

사용법 (저장소 최상위에서):
    python eval/check_role_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
# 계약 text()와 같은 숨은 문자 범주 (backend/app/contracts/fields.py)
HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Zl", "Zp"})


def valid_text(value: object, max_length: int) -> bool:
    """계약 text(max_length): 문자열, NFC 기준 길이 1~max, 숨은 문자·공백뿐인 값 없음."""
    if not isinstance(value, str):
        return False
    value = unicodedata.normalize("NFC", value)
    return (1 <= len(value) <= max_length and value.strip() != ""
            and not any(unicodedata.category(c) in HIDDEN_CATEGORIES for c in value))


def normalize(tag: str) -> str:
    return " ".join(tag.split()).casefold()


def check_role(role: dict) -> list[str]:
    where = role.get("id", "?")
    problems = []
    if set(role) != {"id", "name", "description", "skill_tags", "aliases", "experience_rules"}:
        problems.append(f"{where}: 필드 구성이 CatalogRole과 다름")
        return problems
    if not ROLE_ID.fullmatch(role["id"]):
        problems.append(f"{where}: id 형식")
    if not valid_text(role["name"], 50) or not valid_text(role["description"], 300):
        problems.append(f"{where}: name·description 길이·숨은 문자·공백")
    tags = role["skill_tags"]
    if len(tags) > 20 or not all(valid_text(t, 50) for t in tags) or len(set(tags)) != len(tags):
        problems.append(f"{where}: skill_tags 개수·길이·숨은 문자·중복")
    canonical = {normalize(t) for t in tags}
    if len(canonical) != len(tags):
        problems.append(f"{where}: 정규화 후 중복된 태그")
    seen = set(canonical)
    if len(role["aliases"]) > 100:
        problems.append(f"{where}: aliases 개수")
    for alias in role["aliases"]:
        name, target = normalize(alias["alias"]), normalize(alias["skill_tag"])
        if not valid_text(alias["alias"], 50) or not valid_text(alias["skill_tag"], 50):
            problems.append(f"{where}: 별칭 값 길이·숨은 문자·공백")
        if name in seen or target not in canonical:
            problems.append(f"{where}: 별칭 '{alias['alias']}'의 대상 또는 중복")
        seen.add(name)
    if len(role["experience_rules"]) > 20:
        problems.append(f"{where}: experience_rules 개수")
    for rule in role["experience_rules"]:
        rule_tags = rule["skill_tags"]
        if not 1 <= len(rule_tags) <= 20 or len(set(rule_tags)) != len(rule_tags):
            problems.append(f"{where}: 연결 규칙 태그 개수 1~20·중복")
        if rule["operator"] not in ("all", "any") or not {normalize(t) for t in rule_tags} <= canonical:
            problems.append(f"{where}: 연결 규칙은 확인된 사전 태그만 사용")
    return problems


def match_roles(experiences: list[dict], catalog: list[dict]) -> list[str]:
    """경험 하나 안에서 사전 태그·별칭이 맞는 역할 id (근거 경험 수가 많은 순)."""
    found = []
    for role in catalog:
        mapping = {normalize(t): normalize(t) for t in role["skill_tags"]}
        mapping.update({normalize(a["alias"]): normalize(a["skill_tag"]) for a in role["aliases"]})
        evidence = 0
        for experience in experiences:
            matched = {mapping[normalize(t)] for t in experience["skill_tags"] if normalize(t) in mapping}
            if role["experience_rules"]:
                supported = any(
                    {normalize(t) for t in rule["skill_tags"]} <= matched if rule["operator"] == "all"
                    else bool({normalize(t) for t in rule["skill_tags"]} & matched)
                    for rule in role["experience_rules"]
                )
            else:
                supported = bool(matched)
            evidence += supported
        if evidence:
            found.append((-evidence, role["id"]))
    return [role_id for _, role_id in sorted(found)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    catalog = json.loads((ROOT / "docs/data/role-catalog.json").read_text(encoding="utf-8"))
    problems = [p for role in catalog for p in check_role(role)]
    ids = [role["id"] for role in catalog]
    if len(set(ids)) != len(ids):
        problems.append("역할 id 중복")
    for path in sorted((ROOT / "eval/personas").glob("P*.json")):
        persona = json.loads(path.read_text(encoding="utf-8"))
        got = match_roles(persona["expected_profile"]["experiences"], catalog)
        expected = persona.get("expected_role_ids")
        if expected is None:
            problems.append(f"{persona['id']}: expected_role_ids 없음")
            continue
        unknown = set(expected) - set(ids)
        if unknown:
            problems.append(f"{persona['id']}: 사전에 없는 기대 역할 {sorted(unknown)}")
        if set(got) != set(expected):
            problems.append(f"{persona['id']}: 기대 {sorted(expected)}, 계산 {sorted(got)}")
        print(f"{persona['id']}: {', '.join(got) or '(후보 없음)'}")
    for problem in problems:
        print(problem)
    print(f"\n역할 {len(catalog)}개, 페르소나 대조 포함 문제 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
