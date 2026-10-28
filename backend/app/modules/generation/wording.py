"""경험 문구 다듬기. 모델이 쓴 요약은 근거 원문에 묶여 있을 때만 쓰고, 기간 표기는 서버가 바꾼다.

원문에 없는 사실(숫자·자격·다른 일)이 요약에 들어가지 않게 하는 보수적인 문자열 검사다. 의미까지 판단하지
못하므로 통과한 요약도 사용자 확인을 거친다. 통과하지 못하면 원문 인용으로 되돌린다.
"""

import re

from app.modules.generation.privacy import safe_text

SUMMARY_MAX_LENGTH = 40
_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
# 단어 앞에서 시작하는 한자어 수 + 단위. "오래"·"일했어요"처럼 수가 아닌 글자는 단위가 없어 걸리지 않는다.
_NUMBER = re.compile(r"(?<![가-힣])([일이삼사오육칠팔구]?십[일이삼사오육칠팔구]?|[일이삼사오육칠팔구])\s*(?=년|해|개월|달)")
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


def numbers_in(text: str) -> set[int]:
    """원문에 나온 수. 아라비아 숫자와 단위 앞의 한자어 수(삼십오 년 → 35)를 모두 센다."""
    found = {int(value) for value in re.findall(r"\d+", text)}
    found.update(sino_number(match.group(1)) for match in _NUMBER.finditer(text))
    return found


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
    if _CREDENTIAL.search(summary) or not numbers_in(summary) <= numbers_in(source):
        return False
    words = re.findall(r"[가-힣A-Za-z]+", summary)
    if not words:
        return False
    plain = re.sub(r"\s", "", source)
    return all(word in _GENERIC or word[:2] in plain for word in words if len(word) >= 2)
