"""음성(STT·TTS) Adapter 인터페이스.

내부 음성 서비스 연결(W04-06)이 이 Protocol을 구현한다. 원본 음성·합성 결과를 보관하지 않는다 (Plan/03 §1.2).
"""

from typing import Protocol


class SpeechAdapter(Protocol):
    async def is_ready(self) -> bool:
        """STT·TTS 모델이 모두 요청을 받을 수 있는지. 상태 확인(`/health/ready`)에 쓴다."""
        ...

    async def transcribe(self, audio: bytes, *, content_type: str) -> str:
        """한국어 음성을 전사한다. 크기·형식 검사는 API 계층에서 먼저 끝낸다."""
        ...

    async def synthesize(self, text: str) -> bytes:
        """서버가 고른 표시 문장(최대 2,000자)을 기본 한국어 화자로 읽은 WAV를 돌려준다."""
        ...
