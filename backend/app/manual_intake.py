"""운영자 전용 공식 수동 자료 입력/목표 집계. 입력은 stdin UTF-8 JSON 한 건."""

import argparse
import json
import sys

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.collect import store_factory
from app.core.business_errors import AppError
from app.core.config import get_settings
from app.modules.ingestion.manual import ManualIntake, read_input
from app.persistence.connection import build_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--validate", action="store_true", help="DB 쓰기 없이 형식 검사만 수행, 진위/유효성 증명 아님")
    mode.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        material = None if args.progress else read_input(sys.stdin.buffer)
        if args.validate:
            print('{"status":"format_valid","review_status":"pending"}')
            return 0
        engine = build_engine(get_settings(), poolclass=NullPool)
        service = ManualIntake(sessionmaker(engine).begin, store_factory)
        if args.progress:
            print(json.dumps(service.progress()))
        else:
            result = service.record(material)
            print(json.dumps({"status": result.outcome, "opportunity_id": str(result.opportunity_id), "version": result.version}))
        return 0
    except KeyboardInterrupt:
        print('{"status":"cancelled"}')
        return 130
    except AppError as exc:
        print(json.dumps({"status": "rejected", "code": exc.code}))
        return 1
    except Exception:
        print('{"status":"rejected"}')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
