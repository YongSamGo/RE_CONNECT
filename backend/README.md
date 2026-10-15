# backend — FastAPI 서버

담당: C · 백엔드·보안

하나의 FastAPI 서비스 안에서 기능별 책임을 나누는 모듈형 모놀리스다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)). 공고 수집기도 별도 서비스로 나누지 않고 이 패키지의 모듈로 두며, 6시간 주기의 별도 실행 명령으로 돌린다. API와 수집기가 같은 Pydantic 타입(W02-04)을 쓰기 위해서다.

## 예정 구조

골격은 [#14 W02-03](https://github.com/YongSamGo/RE_CONNECT/issues/14)에서 만든다.

```
backend/
├── app/                  # FastAPI 앱 (설정·라우터·서비스·저장소·Adapter)
├── tests/                # 이 패키지의 단위·통합 테스트 (pytest)
├── requirements.in       # 직접 쓰는 운영 의존성
├── requirements-dev.in   # 테스트·개발 도구
├── requirements.txt      # 컴파일 결과 (해시 포함, 직접 고치지 않음)
├── requirements-dev.txt
├── requirements-pip-tools.in    # 컴파일 도구 (pip-tools) 버전
└── requirements-pip-tools.txt   # 컴파일 도구 해시 잠금
```

## 의존성 고정

`*.in`에 직접 쓰는 패키지만 적고, pip-tools로 해시가 포함된 `*.txt`를 만들어 함께 커밋한다. CI는 `requirements.txt`·`requirements-dev.txt`로 설치하고 `pip-audit`으로 검사한다.

- `requirements-dev.in` 첫 줄에 `-c requirements.txt`를 적어 운영 의존성과 버전이 어긋나지 않게 한다.
- CI·운영과 같은 Linux·Python 3.12에서 컴파일한다. Windows에서 컴파일하면 플랫폼 전용 패키지가 섞일 수 있으니 아래 Docker 명령이나 WSL을 쓴다.
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

`requirements.txt`가 생기면 CI의 Python 점검(pytest·Bandit·pip-audit)이 자동으로 켜진다. 같은 PR에서 테스트를 최소 하나 넣고, [dependabot.yml](../.github/dependabot.yml)의 `pip` 항목 주석을 해제한다.

## 설정

설정값은 루트 `.env`에서 환경변수로 읽는다 ([.env.example](../.env.example)). 코드·테스트·로그에 비밀값을 적지 않는다.
