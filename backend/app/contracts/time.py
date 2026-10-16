"""시각·날짜 공통 처리.

시각은 시간대가 있는 UTC로 저장·전송하고, 날짜(`deadline_date` 등)는 한국 날짜다 (docs/api/README.md §2).
한국은 1988년 이후 서머타임이 없어 고정 오프셋 +09:00으로 충분하다. 시간대 데이터(tzdata)에 의존하지 않는다.
"""

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime

KST = timezone(timedelta(hours=9), "KST")


def to_utc(value: datetime) -> datetime:
    """시간대가 있는 시각을 UTC로 바꾼다. 시간대 없는 시각은 어느 시간대인지 알 수 없으므로 거절한다."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다")
    return value.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


def kst_date(value: datetime) -> date:
    """시각이 속한 한국 날짜."""
    return to_utc(value).astimezone(KST).date()


def kst_today() -> date:
    return kst_date(utc_now())


# 시간대가 없으면 거절하고(timezone_aware), 받은 값은 UTC로 맞춘다.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(to_utc)]
