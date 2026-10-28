"""Compose 내부 전용 ASGI 진입점. 모델은 별도 프로세스에서 실행한다."""

from app.service import create_app

app = create_app()
