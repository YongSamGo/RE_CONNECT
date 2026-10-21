"""동기 SQL 작업 중 취소되어도 worker 종료 전에 연결을 닫지 않는다."""

import asyncio


async def run_query(function, *args):
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except BaseException:
            pass
        raise
