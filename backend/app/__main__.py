"""안전한 로그 설정으로 실행: backend/에서 python -m app."""

import uvicorn

from app.core.safe_logging import LOGGING_CONFIG


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False, log_config=LOGGING_CONFIG)


if __name__ == "__main__":
    main()
