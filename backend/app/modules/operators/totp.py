"""인증 앱용 TOTP (RFC 6238, HMAC-SHA1·6자리·30초). 표준 라이브러리 hmac만 쓴다.

비밀값과 OTP를 로그·예외 메시지에 넣지 않는다. 시험값은 RFC 6238 부록 B로 확인한다.
"""

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import quote, urlencode

PERIOD_SECONDS = 30
DIGITS = 6
SECRET_BYTES = 20
# 기기 시계 차이로 앞뒤 한 구간(±30초)까지 받는다.
DRIFT_STEPS = 1
_OTP = re.compile(r"[0-9]{6}")


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def time_step(unix_seconds: float) -> int:
    return int(unix_seconds) // PERIOD_SECONDS


def code_at(secret: bytes, step: int, *, digits: int = DIGITS) -> str:
    if type(step) is not int or not 0 <= step < 2**63:
        raise ValueError("시간 구간 범위 오류")
    digest = hmac.new(secret, step.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def matching_step(secret: bytes, otp: str, current_step: int) -> int | None:
    """맞는 시간 구간. 후보를 모두 비교해 어느 구간이 맞았는지 응답 시간으로 드러내지 않는다."""
    if not isinstance(otp, str) or _OTP.fullmatch(otp) is None:
        return None
    matched = None
    for step in range(current_step - DRIFT_STEPS, current_step + DRIFT_STEPS + 1):
        if step >= 0 and hmac.compare_digest(code_at(secret, step).encode("ascii"), otp.encode("ascii")):
            matched = step if matched is None else max(matched, step)
    return matched


def provisioning_uri(secret: bytes, account_label: str, *, issuer: str = "RE_CONNECT") -> str:
    """인증 앱 등록 주소. 라벨에는 실명·카카오 회원번호 대신 내부 운영자 별칭만 쓴다."""
    encoded = base64.b32encode(secret).decode("ascii").rstrip("=")
    query = urlencode({"secret": encoded, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD_SECONDS})
    return f"otpauth://totp/{quote(issuer)}:{quote(account_label)}?{query}"
