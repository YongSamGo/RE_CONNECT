"""앱 밖의 관리 진입점: 보관기간(30일)이 지난 감사 기록 정리 (W07-06).

DB만 쓰므로 Redis·앱 조립 없이 실행한다. 주기 실행 연결은 #96(W12-07)이다.
결과는 처리 건수만 출력하고 오류 원문·연결 정보는 출력하지 않는다.
"""

import argparse
import json

from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.core.config import get_settings
from app.modules.audit.repository import SqlAuditRepository
from app.modules.audit.service import AuditService
from app.persistence.connection import build_engine


def execute(command):
    settings = get_settings()
    if settings.database_url is None:
        raise AppError("SERVICE_UNAVAILABLE")
    engine = build_engine(settings)
    try:
        return AuditService(SqlAuditRepository(engine.connect, engine.begin)).prune()
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description="보관기간이 지난 감사 기록 정리")
    parser.add_argument("command", choices=["prune"])
    args = parser.parse_args(argv)
    try:
        count = execute(args.command)
    except (AppError, OSError, ValueError, SQLAlchemyError):
        print(json.dumps({"completed": False, "code": "SERVICE_UNAVAILABLE"}))
        return 1
    print(json.dumps({"completed": True, "processed": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
