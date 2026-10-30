"""다음 질문을 서버 규칙으로 고른다. 모델을 부르지 않는다.

질문 문구는 ID가 붙은 고정 문장이다. 우선순위는 다음과 같다.
1. 경험이 없으면 경험 질문. 답변 상태(경험 없음·모르겠음·알아듣지 못함)에 따라 다른 고정 질문을 쓴다.
2. 가장 최근 경험의 빈 항목(기간·맡은 일)을 묻는 후속 질문. 경험마다 한 번씩만 묻는다.
3. 다른 경험이 있는지 한 번 더 묻는다.
4. 희망 지역·활동 유형을 묻는다. 그 질문에 대한 답만 정해진 목록·낱말과 맞춰 초안에 넣는다(모델 없음).
   읽지 못하면 한 번 더 묻고, 그래도 안 되면 프로필 화면에서 고르도록 안내한다.

같은 질문 ID는 정해진 횟수까지만 묻는다. 대화에서 정보를 뽑는 모델 사용과 질문 선택은 섞지 않는다.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts.profile import ProfileContent
from app.contracts.regions import DISTRICTS

FIRST_ID = "exp.first"
FIRST_QUESTION = "지금까지 해 오신 일 가운데 기억에 남는 일을 한 가지 들려주세요."


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    # 같은 ID를 물을 수 있는 최대 횟수. None이면 마무리 안내라 반복할 수 있다.
    limit: int | None = 1


_BANK = {q.id: q for q in (
    Question(FIRST_ID, FIRST_QUESTION),
    Question("exp.other", "직장 일이 아니어도 괜찮아요. 가게 운영, 봉사, 동아리·지역 모임, 가족 돌봄처럼 해 오신 일이 있으면 들려주세요."),
    Question("exp.hint", "천천히 생각해 보셔도 괜찮아요. 예를 들면 '식당에서 십 년 동안 조리를 했어요'처럼 어디서 무슨 일을 하셨는지 한 가지만 말씀해 주세요."),
    Question("exp.retry", "어디에서 어떤 일을 하셨는지 조금 더 구체적으로 들려주시겠어요?"),
    Question("exp.later", "지금 떠오르는 경험이 없으면 나중에 말씀하셔도 괜찮아요. 프로필 화면에서 희망 지역과 활동 유형을 먼저 고를 수 있어요.", None),
    Question("exp.duration", "그 일은 언제부터 언제까지, 또는 몇 년쯤 하셨어요? 대략 말씀해 주셔도 괜찮아요."),
    Question("exp.tasks", "그 일에서 직접 맡아서 하신 일은 무엇이었나요? 예를 들면 조리, 손님 응대, 계산, 재고 관리처럼요."),
    Question("exp.more", "다른 곳에서 하신 일이나 봉사·모임 활동도 있으면 들려주세요. 없으시면 '없어요'라고 하셔도 돼요."),
    Question("cond.region", "활동하러 다니기 편한 지역은 어디인가요? '서울 강서구', '성남시'처럼 구나 시 이름으로 말씀해 주세요.", 2),
    Question("cond.type", "급여를 받는 일자리와 봉사활동 중 어떤 것을 원하세요? 둘 다 괜찮으시면 '둘 다'라고 해 주세요.", 2),
    Question("cond.profile", "희망 지역과 활동 유형(취업·봉사)은 프로필 화면에서 골라 주세요. 더 들려주실 경험이 있으면 이어서 말씀하셔도 돼요.", None),
)}

# 경험마다 따로 세는 후속 질문. 저장 ID는 "<질문 ID>:<경험 ID>"다.
_PER_EXPERIENCE = ("exp.duration", "exp.tasks")
QUESTION_IDS = frozenset(_BANK)

# 짧은 반말·구어 답도 잡도록 어간 기준으로 둔다(없어·없다·없는데, 몰라·모름, 생각 안 나요).
_NONE = re.compile(r"(없(어|다|는데|네|음|습니다|었)|안\s*해\s*봤|해\s*본\s*(적|거)\s*(이\s*|도\s*)?없|다닌\s*적\s*(이\s*)?없|일\s*안\s*했|^\s*아니(요|오)?\s*[.!]?\s*$)")
_UNSURE = re.compile(r"(모르겠|몰라|모름|글쎄|(기억|생각)\s*(이\s*)?(잘\s*)?안\s*나)")


def answer_state(text: str) -> str:
    """'none'(없음)·'unsure'(모르겠음)·'answer'. 정보 추출이 아니라 다음 질문 분기에만 쓴다."""
    if _UNSURE.search(text):
        return "unsure"
    if _NONE.search(text):
        return "none"
    return "answer"


def text_of(question_id: str) -> str:
    return _BANK[question_id.partition(":")[0]].text


def next_question(draft: ProfileContent, asked: Sequence[str], latest: str) -> str | None:
    """다음 질문 ID. 추천에 필요한 항목이 모두 채워졌으면 None이다(화면은 프로필 확인으로 넘어간다).

    asked: 지금까지 물은 질문 ID(첫 질문 포함, 오래된 순). latest: 이번에 받은 사용자 답.
    """
    if not draft.missing_for_recommendation():
        return None
    counts = Counter(asked)

    def available(question_id: str) -> bool:
        limit = _BANK[question_id.partition(":")[0]].limit
        return limit is None or counts[question_id] < limit

    if not draft.experiences:
        state = answer_state(latest)
        order = {"none": ("exp.other", "exp.hint"), "unsure": ("exp.hint", "exp.other")}.get(state, ("exp.retry", "exp.hint", "exp.other"))
        return next((q for q in order if available(q)), "exp.later")
    latest_experience = draft.experiences[-1]
    follow_ups = []
    if latest_experience.duration_note is None:
        follow_ups.append("exp.duration")
    if not latest_experience.skill_tags:
        follow_ups.append("exp.tasks")
    for question_id in follow_ups:
        scoped = f"{question_id}:{latest_experience.id}"
        if available(scoped):
            return scoped
    if available("exp.more"):
        return "exp.more"
    if not draft.preferred_regions and available("cond.region"):
        return "cond.region"
    if not draft.activity_types and available("cond.type"):
        return "cond.type"
    return "cond.profile"


# 지역·활동 유형 답 읽기. 이 질문에 대한 답에만 쓰고, 결과는 사용자가 프로필에서 확정하기 전까지 초안이다.
_PROVINCE_WORDS = {"seoul": "서울", "gyeonggi": "경기", "incheon": "인천"}
# 시·군·구 이름은 세 시·도에서 겹치지 않는다. "성남"처럼 끝 글자를 뺀 말도 받되, "남동생"의 "남동"처럼 다른 낱말의
# 일부인 경우를 피하려고 뒤에 한글이 바로 붙지 않거나 조사·단위가 올 때만 받는다. 한 글자 어간(중구 → 중)은 받지 않는다.
_TAIL = r"(?=$|[^가-힣]|에|에서|이요|요|이나|나|쪽|근처|이랑|랑|하고|도)"
_DISTRICT_PATTERNS = [
    (province, slug, re.compile(re.escape(name) + "|" + (re.escape(name[:-1]) + _TAIL if len(name) > 2 else "(?!)")))
    for province, items in DISTRICTS.items() for slug, name in items
]


# 음성 인식이 지명을 비슷한 소리의 다른 말로 적는 경우(측정: "마포구요" → "맛보고요", "영등포구요" → "영등포고요")를
# 위해, 정확히 맞는 이름이 없을 때만 자모 단위로 가장 비슷한 지명을 고른다. 소리가 비슷한 자모끼리는 차이를 작게 친다.
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]
_SIMILAR = [set(group) for group in ("ㄱㅋㄲ", "ㄷㅌㄸ", "ㅂㅍㅃ", "ㅈㅊㅉ", "ㅅㅆ", "ㅗㅜ", "ㅐㅔ", "ㅓㅗ", "ㅕㅛ", "ㅚㅙㅞ")]
_FUZZY_MAX = 1.5  # 세 글자 이상 지명에만 쓴다. 두 글자(중구)는 정확히 맞을 때만 받는다.


def _syllables(text: str) -> list[tuple[str, str, str]]:
    out = []
    for char in text:
        code = ord(char) - 0xAC00
        if 0 <= code < 11172:
            out.append((_CHO[code // 588], _JUNG[code % 588 // 28], _JONG[code % 28]))
    return out


def _sound(a: str, b: str) -> float:
    return 0.0 if a == b else 0.5 if any(a in group and b in group for group in _SIMILAR) else 1.0


def _syllable_cost(a: tuple[str, str, str], b: tuple[str, str, str]) -> float:
    # 받침은 있고 없음만 달라도 0.5("마"↔"맛"), 서로 다르면 소리 차이대로 센다.
    tail = 0.0 if a[2] == b[2] else 0.5 if not a[2] or not b[2] else _sound(a[2], b[2])
    return _sound(a[0], b[0]) + _sound(a[1], b[1]) + tail


def _closest_span(target: list[tuple[str, str, str]], text: list[tuple[str, str, str]]) -> float:
    """target이 text의 어느 부분과 가장 비슷한지. 글자끼리 맞추고(시작·끝 자유) 글자 안의 자모 차이를 센다.
    자모를 글자 경계 너머로 맞추지 않아서 "한 삼십"을 "하남시"로 읽지 않는다. 글자 넣고 빼기는 1.0이다."""
    previous = [0.0] * (len(text) + 1)
    for a in target:
        current = [previous[0] + 1.0] + [0.0] * len(text)
        for j, b in enumerate(text, 1):
            current[j] = min(previous[j] + 1.0, current[j - 1] + 1.0, previous[j - 1] + _syllable_cost(a, b))
        previous = current
    return min(previous)


def _fuzzy_district(text: str, context: str | None = None) -> tuple[str, str] | None:
    # 지역 질문의 짧은 답에만 쓴다. 긴 문장에서는 짧은 지명(구리시·하남시)이 우연히 비슷하게 잡힌다.
    if len(re.findall(r"[가-힣]", text)) > 25:
        return None
    letters = _syllables(text)
    # 시·도를 말했으면 그 안에서만 고르고, 말하지 않았으면 더 가깝게 들린 것만 받는다.
    # 여러 곳을 말한 답은 조각별로 고르므로 시·도는 답 전체(context)에서 찾는다.
    named = [province for province, word in _PROVINCE_WORDS.items() if word in (context or text)]
    limit = _FUZZY_MAX if named else 0.5
    scored = []
    for province, items in DISTRICTS.items():
        if named and province not in named:
            continue
        for slug, name in items:
            if len(name) < 3:
                continue
            full, stem = _closest_span(_syllables(name), letters), _closest_span(_syllables(name[:-1]), letters)
            # 끝의 구·시·군도 비슷하게 들려야 한다. "남동생"처럼 앞부분만 같은 다른 낱말을 고르지 않는다.
            if full - stem <= 0.5:
                scored.append((full, province, slug))
    scored.sort()
    if not scored or scored[0][0] > limit or (len(scored) > 1 and scored[1][0] - scored[0][0] < 0.5):
        return None
    return scored[0][1], scored[0][2]


def _matches(text: str) -> list[tuple[str, str]]:
    return [(province, slug) for province, slug, pattern in _DISTRICT_PATTERNS if pattern.search(text)]


# 음성 인식이 두 글자 지명 "중구"를 "중국"으로 적는다(2026-10-30 운영 시험). 두 글자 지명은 비슷한 소리로 고르지 않으므로
# 지역 질문의 답에서만 이 말을 중구로 읽는다.
_MISHEARD = [(re.compile(r"중국"), "중구")]
# 여러 곳을 말한 답("광진구랑 송동구")은 조각마다 정확히 맞는 지명이 없을 때만 가장 비슷한 지명을 고른다.
_SEPARATORS = re.compile(r"[,，·/]|\s(?:그리고|또는|아니면)\s|(?<=[가-힣])(?:이랑|랑|하고)(?=\s|$)")


def read_regions(text: str) -> list[dict]:
    """답에 나온 시·군·구. 시·도만 말하면(예: "서울이면 다 좋아요") 그 시·도 전체로 본다. 최대 10곳."""
    for pattern, name in _MISHEARD:
        text = pattern.sub(name, text)
    found = _matches(text)
    pieces = _SEPARATORS.split(text)
    if len(pieces) > 1:
        for piece in pieces:
            if not _matches(piece) and (closest := _fuzzy_district(piece, text)) is not None and closest not in found:
                found.append(closest)
    elif not found and (closest := _fuzzy_district(text)) is not None:
        found = [closest]
    regions = [{"province": province, "district": slug} for province, slug in found]
    named = {province for province, _ in found}
    regions += [{"province": province, "district": None} for province, word in _PROVINCE_WORDS.items()
                if word in text and province not in named]
    return regions[:10]


_BOTH = re.compile(r"둘\s*다|상관\s*없|아무\s*거나|다\s*(좋|괜찮)")
# "그결"·"그별"은 음성 인식이 질문의 "급여"를 잘못 적은 결과다(2026-10-30 운영 시험).
_EMPLOYMENT = re.compile(r"일자리|취업|급여|그결|그별|월급|유급|알바|아르바이트|돈\s*(을\s*)?(벌|받)|직장")
_VOLUNTEERING = re.compile(r"봉사|무급")


def read_activity_types(text: str) -> list[str]:
    if _BOTH.search(text):
        return ["employment", "volunteering"]
    return [kind for kind, pattern in (("employment", _EMPLOYMENT), ("volunteering", _VOLUNTEERING)) if pattern.search(text)]
