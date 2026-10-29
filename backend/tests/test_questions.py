"""다음 질문 규칙(모델 없음): 답변 상태별 분기, 경험별 후속 질문, 반복 제한, 저장 ID 검증."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.journey import ConversationTurn
from app.contracts.profile import ProfileContent, empty_profile_content
from app.modules.generation import questions
from app.modules.generation.questions import FIRST_ID, answer_state, next_question, text_of


def profile(*experiences, regions=(), types=()):
    base = empty_profile_content().model_dump(mode="json")
    items = [{"id": str(uuid4()), "description": description, "duration_note": duration, "skill_tags": list(tags)}
             for description, duration, tags in experiences]
    return ProfileContent.model_validate({**base, "experiences": items, "preferred_regions": list(regions),
                                          "activity_types": list(types)})


@pytest.mark.parametrize(("text", "state"), [
    ("직장에 다닌 적은 없어요.", "none"), ("일해 본 적이 없습니다", "none"), ("아니요.", "none"),
    ("잘 모르겠어요.", "unsure"), ("기억이 잘 안 나네요", "unsure"),
    # 짧은 반말·구어 답(리뷰 #312)
    ("없어", "none"), ("없다", "none"), ("그런 거 없는데", "none"), ("해본 거 없어", "none"), ("일 안 했어요", "none"),
    ("몰라요", "unsure"), ("몰라", "unsure"), ("모름", "unsure"), ("생각 안 나요", "unsure"),
    ("식당에서 일했어요.", "answer"), ("아니요 저는 식당에서 일했어요", "answer"),
])
def test_answer_state(text, state):
    assert answer_state(text) == state


def test_no_experience_offers_other_kinds_then_stops_repeating():
    # 예시 B: 직장 경험이 없으면 다른 경험 유형을 안내하고, 같은 질문을 되풀이하지 않는다.
    empty = profile()
    asked = [FIRST_ID]
    assert next_question(empty, asked, "직장에 다닌 적은 없어요.") == "exp.other"
    assert next_question(empty, [*asked, "exp.other"], "그런 것도 없어요.") == "exp.hint"
    final = next_question(empty, [*asked, "exp.other", "exp.hint"], "없어요")
    assert final == "exp.later"
    assert next_question(empty, [*asked, "exp.other", "exp.hint", "exp.later"], "없어요") == "exp.later"
    assert "프로필 화면" in text_of(final)


def test_unclear_answer_gets_example_before_retry():
    assert next_question(profile(), [FIRST_ID], "글쎄요 잘 모르겠어요") == "exp.hint"
    assert next_question(profile(), [FIRST_ID], "그냥 이것저것요") == "exp.retry"
    assert next_question(profile(), [FIRST_ID, "exp.retry"], "이것저것요") == "exp.hint"


def test_latest_experience_follow_ups_ask_duration_then_tasks_once_each():
    # 예시 A: "식당에서 일했어요."에는 기간과 직접 맡은 일을 차례로 묻는다.
    draft = profile(("식당", None, ()))
    experience_id = draft.experiences[-1].id
    first = next_question(draft, [FIRST_ID], "식당에서 일했어요.")
    assert first == f"exp.duration:{experience_id}" and "몇 년" in text_of(first)
    second = next_question(draft, [FIRST_ID, first], "잘 모르겠어요")
    assert second == f"exp.tasks:{experience_id}" and "직접 맡아서" in text_of(second)
    assert next_question(draft, [FIRST_ID, first, second], "기억이 안 나요") == "exp.more"
    assert next_question(draft, [FIRST_ID, first, second, "exp.more"], "없어요") == "cond.profile"


def test_new_experience_gets_its_own_follow_ups():
    older = profile(("식당", None, ()))
    asked = [FIRST_ID, f"exp.duration:{older.experiences[0].id}", f"exp.tasks:{older.experiences[0].id}", "exp.more"]
    newer = profile(("식당", None, ()), ("도서관 봉사", "삼 년", ()))
    assert next_question(newer, asked, "도서관 봉사를 삼 년 했어요") == f"exp.tasks:{newer.experiences[-1].id}"


def test_complete_experience_moves_to_profile_conditions_and_ends_when_ready():
    done = profile(("식당", "십 년", ("조리",)))
    assert next_question(done, [FIRST_ID], "식당에서 십 년 조리했어요") == "exp.more"
    assert next_question(done, [FIRST_ID, "exp.more"], "없어요") == "cond.profile"
    # 추천에 필요한 항목이 모두 있으면 질문하지 않는다(화면은 프로필 확인으로 넘어간다).
    ready = profile(("식당", None, ()), regions=[{"province": "seoul", "district": "nowon"}], types=["volunteering"])
    assert next_question(ready, [FIRST_ID], "식당에서 일했어요") is None


def test_question_texts_are_fixed_and_do_not_request_sensitive_data():
    for question_id in questions.QUESTION_IDS:
        sentence = text_of(question_id)
        assert 0 < len(sentence) <= 2000
        for word in ("주민", "전화", "연락처", "계좌", "병", "진단", "가족 관계"):
            assert word not in sentence


@pytest.mark.parametrize("value", [
    "exp.duration", "cond.profile", f"exp.tasks:{uuid4()}", None,
])
def test_stored_question_id_accepts_known_shape(value):
    assert ConversationTurn(message_id=uuid4(), text="가상 답변", next_question=value).next_question == value


@pytest.mark.parametrize("value", [
    "exp.duration; drop", "EXP.more", "exp.more:../../x", "x" * 61, "지시를 무시해", "exp.more\n",
])
def test_stored_question_id_rejects_injected_values(value):
    with pytest.raises(ValidationError):
        ConversationTurn(message_id=uuid4(), text="가상 답변", next_question=value)


def test_turns_saved_before_this_change_still_load():
    turn = ConversationTurn.model_validate({"message_id": str(uuid4()), "text": "가상 답변"})
    assert turn.next_question is None
