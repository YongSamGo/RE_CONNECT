"""기능 모듈 (Plan/03 §2).

모듈마다 아래 파일로 책임을 나누고, 의존은 `router → service → repository/Adapter` 한 방향만 허용한다.

- `router.py`: HTTP 입출력만 다룬다. 저장소·Adapter 구현을 직접 import하지 않는다.
- `service.py`(또는 기능 이름의 파일): 업무 규칙. 저장소·Adapter는 Protocol로 받는다.
- `repository.py`: DB·Redis 접근. 다른 모듈의 저장소를 부르지 않는다.

이 규칙은 tests/test_architecture.py가 검사한다.
"""
