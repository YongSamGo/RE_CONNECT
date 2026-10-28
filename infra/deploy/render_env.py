"""SSM Parameter Store 응답으로 컨테이너 env 파일을 만든다 (#93 W12-04).

EC2 인스턴스 역할로 읽은 결과를 표준 입력으로 받는다. 값은 출력·로그·명령행에 남기지 않는다.

    aws ssm get-parameters-by-path --path /re-connect/production/app/ --with-decryption \
      --output json | python3 -I infra/deploy/render_env.py --role app \
      --prefix /re-connect/production/app/ --output /run/reconnect/app.env

- 역할마다 허용 이름 목록만 받는다. 모르는 이름·중복·빠진 필수값이 있으면 아무것도 쓰지 않고 실패한다.
- Compose `format: raw`로 읽으므로 따옴표·$를 해석하지 않는다. 줄바꿈·NUL만 막으면 한 줄 한 값이 보장된다.
- 파일은 같은 폴더의 임시 파일(0600)에 쓴 뒤 교체한다. 보통 tmpfs인 /run/reconnect에 둔다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import IO
from urllib.parse import parse_qs, urlsplit

MAX_VALUE_LENGTH = 65536
_PREFIX = re.compile(r"^/re-connect/(staging|production)/(app|redis|migrate)/$")

ROLES: dict[str, dict[str, frozenset[str]]] = {
    "app": {
        "required": frozenset({
            "DATABASE_URL", "REDIS_URL", "REQUEST_LIMIT_KEY", "PUBLIC_ORIGIN",
            "DATA_ENCRYPTION_KEYS", "DATA_ENCRYPTION_ACTIVE_KEY_ID",
        }),
        "optional": frozenset({
            "KAKAO_REST_API_KEY", "KAKAO_CLIENT_SECRET", "KAKAO_APP_ID", "DATA_GO_KR_SERVICE_KEY",
            "INFERENCE_CONTROL_EPOCH", "AI_NOTICE_VERSION", "STORAGE_NOTICE_VERSION",
            "CONSENT_NOTICES_JSON", "OLLAMA_MODEL",
        }),
    },
    "redis": {"required": frozenset({"REDIS_PASSWORD"}), "optional": frozenset()},
    "migrate": {"required": frozenset({"DATABASE_URL"}), "optional": frozenset()},
}


class EnvError(ValueError):
    """값을 담지 않는 오류. 메시지에는 이름과 이유만 넣는다."""


def _check_database_url(value: str) -> None:
    try:
        url = urlsplit(value)
        query = parse_qs(url.query, strict_parsing=True)
    except ValueError:
        raise EnvError("DATABASE_URL 형식 오류") from None
    if url.scheme != "postgresql+psycopg" or not url.hostname:
        raise EnvError("DATABASE_URL은 postgresql+psycopg 주소여야 합니다")
    if query.get("sslmode") != ["verify-full"] or query.get("sslrootcert") != ["/run/rds-ca.pem"]:
        raise EnvError("DATABASE_URL에는 sslmode=verify-full과 sslrootcert=/run/rds-ca.pem이 필요합니다")


def _check_redis_password(value: str) -> None:
    if len(value) < 32 or not re.fullmatch(r"[0-9a-fA-F]+", value):
        raise EnvError("REDIS_PASSWORD는 32자 이상 hex여야 합니다")


def _check_redis_url(value: str) -> None:
    url = urlsplit(value)
    if url.scheme != "redis" or url.hostname != "redis" or url.username or not url.password:
        raise EnvError("REDIS_URL은 내부 redis 서비스와 비밀번호를 가리켜야 합니다")


VALUE_CHECKS = {
    "DATABASE_URL": _check_database_url,
    "REDIS_PASSWORD": _check_redis_password,
    "REDIS_URL": _check_redis_url,
}


def collect(document: object, role: str, prefix: str) -> dict[str, str]:
    if role not in ROLES:
        raise EnvError("알 수 없는 역할")
    match = _PREFIX.fullmatch(prefix)
    if not match or match.group(2) != role:
        raise EnvError("prefix는 /re-connect/<staging|production>/<역할>/ 이어야 합니다")
    if not isinstance(document, Mapping) or not isinstance(document.get("Parameters"), list):
        raise EnvError("SSM 응답 형식 오류")
    allowed = ROLES[role]["required"] | ROLES[role]["optional"]
    values: dict[str, str] = {}
    for item in document["Parameters"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("Name"), str) or not isinstance(item.get("Value"), str):
            raise EnvError("SSM 항목 형식 오류")
        name, value = item["Name"], item["Value"]
        if not name.startswith(prefix) or name[len(prefix):] not in allowed:
            # 허용 목록 밖 이름은 그대로 출력해도 값이 아니지만, 경로 구조만 알린다.
            raise EnvError("허용하지 않는 매개변수 이름")
        key = name[len(prefix):]
        if key in values:
            raise EnvError(f"{key}: 중복")
        if item.get("Type") != "SecureString":
            raise EnvError(f"{key}: SecureString이어야 합니다")
        if not value or len(value) > MAX_VALUE_LENGTH or any(char in value for char in "\r\n\0"):
            raise EnvError(f"{key}: 빈 값·길이 초과·줄바꿈은 허용하지 않습니다")
        check = VALUE_CHECKS.get(key)
        if check:
            check(value)
        values[key] = value
    missing = sorted(ROLES[role]["required"] - values.keys())
    if missing:
        raise EnvError("필수 값 없음: " + ", ".join(missing))
    return values


def private_directory(mode: int) -> bool:
    """그룹·기타 쓰기 권한이 없는 폴더인지."""
    return stat.S_ISDIR(mode) and not mode & (stat.S_IWGRP | stat.S_IWOTH)


def write_env(values: Mapping[str, str], output: Path) -> None:
    parent = output.parent
    if not private_directory(parent.stat().st_mode):
        raise EnvError("출력 폴더는 그룹·기타 쓰기 권한이 없어야 합니다")
    if output.is_symlink():
        raise EnvError("출력 경로가 심볼릭 링크입니다")
    temporary = parent / f".{output.name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for key in sorted(values):
                handle.write(f"{key}={values[key]}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None, stdin: IO[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", required=True, choices=sorted(ROLES))
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = json.load(stdin or sys.stdin)
    except ValueError:
        print("SSM 응답이 JSON이 아닙니다", file=sys.stderr)
        return 1
    try:
        values = collect(document, args.role, args.prefix)
        write_env(values, args.output)
    except (EnvError, OSError) as error:
        message = str(error) if isinstance(error, EnvError) else "env 파일을 쓰지 못했습니다"
        print(message, file=sys.stderr)
        return 1
    print(f"{args.role}: {len(values)}개 항목을 썼습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
