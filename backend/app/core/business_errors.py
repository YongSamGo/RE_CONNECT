"""업무 오류의 고정 코드·HTTP 상태·안내문 (docs/api/README.md §2.5)."""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    message: str


ERRORS = MappingProxyType({
    "UNAUTHENTICATED": ErrorSpec(401, "로그인이 필요합니다."),
    "SESSION_EXPIRED": ErrorSpec(401, "이용 시간이 지났습니다. 다시 로그인해 주세요."),
    "FORBIDDEN": ErrorSpec(403, "이 작업을 할 권한이 없습니다."),
    "CSRF_FAILED": ErrorSpec(403, "요청을 확인할 수 없습니다. 화면을 새로 열어 주세요."),
    "MFA_REQUIRED": ErrorSpec(403, "운영자 추가 인증이 필요합니다."),
    "MFA_INVALID": ErrorSpec(403, "인증번호를 확인해 주세요."),
    "MFA_LOCKED": ErrorSpec(429, "인증 시도가 많습니다. 잠시 후 다시 시도해 주세요."),
    "CONSENT_REQUIRED": ErrorSpec(403, "안내 내용을 확인하고 필요한 동의를 선택해 주세요."),
    "REAUTH_REQUIRED": ErrorSpec(403, "본인 확인을 위해 다시 로그인해 주세요."),
    "NOT_FOUND": ErrorSpec(404, "찾을 수 없거나 이용 시간이 지났습니다."),
    "SAVE_INTENT_NOT_FOUND": ErrorSpec(404, "저장 대기를 찾을 수 없거나 이용 시간이 지났습니다."),
    "VERSION_CONFLICT": ErrorSpec(409, "정보가 변경되었습니다. 최신 내용을 확인해 주세요."),
    "IDEMPOTENCY_KEY_REUSED": ErrorSpec(409, "요청 정보가 변경되었습니다. 새 요청으로 다시 시도해 주세요."),
    "REQUEST_IN_PROGRESS": ErrorSpec(409, "요청을 처리하고 있습니다. 잠시 기다려 주세요."),
    "REQUEST_ALREADY_COMPLETED": ErrorSpec(409, "이미 처리된 요청입니다. 새 요청으로 다시 시도해 주세요."),
    "PROFILE_NOT_CONFIRMED": ErrorSpec(409, "프로필을 확인하고 확정해 주세요."),
    "PROFILE_NOT_SAVED": ErrorSpec(409, "먼저 근거 프로필을 저장해 주세요."),
    "DRAFT_NOT_APPROVED": ErrorSpec(409, "지원서를 확인하고 승인해 주세요."),
    "OPPORTUNITY_NOT_AVAILABLE": ErrorSpec(409, "지금은 이 공고를 이용할 수 없습니다."),
    "INVALID_STATE_TRANSITION": ErrorSpec(409, "현재 상태에서는 이 작업을 할 수 없습니다."),
    "ALREADY_SIGNED_IN": ErrorSpec(409, "이미 로그인되어 있습니다. 현재 화면에서 저장해 주세요."),
    "PAYLOAD_TOO_LARGE": ErrorSpec(413, "보낸 내용이 너무 큽니다."),
    "VALIDATION_FAILED": ErrorSpec(422, "입력 내용을 확인해 주세요."),
    "RATE_LIMITED": ErrorSpec(429, "요청이 많습니다. 잠시 후 다시 시도해 주세요."),
    "DAILY_QUOTA_EXCEEDED": ErrorSpec(429, "오늘 이용 한도에 도달했습니다. 다음 날 다시 시도해 주세요."),
    "INFERENCE_BUSY": ErrorSpec(429, "다른 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요."),
    "INTERNAL_ERROR": ErrorSpec(500, "일시적인 문제가 생겼습니다. 잠시 뒤 다시 시도해 주세요."),
    "MODEL_UNAVAILABLE": ErrorSpec(503, "지금은 AI 기능을 사용할 수 없습니다. 직접 작성하거나 잠시 후 다시 시도해 주세요."),
    "AI_TIMEOUT": ErrorSpec(503, "AI 처리 시간이 초과되었습니다. 직접 작성하거나 잠시 후 다시 시도해 주세요."),
    "SERVICE_UNAVAILABLE": ErrorSpec(503, "서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해 주세요."),
})


class AppError(Exception):
    """임의 메시지·상태·헤더 대신 검증된 코드만 받는 업무 예외.

    소유권 실패는 NOT_FOUND, 상태·버전 충돌은 해당 409 코드를 서비스에서 고른다.
    """

    def __init__(self, code: str, *, retry_after: int | None = None) -> None:
        if code not in ERRORS:
            raise ValueError("정의되지 않은 업무 오류 코드")
        if retry_after is not None:
            if type(retry_after) is not int or not 1 <= retry_after <= 86400:
                raise ValueError("재시도 대기 시간 범위 오류")
            if ERRORS[code].status != 429 and code != "REQUEST_IN_PROGRESS":
                raise ValueError("재시도 헤더를 허용하지 않는 오류")
        if code == "REQUEST_IN_PROGRESS" and retry_after is None:
            raise ValueError("진행 중 요청은 재시도 대기 시간이 필요합니다")
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
