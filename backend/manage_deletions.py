"""앱 밖의 관리 진입점: main의 조립을 사용한 삭제 재시도·공개 전 복구 재적용."""

import argparse
import asyncio
import json

from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.business_errors import AppError
from app.core.config import get_settings


async def execute(command, limit):
    settings = get_settings()
    if settings.database_url is None or settings.redis_url is None:
        raise AppError('SERVICE_UNAVAILABLE')
    from app.main import create_app
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        service = app.state.deletion_service
        if command == 'retry': count = await service.retry(limit)
        elif command == 'recover': count = await service.recover(limit)
        else: count = await service.prune()
    return count


def main():
    parser = argparse.ArgumentParser(description='삭제 실패 재시도 또는 서비스 공개 전 복구 삭제 재적용')
    parser.add_argument('command', choices=['retry', 'recover', 'prune'])
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    maximum = 1000 if args.command == 'recover' else 100
    if not 1 <= args.limit <= maximum: parser.error(f'limit은 1~{maximum}입니다')
    try:
        count = asyncio.run(execute(args.command, args.limit))
    except (AppError, OSError, ValueError, ValidationError, RedisError, SQLAlchemyError):
        print(json.dumps({'completed': False, 'code': 'SERVICE_UNAVAILABLE'}))
        return 1
    print(json.dumps({'completed': True, 'processed': count}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
