"""안전한 로그 설정으로 실행: backend/에서 python -m app."""

import uvicorn

from app.core.safe_logging import LOGGING_CONFIG
from app.core.config import get_settings


def main() -> None:
    trusted = [str(address) for address in get_settings().trusted_proxy_ips]
    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, access_log=False, log_config=LOGGING_CONFIG,
        proxy_headers=bool(trusted), forwarded_allow_ips=trusted,
    )


if __name__ == "__main__":
    main()
