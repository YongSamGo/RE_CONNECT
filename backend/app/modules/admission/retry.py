"""하나의 admission 실행 안에서 종료가 확인된 일시 오류만 한 번 재시도한다."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.modules.admission.service import RuntimeCompletion

T = TypeVar('T')


async def retry_once(completion: RuntimeCompletion, operation: Callable[[RuntimeCompletion], Awaitable[T]],
                     transient: type[Exception]) -> T:
    # 전체 제한시간과 예산/lease는 호출자의 AdmissionService.run 하나가 관리한다.
    # 이전 시도의 늦은 callback은 새 시도의 종료를 확인할 수 없다.
    current = None
    try:
        for index in range(2):
            current = RuntimeCompletion()
            try:
                return await operation(current)
            except transient:
                if index == 1 or not current.ended:
                    raise
        raise RuntimeError('재시도 경계 오류')
    finally:
        if current is not None and current.ended:
            completion.confirm_ended()
