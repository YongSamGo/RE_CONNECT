"""전송 전 보수적인 표본 필터. 의미 기반 개인정보/인젝션 탐지기가 아니다."""

import re
import unicodedata

from pydantic import TypeAdapter, ValidationError

from app.contracts.fields import text

_TEXT = TypeAdapter(text(4000, multiline=True))
_PATTERNS = (
    r"(?<!\d)\d{6}\s*[- ]?\s*[1-8]\d{6}(?!\d)",
    r"(?<!\d)0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)",
    r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
    r"주민\s*(?:등록)?\s*번호|전화\s*(?:번호|는)|연락처|여권\s*번호|계좌\s*번호",
    r"진단|병력|관절염|당뇨|고혈압|치매|암\s*치료",
    r"남편|아내|배우자|자녀|아들|딸|가족사",
    r"(?:이전|기존|지금까지|모든)\s*지시.{0,20}무시",
    r"시스템\s*(?:설정|프롬프트)|개발자\s*(?:메시지|지시)",
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|system\s+prompt",
)
_BLOCKED = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def safe_text(value: str) -> str | None:
    """숨은 문자·과대 입력·알려진 개인정보/지시문은 문장 전체를 제외한다."""
    try:
        normalized = _TEXT.validate_python(value)
    except ValidationError:
        return None
    # 호환 문자로 쓴 숫자·영문 우회를 검사하되 전송 텍스트는 계약의 NFC를 유지한다.
    if _BLOCKED.search(unicodedata.normalize("NFKC", normalized)):
        return None
    return normalized
