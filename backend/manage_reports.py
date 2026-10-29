"""앱 밖의 관리 진입점: 종결 후 30일이 지난 신고의 설명·처리 사유 정리 (W07-05)."""

import argparse
import asyncio
import json

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.core.config import get_settings


async def execute(limit):
    settings = get_settings()
    if settings.database_url is None:
        raise AppError('SERVICE_UNAVAILABLE')
    from app.main import create_app
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        return await app.state.report_service.purge(limit)


def main():
    parser = argparse.ArgumentParser(description='종결 후 30일이 지난 공고 오류 신고의 설명·처리 사유 정리')
    parser.add_argument('command', choices=['purge'])
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000: parser.error('limit은 1~1000입니다')
    try:
        count = asyncio.run(execute(args.limit))
    except (AppError, OSError, ValueError, ValidationError, RedisError, SQLAlchemyError):
        print(json.dumps({'completed': False, 'code': 'SERVICE_UNAVAILABLE'}))
        return 1
    print(json.dumps({'completed': True, 'processed': count}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
