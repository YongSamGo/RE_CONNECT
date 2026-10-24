"""계약에서 되풀이되는 필드 타입.

숫자·불리언·문자열은 strict로 받는다. 계약 형식이 number인 자리에 문자열 "3"이나 true가 오면 바꾸지 않고 거절한다.
UUID·날짜·시각은 JSON에서 문자열로 오므로 strict로 두지 않는다.

자유 텍스트는 `text()`로 만든다. 사용자 입력·운영자 입력·수집한 공고 원문이 같은 타입을 쓰므로, 여기서
보이지 않는 문자(제어 문자·폭 없는 문자·글자 방향 제어)와 공백뿐인 값을 한 번에 거절한다.
"""

import unicodedata
from collections.abc import Callable, Hashable, Sequence
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, ConfigDict, Field, StrictFloat, StrictInt, StrictStr
from pydantic_core import PydanticCustomError

# 모든 계약 모델의 공통 설정. 정의하지 않은 키는 unknown_field로 거절한다.
CONTRACT_CONFIG = ConfigDict(extra="forbid", frozen=True)

ActivityType = Literal["employment", "volunteering"]

Weekday = Annotated[StrictInt, Field(ge=1, le=7)]
HoursPerWeek = Annotated[StrictFloat, Field(ge=0, le=168)]
# 제어(Cc)·서식(Cf: 폭 없는 문자, U+202E 같은 글자 방향 제어)·사용자 정의·서로게이트 문자와 줄·문단 구분자.
# 화면에서 문구를 다르게 보이게 하거나, 검수자 눈에 띄지 않은 채 LLM 입력에 들어갈 수 있다.
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Zl", "Zp"})


def _text_checker(multiline: bool) -> Callable[[str], str]:
    allowed = frozenset("\n\t") if multiline else frozenset()

    def check(value: str) -> str:
        value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
        if any(unicodedata.category(char) in _HIDDEN_CATEGORIES and char not in allowed for char in value):
            raise PydanticCustomError("hidden_characters", "보이지 않는 제어 문자가 있다")
        # 값이 없으면 null을 보낸다. 빈 문자열·공백뿐인 값은 "미확인"과 구분되지 않으므로 받지 않는다.
        if not value.strip():
            raise PydanticCustomError("blank_text", "공백뿐인 값")
        return value

    return check


def text(max_length: int, *, multiline: bool = False) -> Any:
    """자유 텍스트 타입. NFC로 맞추고, 숨은 문자·공백뿐인 값을 거절한다. 줄바꿈·탭은 multiline일 때만 받는다."""
    return Annotated[
        StrictStr,
        Field(min_length=1, max_length=max_length),
        AfterValidator(_text_checker(multiline)),
    ]


# 역량 태그 어휘는 고정하지 않는다. 길이·개수만 제한한다.
SkillTag = text(50)


def _ensure_unique[T: Sequence[Hashable]](items: T) -> T:
    if len(set(items)) != len(items):
        raise PydanticCustomError("unique_items", "중복된 항목이 있다")
    return items


# 계약의 uniqueItems. 중복은 invalid_value로 거절한다.
Unique = AfterValidator(_ensure_unique)
