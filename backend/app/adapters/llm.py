"""텍스트 LLM Adapter 인터페이스.

서비스는 이 Protocol에만 의존하고, Ollama 구현(W04-02)은 이 모듈을 따르는 별도 클래스로 둔다.
구현은 서비스가 넘긴 Pydantic 모델로 결과를 검증해 돌려주며, 계정·권한·검수 상태를 바꾸지 않는다 (Plan/03 §2).
"""

from collections.abc import Sequence
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMError(Exception):
    """LLM 호출 실패. 메시지는 고정 문구이며 입력·모델 출력 원문을 담지 않는다.

    서비스는 구현(Ollama 등)이 아니라 이 예외들로 오류 코드를 고른다 (docs/api/README.md §2.5).
    Adapter는 재시도하지 않는다. 재시도 여부는 서비스가 전체 제한시간 안에서 정한다 (Plan/05 §3).
    """


class LLMTimeoutError(LLMError):
    """제한시간 안에 응답이 오지 않음 → 503 `AI_TIMEOUT`."""


class LLMUnavailableError(LLMError):
    """런타임에 연결할 수 없거나, 모델이 없거나, 런타임이 오류로 답함 → 503 `MODEL_UNAVAILABLE`."""


class LLMInvalidOutputError(LLMError):
    """응답이 잘렸거나 JSON·`output_model` 검증에 실패함. 같은 입력으로 바로 재시도하지 않는다."""


class UntrustedTurn(BaseModel):
    """대화 한 턴. 역할은 서버가 정하고, `text`는 비신뢰 데이터(사용자 답변·이전 모델 출력)다.

    턴을 문자열 하나로 이어 붙이지 않고 따로 넘겨, 구현이 Ollama `/api/chat`의 `messages` 역할로 나눠 보내게 한다.
    그래야 답변 안의 "assistant:" 같은 문자열이 턴 경계로 읽히지 않는다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    text: str


class LLMAdapter(Protocol):
    async def is_ready(self) -> bool:
        """모델이 적재돼 요청을 받을 수 있는지. 상태 확인(`/health/ready`)에 쓴다."""
        ...

    async def generate_structured(
        self,
        *,
        instructions: str,
        untrusted_turns: Sequence[UntrustedTurn],
        output_model: type[OutputT],
    ) -> OutputT:
        """서버가 만든 지시문과 비신뢰 대화 턴을 분리해 넘기고, `output_model`로 검증한 결과를 받는다.

        한 번만 묻는 추출(공고 원문 등)은 `user` 턴 하나로 넘긴다.
        제한시간 초과·모델 장애·검증 실패는 위의 `LLMError` 하위 예외로 알린다. 예외 메시지에 입력 원문을 넣지 않는다.
        """
        ...
