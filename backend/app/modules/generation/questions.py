"""다음 질문을 서버 규칙으로 고른다. 모델을 부르지 않는다.

질문 문구는 ID가 붙은 고정 문장이다. 우선순위는 다음과 같다.
1. 경험이 없으면 경험 질문. 답변 상태(경험 없음·모르겠음·알아듣지 못함)에 따라 다른 고정 질문을 쓴다.
2. 가장 최근 경험의 빈 항목(기간·맡은 일)을 묻는 후속 질문. 경험마다 한 번씩만 묻는다.
3. 다른 경험이 있는지 한 번 더 묻는다.
4. 대화로 채우지 않는 희망 지역·활동 유형은 프로필 화면에서 고르도록 안내한다.

같은 질문 ID는 정해진 횟수까지만 묻는다. 대화에서 정보를 뽑는 모델 사용과 질문 선택은 섞지 않는다.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts.profile import ProfileContent

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
    Question("cond.profile", "희망 지역과 활동 유형(취업·봉사)은 프로필 화면에서 골라 주세요. 더 들려주실 경험이 있으면 이어서 말씀하셔도 돼요.", None),
)}

# 경험마다 따로 세는 후속 질문. 저장 ID는 "<질문 ID>:<경험 ID>"다.
_PER_EXPERIENCE = ("exp.duration", "exp.tasks")
QUESTION_IDS = frozenset(_BANK)

_NONE = re.compile(r"(없어요|없습니다|없었|없네|없음|안\s*해\s*봤|해\s*본\s*적\s*(이\s*)?없|다닌\s*적\s*(이\s*)?없|^\s*아니(요|오)?\s*[.!]?\s*$)")
_UNSURE = re.compile(r"(모르겠|잘\s*몰라|글쎄|기억(이|이\s*잘)?\s*안\s*나|생각이\s*안\s*나)")


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
    return "cond.profile"
