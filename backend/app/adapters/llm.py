"""텍스트 LLM Adapter 인터페이스.

서비스는 이 Protocol에만 의존하고, Ollama 구현(W04-02)은 이 모듈을 따르는 별도 클래스로 둔다.
구현은 서비스가 넘긴 Pydantic 모델로 결과를 검증해 돌려주며, 계정·권한·검수 상태를 바꾸지 않는다 (Plan/03 §2).
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMAdapter(Protocol):
    async def is_ready(self) -> bool:
        """모델이 적재돼 요청을 받을 수 있는지. 상태 확인(`/health/ready`)에 쓴다."""
        ...

    async def generate_structured(
        self,
        *,
        instructions: str,
        untrusted_input: str,
        output_model: type[OutputT],
    ) -> OutputT:
        """지시문과 비신뢰 입력(사용자 대화·공고 원문)을 분리해 넘기고, `output_model`로 검증한 결과를 받는다.

        제한시간 초과·모델 장애·검증 실패는 구현이 정의하는 예외로 알린다. 예외 메시지에 입력 원문을 넣지 않는다.
        """
        ...
