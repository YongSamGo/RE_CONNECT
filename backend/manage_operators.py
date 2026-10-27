"""운영자 역할 부여·회수와 MFA 등록·복구 (W07-01). 앱 밖 서버 셸에서만 실행하며 공개 API로 열지 않는다.

    python manage_operators.py grant <user-id>      # 운영자 역할 부여 (대상은 한 번 로그인한 회원)
    python manage_operators.py enroll <user-id>     # 인증 앱 등록. 첫 코드를 확인해야 저장된다
    python manage_operators.py reset-mfa <user-id>  # 기기 분실 복구. 비밀값 폐기·모든 세션 종료 후 enroll
    python manage_operators.py revoke <user-id>     # 역할 회수. 비밀값 폐기·모든 세션 즉시 종료

<user-id>는 대상 회원이 로그인한 뒤 내 정보(/me)의 user.id다. 모든 명령은 감사 기록(actor_role=system)을 남긴다.
등록 주소(비밀값 포함)는 터미널에 한 번만 표시하고 로그·파일로 내보내지 않는다. OTP는 화면에 표시하지 않고 입력받는다.
"""

import argparse
from datetime import UTC, datetime
import getpass
import json
import sys
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.encryption import ContentCipher, EncryptionKeyRing, EncryptionUnavailable
from app.core.request_id import new_request_id
from app.modules.operators import totp
from app.modules.operators.repository import OperatorProcedureError, SqlOperatorMfaRepository
from app.persistence.connection import build_engine

ENROLL_ATTEMPTS = 3


def _user_id(value):
    try:
        parsed = UUID(value)
    except ValueError:
        raise argparse.ArgumentTypeError("회원 ID는 /me의 user.id(UUID)입니다") from None
    if str(parsed) != value.lower():
        raise argparse.ArgumentTypeError("회원 ID는 하이픈을 포함한 UUID 형식입니다")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="운영자 역할 부여·회수와 MFA 등록·복구")
    parser.add_argument("command", choices=["grant", "enroll", "reset-mfa", "revoke"])
    parser.add_argument("user_id", type=_user_id)
    return parser.parse_args(argv)


def enroll(repository, user_id, *, clock, prompt, show):
    """비밀값을 만들어 보여 주고, 인증 앱의 코드가 맞을 때만 저장한다. 실패하면 아무것도 남기지 않는다."""
    secret = totp.new_secret()
    show(totp.provisioning_uri(secret, "operator-" + user_id.hex[:8]))
    for _ in range(ENROLL_ATTEMPTS):
        now = clock()
        step = totp.matching_step(secret, prompt(), totp.time_step(now.timestamp()))
        if step is not None:
            repository.enroll(user_id, secret, step, now=now, request_id=new_request_id())
            return True
    return False


def execute(command, user_id, repository, *, clock=lambda: datetime.now(UTC), prompt=None, show=None):
    if command == "enroll":
        return {"completed": enroll(repository, user_id, clock=clock, prompt=prompt, show=show)}
    action = {"grant": repository.grant, "reset-mfa": repository.reset, "revoke": repository.revoke}[command]
    action(user_id, now=clock(), request_id=new_request_id())
    return {"completed": True}


def build_repository(settings):
    if settings.database_url is None:
        raise OperatorProcedureError("unavailable")
    try:
        cipher = ContentCipher(EncryptionKeyRing.from_settings(settings))
    except EncryptionUnavailable:
        raise OperatorProcedureError("unavailable") from None
    engine = build_engine(settings)
    return engine, SqlOperatorMfaRepository(sessionmaker(engine).begin, cipher)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "enroll" and not (sys.stdin.isatty() and sys.stdout.isatty()):
        # 등록 주소에 비밀값이 들어 있으므로 파이프·로그 파일로 출력하지 않는다.
        print(json.dumps({"completed": False, "code": "tty_required"}))
        return 1
    engine = None
    try:
        engine, repository = build_repository(get_settings())
        result = execute(args.command, args.user_id, repository,
                         prompt=lambda: getpass.getpass("인증 앱의 6자리 코드: ").strip(),
                         show=lambda uri: print("인증 앱에 아래 주소를 등록하세요(한 번만 표시):\n" + uri))
    except OperatorProcedureError as error:
        print(json.dumps({"completed": False, "code": error.code}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({"completed": False, "code": "unavailable"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    if args.command == "enroll" and not result["completed"]:
        print(json.dumps({"completed": False, "code": "code_mismatch"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
