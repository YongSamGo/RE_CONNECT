"""업무 서비스에 노출하는 LLM은 인증 주체·한도·공유 슬롯을 먼저 요구한다."""

from collections.abc import Callable, Sequence
from typing import Protocol

from app.adapters.llm import OutputT, UntrustedTurn
from app.core.business_errors import AppError
from app.modules.admission.service import AdmissionService, InferenceIdentity, UnavailableAdmissionService


class TerminalLLM(Protocol):
    async def is_ready(self) -> bool: ...
    def validate_request(self, *, instructions: str, untrusted_turns: Sequence[UntrustedTurn], output_model: type[OutputT]) -> None: ...
    async def generate_structured(self, *, instructions: str, untrusted_turns: Sequence[UntrustedTurn], output_model: type[OutputT], on_runtime_ended: Callable[[], None] | None = None) -> OutputT: ...


class ControlledLLMAdapter:
    def __init__(self, runtime: TerminalLLM, admission: AdmissionService | UnavailableAdmissionService):
        self._runtime = runtime
        self._admission = admission

    async def is_ready(self) -> bool:
        return await self._admission.is_ready() and await self._runtime.is_ready()

    def for_identity(self, identity: InferenceIdentity) -> 'IdentityBoundLLM':
        if not isinstance(identity, InferenceIdentity):
            raise ValueError('서버가 확인한 추론 주체가 필요합니다')
        return IdentityBoundLLM(self, identity)

    async def generate_structured(self, *, instructions: str, untrusted_turns: Sequence[UntrustedTurn], output_model: type[OutputT], identity: InferenceIdentity | None = None) -> OutputT:
        if identity is None:
            raise AppError("SERVICE_UNAVAILABLE")
        self._runtime.validate_request(instructions=instructions, untrusted_turns=untrusted_turns, output_model=output_model)
        return await self._admission.run(identity, "llm", lambda completion: self._runtime.generate_structured(
            instructions=instructions, untrusted_turns=untrusted_turns, output_model=output_model,
            on_runtime_ended=completion.confirm_ended,
        ))


class IdentityBoundLLM:
    """업무 호출 하나의 서버 주체를 고정한다. HTTP 입력에서 만들지 않는다."""
    def __init__(self, controlled: ControlledLLMAdapter, identity: InferenceIdentity):
        self._controlled, self._identity = controlled, identity

    async def is_ready(self) -> bool:
        return await self._controlled.is_ready()

    async def generate_structured(self, *, instructions: str, untrusted_turns: Sequence[UntrustedTurn], output_model: type[OutputT]) -> OutputT:
        return await self._controlled.generate_structured(instructions=instructions, untrusted_turns=untrusted_turns,
            output_model=output_model, identity=self._identity)
