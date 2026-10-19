# backend — FastAPI 서버

담당: C · 백엔드·보안

하나의 FastAPI 서비스 안에서 기능별 책임을 나누는 모듈형 모놀리스다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)). 공고 수집기도 별도 서비스로 나누지 않고 이 패키지의 모듈로 두며, 6시간 주기의 별도 실행 명령으로 돌린다. API와 수집기가 같은 Pydantic 타입(W02-04)을 쓰기 위해서다.

## 구조

```
backend/
├── app/
│   ├── main.py           # 앱 조립. 구체 구현(DB·Redis·Ollama·음성)은 여기서만 고른다
│   ├── core/             # 설정·요청 추적 ID·공통 오류 처리
│   ├── adapters/         # LLM·Speech Adapter 인터페이스(Protocol). 구현은 각 작업에서 더한다
│   ├── contracts/        # 공통 데이터 타입(프로필·공고·조건)·지역 목록·시각 처리 (W02-04)
│   └── modules/          # 기능 모듈 (Plan/03 §2). 지금은 operations(상태 확인)·regions(지역 목록)가 있다
├── tests/                # 이 패키지의 단위·통합 테스트 (pytest)
├── pyproject.toml        # pytest 설정만 둔다
├── requirements.in       # 직접 쓰는 운영 의존성
├── requirements-dev.in   # 테스트·개발 도구
├── requirements.txt      # 컴파일 결과 (해시 포함, 직접 고치지 않음)
├── requirements-dev.txt
├── requirements-pip-tools.in    # 컴파일 도구 (pip-tools) 버전
└── requirements-pip-tools.txt   # 컴파일 도구 해시 잠금
```

### 의존 방향

`router → service → repository/Adapter` 한 방향만 허용한다. 라우터는 저장소·Adapter를 직접 import하지 않고, 모듈은 다른 모듈의 저장소를 부르지 않는다. `core`·`adapters`는 `modules`에 의존하지 않는다. `contracts`는 수집기·평가 도구도 쓰므로 `app` 안의 다른 패키지를 import하지 않는다. [tests/test_architecture.py](tests/test_architecture.py)가 이 규칙을 검사한다.

### 공통 동작

- 모든 응답에 서버가 만든 `X-Request-ID`(`req_` + 32자 hex)를 붙인다. 클라이언트가 보낸 값은 쓰지 않는다.
- 오류는 `{code, message, request_id}`로 돌려준다(422만 `fields` 추가). 입력값·식별자 형식이 아닌 필드 이름·예외 메시지·추적 정보는 넣지 않는다. 405는 계약에 코드가 없어 404 `NOT_FOUND`로, 계약 코드가 없는 400·415 등은 422 `VALIDATION_FAILED`로 답한다.
- 처리하지 못한 예외는 `UnhandledErrorMiddleware`가 500으로 바꾸고 다시 던지지 않는다. 서버 로그에는 예외 종류와 `request_id`만 남는다.
- `/health/live`·`/health/ready`는 `/api/v1` 밖의 내부 전용 경로다. DB·Redis 실패는 503 `unavailable`, LLM·음성만 실패하면 200 `degraded`다. 연결 구현이 없는 구성 요소는 `fail`로 답한다.
- `APP_ENV`가 `development`일 때만 `/docs`·`/openapi.json`을 연다. 값이 없으면 `production`으로 본다.

## 공공 API 수집

공공 API의 고정 대상·DNS/IP·TLS·XML 수집 경계는 [modules/ingestion](app/modules/ingestion/README.md)에 있다. 원문 저장·정규화·스케줄 실행은 후속 작업이며 서버 시작 시 수집하지 않는다.

## 공통 데이터 계약

[app/contracts/](app/contracts/)는 API·수집기·평가 도구가 함께 쓰는 Pydantic 타입이다. 필드 정의의 원본은 [openapi.yaml](../docs/api/openapi.yaml)과 [Plan/02](../Plan/02_Data_Design.md)이고, 바꿀 때는 세 곳을 함께 고친다.

- 모든 모델은 정의하지 않은 키를 거절하고(`unknown_field`), 선택 항목도 키가 있어야 한다(`required`). 값이 없으면 `null`을 보낸다.
- 숫자·불리언·문자열은 형 변환 없이 받는다. number 자리의 `"3"`이나 `true`는 `invalid_type`이다.
- 자유 텍스트는 `fields.text()`로 만든다. NFC로 맞추고, 빈 문자열·공백뿐인 값과 보이지 않는 문자(제어 문자·폭 없는 문자·글자 방향 제어)를 거절한다. 줄바꿈·탭은 설명·안내처럼 여러 줄인 필드에서만 받는다.
- 공고 URL은 `https`이고 계정정보·백슬래시·fragment·443 외 포트가 없는 주소만 받는다. `deadline_date`와 `deadline_at`이 함께 있으면 같은 한국 날짜여야 한다.
- 지역은 [regions.py](app/contracts/regions.py)의 목록으로 검증한다. 시·군·구는 영문 slug이고, 경기도는 시·군 단위, 인천은 2026-07-01 행정체제 개편 뒤 기준이다. 목록을 바꾸면 `REGION_CATALOG_VERSION`을 올린다. 외부 출처의 지역코드 매핑은 수집기가 출처별로 맡는다.
- 자격조건은 [requirement.py](app/contracts/requirement.py)의 field·operator 허용표에 있는 조합만 받는다. 해석하지 못한 조건은 `field=other`, `clarity=needs_review`로 남긴다.
- 시각은 시간대가 있어야 하고 UTC로 바꿔 다룬다. 한국 날짜는 [time.py](app/contracts/time.py)의 `kst_date`·`kst_today`로만 계산한다. 한국은 서머타임이 없어 고정 오프셋 +09:00을 쓴다.

## 의존성 고정

`*.in`에 직접 쓰는 패키지만 적고, pip-tools로 해시가 포함된 `*.txt`를 만들어 함께 커밋한다. CI는 `requirements.txt`·`requirements-dev.txt`로 설치하고 `pip-audit`으로 검사한다.

- `requirements-dev.in` 첫 줄에 `-c requirements.txt`를 적어 운영 의존성과 버전이 어긋나지 않게 한다.
- CI·운영과 같은 Linux·Python 3.12에서 컴파일한다. Windows에서 컴파일하면 플랫폼 전용 패키지가 섞일 수 있으니 아래 Docker 명령이나 WSL을 쓴다.
- Linux에서 컴파일하면 Windows에서만 필요한 의존성(예: pytest·click의 `colorama`)이 빠진다. 해시 모드에서는 빠진 패키지 하나로 설치 전체가 실패하므로, 이런 패키지는 해당 `.in`에 직접 적는다.
- 배포된 지 7일이 지나지 않은 버전이 잡히면 그 패키지를 직전 버전으로 제한해 한 번 컴파일한 뒤, 제한 없이 다시 컴파일한다. pip-compile은 기존 `requirements.txt`의 고정값을 유지하므로 `.in`에 버전을 적지 않아도 된다.
- 컴파일 결과의 해시를 CI·운영 설치가 그대로 믿으므로, 컴파일 도구도 고정한다. 이미지는 digest로, pip-tools는 해시 잠금 파일 [requirements-pip-tools.txt](requirements-pip-tools.txt)로 설치한다.

`backend/` 폴더에서 셸에 맞는 명령을 실행한다.

PowerShell:

```powershell
docker run --rm -v "${PWD}:/src" -w /src python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 sh -c "pip install --require-hashes -r requirements-pip-tools.txt && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements.txt requirements.in && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements-dev.txt requirements-dev.in"
```

Git Bash (경로 자동 변환을 끈다), macOS·Linux:

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/src" -w /src python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 sh -c "pip install --require-hashes -r requirements-pip-tools.txt && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements.txt requirements.in && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements-dev.txt requirements-dev.in"
```

이미지 digest는 `python:3.12-slim`의 2026-10-15 기준값이다. 바꿀 때는 `docker buildx imagetools inspect python:3.12-slim`으로 확인해 두 명령을 함께 고친다. pip-tools를 올릴 때는 [requirements-pip-tools.in](requirements-pip-tools.in)의 버전을 고치고 잠금 파일 첫 줄의 명령으로 다시 만든다.

`requirements.txt`가 있으므로 CI의 Python 점검(pytest·Bandit·pip-audit)이 이 폴더에서 돈다. [dependabot.yml](../.github/dependabot.yml)의 `pip` 항목이 매주 업데이트 PR을 만든다.

## 설정

설정값은 루트 `.env`에서 환경변수로 읽는다 ([.env.example](../.env.example)). 코드·테스트·로그에 비밀값을 적지 않는다.
