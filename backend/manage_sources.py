"""앱 밖의 관리 진입점: 공고 수집 출처(senuri·volunteer) 등록과 활성화.

    python manage_sources.py list
    python manage_sources.py register            # 두 출처를 비활성으로 등록(이미 있으면 값만 확인)
    python manage_sources.py enable senuri       # 수집 타이머 대상에 넣는다
    python manage_sources.py disable volunteer

출처의 코드·이름·URL은 아래 허용 목록에 고정한다. 인자로 URL을 받지 않는다. 이미 있는 행의
URL·이름이 허용 목록과 다르면 고치지 않고 실패한다(변조 의심). 출력에는 상태와 코드만 남긴다.
"""

import argparse
import json

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.modules.ingestion.runs import BASE_URLS, DAILY_LIMITS
from app.persistence.connection import build_engine
from app.persistence.operations import Source

# 수집기가 아는 출처만 받는다. URL은 수집기(BASE_URLS)와 같은 값을 쓴다 (docs/data/field-mapping.md 1절).
OFFICIAL = {
    "senuri": {
        "name": "한국노인인력개발원 노인 구인정보",
        "base_url": BASE_URLS["senuri"],
        "terms_url": "https://www.data.go.kr/data/15015153/openapi.do",
    },
    "volunteer": {
        "name": "행정안전부 봉사참여정보서비스 (1365)",
        "base_url": BASE_URLS["volunteer"],
        "terms_url": "https://www.data.go.kr/data/15157582/openapi.do",
    },
}
if set(OFFICIAL) != set(DAILY_LIMITS):
    raise RuntimeError("수집기 출처와 허용 목록이 달라졌다")


class SourceError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _matches(row, code):
    expected = OFFICIAL[code]
    return row.base_url == expected["base_url"] and row.name == expected["name"] and row.terms_url == expected["terms_url"]


def list_sources(engine):
    with engine.connect() as db:
        rows = {row.code: row for row in db.execute(select(Source.code, Source.name, Source.base_url, Source.terms_url, Source.enabled, Source.last_success_at))}
    result = []
    for code in sorted(OFFICIAL):
        row = rows.get(code)
        result.append({
            "code": code,
            "registered": row is not None,
            "official": row is not None and _matches(row, code),
            "enabled": bool(row and row.enabled),
            "last_success_at": row.last_success_at.isoformat() if row and row.last_success_at else None,
        })
    return result


def register(engine):
    """없는 출처는 비활성으로 추가한다. 있는 출처는 허용 목록과 같은지만 확인한다(멱등)."""
    created = []
    with engine.begin() as db:
        rows = {row.code: row for row in db.execute(select(Source.code, Source.name, Source.base_url, Source.terms_url).with_for_update())}
        for code in sorted(OFFICIAL):
            row = rows.get(code)
            if row is None:
                db.execute(Source.__table__.insert().values(code=code, enabled=False, **OFFICIAL[code]))
                created.append(code)
            elif not _matches(row, code):
                raise SourceError("SOURCE_MISMATCH")
    return created


def set_enabled(engine, code, enabled):
    if code not in OFFICIAL:
        raise SourceError("UNKNOWN_SOURCE")
    with engine.begin() as db:
        row = db.execute(select(Source.code, Source.name, Source.base_url, Source.terms_url).where(Source.code == code).with_for_update()).one_or_none()
        if row is None:
            raise SourceError("SOURCE_NOT_REGISTERED")
        # 켜기만 허용 목록과 같아야 한다. 끄기는 수집을 멈추는 안전한 쪽이라, 값이 달라진(변조 의심) 행도
        # 메타데이터는 그대로 둔 채 바로 끌 수 있어야 한다. 수집기는 요청마다 enabled를 다시 확인한다.
        if enabled and not _matches(row, code):
            raise SourceError("SOURCE_MISMATCH")
        db.execute(update(Source).where(Source.code == code).values(enabled=enabled))


def main(argv=None, engine=None):
    parser = argparse.ArgumentParser(description="공고 수집 출처 등록·활성화 (senuri·volunteer)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("register")
    for name in ("enable", "disable"):
        commands.add_parser(name).add_argument("code", choices=sorted(OFFICIAL))
    args = parser.parse_args(argv)
    try:
        if engine is None:
            settings = get_settings()
            if settings.database_url is None:
                raise SourceError("SERVICE_UNAVAILABLE")
            engine = build_engine(settings, poolclass=NullPool)
        if args.command == "list":
            output = {"completed": True, "sources": list_sources(engine)}
        elif args.command == "register":
            output = {"completed": True, "created": register(engine)}
        else:
            set_enabled(engine, args.code, args.command == "enable")
            output = {"completed": True, "code": args.code, "enabled": args.command == "enable"}
    except SourceError as error:
        print(json.dumps({"completed": False, "code": error.code}))
        return 1
    except (OSError, ValueError, SQLAlchemyError):
        print(json.dumps({"completed": False, "code": "SERVICE_UNAVAILABLE"}))
        return 1
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
