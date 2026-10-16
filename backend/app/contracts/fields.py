"""계약에서 되풀이되는 필드 타입.

숫자·불리언·문자열은 strict로 받는다. 계약 형식이 number인 자리에 문자열 "3"이나 true가 오면 바꾸지 않고 거절한다.
UUID·날짜·시각은 JSON에서 문자열로 오므로 strict로 두지 않는다.
"""

from collections.abc import Hashable, Sequence
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, StrictFloat, StrictInt, StrictStr
from pydantic_core import PydanticCustomError

# 모든 계약 모델의 공통 설정. 정의하지 않은 키는 unknown_field로 거절한다.
CONTRACT_CONFIG = ConfigDict(extra="forbid", frozen=True)

ActivityType = Literal["employment", "volunteering"]

Weekday = Annotated[StrictInt, Field(ge=1, le=7)]
HoursPerWeek = Annotated[StrictFloat, Field(ge=0, le=168)]
# 역량 태그 어휘는 고정하지 않는다. 길이·개수만 제한한다.
SkillTag = Annotated[StrictStr, Field(min_length=1, max_length=50)]


def _ensure_unique[T: Sequence[Hashable]](items: T) -> T:
    if len(set(items)) != len(items):
        raise PydanticCustomError("unique_items", "중복된 항목이 있다")
    return items


# 계약의 uniqueItems. 중복은 invalid_value로 거절한다.
Unique = AfterValidator(_ensure_unique)
