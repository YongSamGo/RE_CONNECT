"""인증 제공자 경계. 계정 연결·클라이언트 토큰 전달은 포함하지 않는다."""

from typing import Protocol


class OAuthFailure(Exception):
    """인가 코드·토큰·외부 응답이 없는 고정 인증 실패."""


class OAuthProvider(Protocol):
    def authorization_url(self, state: str, challenge: str, purpose: str) -> str: ...
    async def exchange(self, code: str, verifier: str) -> str: ...
