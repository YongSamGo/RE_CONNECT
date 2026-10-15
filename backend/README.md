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
└── requirements-dev.txt
```

## 의존성 고정

`*.in`에 직접 쓰는 패키지만 적고, pip-tools로 해시가 포함된 `*.txt`를 만들어 함께 커밋한다. CI는 `requirements.txt`·`requirements-dev.txt`로 설치하고 `pip-audit`으로 검사한다.

- `requirements-dev.in` 첫 줄에 `-c requirements.txt`를 적어 운영 의존성과 버전이 어긋나지 않게 한다.
- CI·운영과 같은 Linux·Python 3.12에서 컴파일한다. Windows에서 컴파일하면 플랫폼 전용 패키지가 섞일 수 있으니 아래 Docker 명령이나 WSL을 쓴다.

```bash
docker run --rm -v "$PWD:/src" -w /src python:3.12-slim sh -c "pip install pip-tools==7.6.2 && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements.txt requirements.in && pip-compile --generate-hashes --allow-unsafe --strip-extras -o requirements-dev.txt requirements-dev.in"
```

`requirements.txt`가 생기면 CI의 Python 점검(pytest·Bandit·pip-audit)이 자동으로 켜진다. 같은 PR에서 테스트를 최소 하나 넣고, [dependabot.yml](../.github/dependabot.yml)의 `pip` 항목 주석을 해제한다.

## 설정

설정값은 루트 `.env`에서 환경변수로 읽는다 ([.env.example](../.env.example)). 코드·테스트·로그에 비밀값을 적지 않는다.
