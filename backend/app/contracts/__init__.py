"""공통 데이터 계약 (W02-04, Plan/02 §2~4).

API·수집기·평가 도구가 같은 Pydantic 타입과 지역 목록을 쓴다. 필드 정의의 원본은 docs/api/openapi.yaml이다.

- `regions`: 시·도·시·군·구 목록과 `Region`
- `profile`: 프로필·경험
- `requirement`: 공고 자격조건과 필드별 연산 허용표
- `opportunity`: 운영자가 등록·수정하는 공고 내용
- `time`: UTC 저장·한국 날짜 계산

이 패키지는 `modules`·`adapters`·`core`에 의존하지 않는다. tests/test_architecture.py가 검사한다.
"""
