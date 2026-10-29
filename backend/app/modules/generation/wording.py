"""경험 문구 다듬기. 모델이 쓴 요약은 근거 원문에 묶여 있을 때만 쓰고, 기간 표기는 서버가 바꾼다.

원문에 없는 사실(숫자·자격·다른 일)이 요약에 들어가지 않게 하는 보수적인 문자열 검사다. 의미까지 판단하지
못하므로 통과한 요약도 사용자 확인을 거친다. 통과하지 못하면 원문 인용으로 되돌린다.
"""

import re

from app.modules.generation.privacy import safe_text

SUMMARY_MAX_LENGTH = 40
_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
# 단어 앞에서 시작하는 한자어 수 + 단위. "오래"·"일했어요"처럼 수가 아닌 글자는 단위가 없어 걸리지 않는다.
_SINO = r"[일이삼사오육칠팔구]?십[일이삼사오육칠팔구]?|[일이삼사오육칠팔구]"
# 수와 바로 뒤의 단위. 같은 수라도 단위가 다르면 다른 사실이다(6개월 ≠ 6년).
_UNITS = {"년": "년", "해": "년", "개월": "개월", "달": "개월", "시간": "시간", "살": "세", "세": "세", "명": "명", "회": "회", "급": "급"}
_UNIT = "|".join(sorted(_UNITS, key=len, reverse=True))
# 단어 앞에서 시작하는 한자어 수는 단위가 있을 때만 수로 읽는다. "오래"·"일했어요"는 수가 아니다.
_NUMBER = re.compile(rf"(?<![가-힣])({_SINO})\s*({_UNIT})")
_ARABIC = re.compile(rf"(\d+)\s*({_UNIT})?")
_DURATION = re.compile(r"^(?:(한|약|대략)\s*)?(\d{1,2}|[일이삼사오육칠팔구]?십[일이삼사오육칠팔구]?|[일이삼사오육칠팔구])\s*"
                       r"(년|해|개월)\s*(정도|쯤|가량|넘게|남짓)?\s*[.?!]?$")
# 요약에 새로 넣을 수 있는 일반어. 사실을 더하지 않는 말만 둔다.
_GENERIC = frozenset({"경력", "근무", "업무", "활동", "봉사", "담당", "경험", "보조", "및", "년", "개월"})
# 자격·면허는 경험 요약이 아니라 자격 항목에서 사용자가 확인한다.
_CREDENTIAL = re.compile(r"자격|면허|기능사|산업기사|\d\s*급|[일이삼]급")


def sino_number(word: str) -> int:
    if word.isdigit():
        return int(word)
    if "십" not in word:
        return _DIGITS[word]
    tens, _, ones = word.partition("십")
    return (_DIGITS[tens] if tens else 1) * 10 + (_DIGITS[ones] if ones else 0)


def numbers_in(text: str) -> set[tuple[int, str]]:
    """원문에 나온 (수, 단위). 아라비아 숫자와 단위 앞의 한자어 수(삼십오 년 → (35, 년))를 모두 센다. 단위가 없으면 ''."""
    found = {(int(value), _UNITS.get(unit or "", "")) for value, unit in _ARABIC.findall(text)}
    found.update((sino_number(match.group(1)), _UNITS[match.group(2)]) for match in _NUMBER.finditer(text))
    return found


def _numbers_match(summary: str, source: str) -> bool:
    """요약의 수는 원문에 같은 단위로 있어야 한다. 단위 없는 수는 원문에 그 수가 어떤 단위로든 있으면 된다."""
    known = numbers_in(source)
    values = {value for value, _ in known}
    return all((value, unit) in known if unit else value in values for value, unit in numbers_in(summary))


def credential(text: str) -> bool:
    """자격·면허·급수 표현. 자격 보유는 경험의 기술이 아니라 자격 항목에서 사용자가 확인한다."""
    return bool(_CREDENTIAL.search(text))


def duration_label(quote: str) -> str:
    """'삼십오 년' → '35년', '한 삼십 년.' → '약 30년'. 모르는 형태는 원문 인용을 그대로 둔다."""
    match = _DURATION.match(quote.strip())
    if not match:
        return quote
    about, number, unit, approx = match.groups()
    unit = "개월" if unit == "개월" else "년"
    return f"{'약 ' if about or approx else ''}{sino_number(number)}{unit}"


def summary_grounded(summary: str | None, source: str) -> bool:
    """요약의 단어가 근거 턴에 있는지 본다. 단어마다 앞 두 글자가 원문에 있어야 한다(담임교사 ← 담임을)."""
    if summary is None or not 2 <= len(summary) <= SUMMARY_MAX_LENGTH or "\n" in summary or safe_text(summary) is None:
        return False
    if _CREDENTIAL.search(summary) or not _numbers_match(summary, source):
        return False
    words = re.findall(r"[가-힣A-Za-z]+", summary)
    if not words:
        return False
    plain = re.sub(r"\s", "", source)
    return all(word in _GENERIC or word[:2] in plain for word in words if len(word) >= 2)
