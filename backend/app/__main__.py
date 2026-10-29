"""안전한 로그 설정으로 실행: backend/에서 python -m app.

기본은 루프백(127.0.0.1)이다. 컨테이너 안에서만 `--host 0.0.0.0`으로 내부 네트워크에 연다.
"""

import argparse
import ipaddress
import sys
from collections.abc import Sequence

import uvicorn

from app.core.safe_logging import LOGGING_CONFIG
from app.core.config import get_settings


def _bind_host(value: str) -> str:
    """이름 해석 없이 IP 주소만 받는다."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise argparse.ArgumentTypeError("IP 주소만 지정할 수 있습니다") from None


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("--host", type=_bind_host, default="127.0.0.1")
    args = parser.parse_args([] if argv is None else argv)
    trusted = [str(address) for address in get_settings().trusted_proxy_ips]
    uvicorn.run(
        "app.main:app", host=args.host, port=8000, access_log=False, log_config=LOGGING_CONFIG,
        proxy_headers=bool(trusted), forwarded_allow_ips=trusted,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
