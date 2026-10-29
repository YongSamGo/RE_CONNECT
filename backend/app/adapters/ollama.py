"""내부 Ollama `/api/chat` Adapter (W04-02).

- 주소·모델은 설정으로만 정한다. 사용자 요청으로 바꾸지 않고 리다이렉트를 따라가지 않는다.
- 서버 지시문은 `system` 메시지 하나로, 비신뢰 대화 턴은 각자의 역할 메시지로 나눠 보낸다.
- `format`에 `output_model`의 JSON Schema를 넣고 `stream=false`로 최종 응답만 받는다.
- 응답에서는 `message.content`만 쓰고 `thinking`(추론 과정)은 버린다. content는 `output_model`로 다시 검증한다.
- 입력·모델 출력 원문은 예외 메시지와 로그에 남기지 않는다. 재시도는 하지 않는다 (app/adapters/llm.py).
"""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.adapters.llm import (
    LLMInvalidOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMTransientUnavailableError,
    OutputT,
    UntrustedTurn,
)

logger = logging.getLogger(__name__)


class _ResponseTooLarge(Exception):
    pass


class OllamaLLMAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        num_predict: int,
        think: bool | None,
        max_response_bytes: int,
        num_ctx: int = 16384,
        ready_timeout_seconds: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._num_predict = num_predict
        if num_ctx < num_predict + 4096:
            raise ValueError("컨텍스트에 입력과 출력의 여유가 필요합니다")
        self._num_ctx = num_ctx
        self._think = think
        self._max_response_bytes = max_response_bytes
        self._ready_timeout_seconds = ready_timeout_seconds
        # 테스트에서 가짜 전송 계층을 끼우기 위한 것이다. 목적지를 바꾸는 용도가 아니다.
        self._transport = transport

    def _client(self, timeout_seconds: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            transport=self._transport,
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,  # 프록시 환경변수로 내부 추론 요청이 밖으로 나가지 않게 한다
        )

    async def _post_json(self, client: httpx.AsyncClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """200 응답의 JSON 객체. 그 밖의 상태는 LLMUnavailableError, 크기 초과·깨진 JSON은 _ResponseTooLarge·ValueError."""
        async with client.stream("POST", path, json=payload) as response:
            if response.status_code != 200:
                # 오류 본문에는 모델 이름·입력 일부가 섞일 수 있어 읽지 않는다
                logger.warning("Ollama 오류 응답: path=%s status=%s", path, response.status_code)
                raise LLMUnavailableError("모델 런타임이 요청을 처리하지 못했습니다")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self._max_response_bytes:
                    raise _ResponseTooLarge
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("응답이 JSON 객체가 아님")
        return data

    async def is_ready(self) -> bool:
        """사전 적재된 설정 모델만 ready. health 요청에서 다운로드·적재하지 않는다."""
        try:
            async with self._client(self._ready_timeout_seconds) as client:
                async with asyncio.timeout(self._ready_timeout_seconds):
                    async with client.stream("GET", "/api/ps") as response:
                        if response.status_code != 200:
                            return False
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self._max_response_bytes:
                                return False
                    data = json.loads(body)
                    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                        return False
                    return any(
                        isinstance(model, dict) and model.get("name") == self._model
                        for model in data["models"]
                    )
        except Exception as exc:
            logger.info("Ollama 준비 확인 실패: type=%s", type(exc).__name__)
            return False

    def _payload(self, instructions: str, turns: Sequence[UntrustedTurn], output_model: type[BaseModel]) -> dict[str, Any]:
        messages = [{"role": "system", "content": instructions}]
        messages += [{"role": turn.role, "content": turn.text} for turn in turns]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "format": output_model.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0, "num_predict": self._num_predict, "num_ctx": self._num_ctx},
        }
        # 토큰을 문자 수로 추정하지 않는다. UTF-8 바이트에 보수적인 한도를 두고
        # 템플릿·특수 토큰에 2048, 출력에 num_predict를 별도로 남긴다.
        # 실제 모델 토크나이저·템플릿에 대한 대조는 모델 실측 단계에서 수행한다.
        input_bytes = len(json.dumps({"messages": messages, "format": payload["format"]}, ensure_ascii=False).encode("utf-8"))
        if len(turns) > 64 or input_bytes > min(16384, self._num_ctx - self._num_predict - 2048):
            raise ValueError("모델 입력 한도를 초과했습니다")
        if self._think is not None:
            payload["think"] = self._think
        return payload

    def validate_request(self, *, instructions, untrusted_turns, output_model) -> None:
        if not untrusted_turns:
            raise ValueError("대화 턴이 비어 있습니다")
        if output_model.model_config.get("extra") != "forbid":
            raise ValueError("출력 모델은 정의하지 않은 필드를 거절해야 합니다")
        self._payload(instructions, untrusted_turns, output_model)

    async def generate_structured(
        self,
        *,
        instructions: str,
        untrusted_turns: Sequence[UntrustedTurn],
        output_model: type[OutputT],
        on_runtime_ended: Callable[[], None] | None = None,
    ) -> OutputT:
        self.validate_request(instructions=instructions, untrusted_turns=untrusted_turns, output_model=output_model)
        payload = self._payload(instructions, untrusted_turns, output_model)
        try:
            async with self._client(self._timeout_seconds) as client:
                data = await asyncio.wait_for(self._post_json(client, "/api/chat", payload), self._timeout_seconds)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # 고정 내부 목적지에 연결하지 못해 추론 요청이 시작되지 않은 경우만 재시도 후보.
            if on_runtime_ended is not None:
                on_runtime_ended()
            raise LLMTransientUnavailableError("모델 런타임에 연결하지 못했습니다") from None
        except (TimeoutError, httpx.TimeoutException):
            raise LLMTimeoutError("모델 응답 시간이 초과되었습니다") from None
        except httpx.RequestError as exc:
            logger.warning("Ollama 연결 실패: type=%s", type(exc).__name__)
            raise LLMUnavailableError("모델 런타임에 연결하지 못했습니다") from None
        except (_ResponseTooLarge, ValueError):
            # json.JSONDecodeError도 ValueError다. 원문을 체인으로 남기지 않는다.
            raise LLMInvalidOutputError("모델 응답 형식이 올바르지 않습니다") from None

        # 입력/출력 검증 오류와 실제 연산 종료는 다르다. 정상 최종 응답에서만 슬롯 반환을 허용한다.
        if data.get("done") is True and data.get("done_reason") in ("stop", "length") and on_runtime_ended is not None:
            on_runtime_ended()
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if data.get("done") is not True or data.get("done_reason") != "stop" or not isinstance(content, str):
            # done_reason=length: num_predict에 걸려 잘린 출력이다. 런타임 문자열은 로그에 그대로 넣지 않는다.
            truncated = data.get("done_reason") == "length"
            logger.warning("Ollama 응답 미완료: truncated=%s", truncated)
            raise LLMInvalidOutputError("모델 응답이 완료되지 않았습니다")
        try:
            return output_model.model_validate_json(content)
        except ValidationError as exc:
            logger.warning("Ollama 출력 검증 실패: errors=%s", exc.error_count())
            raise LLMInvalidOutputError("모델 응답이 요구 형식과 다릅니다") from None
