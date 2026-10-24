# 개발 환경 안내

새 작업 환경에서 같은 구조·같은 버전·같은 명령으로 개발하기 위한 안내다. 폴더별 세부 규칙은 각 폴더의 README에 있다.

## 1. 필요한 도구

| 도구 | 버전 | 기준 파일 |
| --- | --- | --- |
| Git | 최신 | — |
| Python | 3.12 | [.python-version](../.python-version) |
| Node.js | 24 (npm 포함) | [.nvmrc](../.nvmrc) |
| Docker | Docker Desktop 또는 Docker Engine + Compose v2 | — |

CI도 Python 3.12·Node 24를 쓴다 ([ci.yml](../.github/workflows/ci.yml)). 다른 Python이 기본으로 깔려 있으면 Windows에서는 `py -3.12`, macOS·Linux에서는 pyenv나 uv로 3.12를 지정한다.

## 2. 처음 받은 뒤

```bash
git clone https://github.com/YongSamGo/RE_CONNECT.git
```

루트에서 `.env.example`을 `.env`로 복사하고 필요한 값만 채운다. `.env`는 `.gitignore`로 막혀 있고, CI의 gitleaks가 커밋 이력 전체에서 비밀값을 찾는다.

```bash
cp .env.example .env
```

PowerShell에서는 `Copy-Item .env.example .env`를 쓴다.

개발 PC에서는 `.env`의 `# APP_ENV=development` 주석을 풀어 API 문서 화면(`/docs`)을 연다. 값이 없으면 운영(`production`)으로 동작하므로 운영 서버에서는 이 줄을 풀지 않는다.

## 3. 폴더 구조

| 폴더 | 내용 | 담당 |
| --- | --- | --- |
| [backend/](../backend/README.md) | FastAPI 서버. 공고 수집기도 이 안의 모듈 | C |
| [frontend/](../frontend/README.md) | React·TypeScript·Vite 클라이언트 | A |
| [speech/](../speech/README.md) | 로컬 STT·TTS 음성 서비스 컨테이너 | B |
| [infra/](../infra/README.md) | Compose·Nginx·배포 설정 | C |
| [tests/](../tests/README.md) | 서비스를 넘나드는 E2E·계약·보안 시나리오 시험 | 전원 |
| [worker/](../worker/README.md) | 공고 출처 조사 도구 (W01-05) | B |

단위 테스트는 각 프로젝트 안(`backend/tests/` 등)에 둔다.

## 4. 개발 명령

`cd`가 없는 명령은 저장소 루트에서, `cd backend 후`처럼 적힌 명령은 그 폴더에서 실행한다. "준비 중"인 명령은 해당 이슈가 끝나면 쓸 수 있다.

| 작업 | 명령 | 준비 |
| --- | --- | --- |
| 개발 DB·Redis 시작 | `docker compose --env-file .env -f infra/compose.dev.yaml up -d --wait` | 사용 가능. 비밀번호 설정과 휘발성 데이터 주의: [개발 DB 안내](data/development-db.md) |
| 개발 DB·Redis 종료 | `docker compose --env-file .env -f infra/compose.dev.yaml down` | 사용 가능. tmpfs의 개발 데이터가 삭제됨 |
| DB 마이그레이션 | `cd backend` 후 `python -m alembic upgrade head`, `python -m alembic check` | 사용 가능. DATABASE_URL 설정 필요 |
| 백엔드 가상환경 | `cd backend` 후 `python -m venv .venv` | 사용 가능 |
| 백엔드 의존성 설치 | `cd backend` 후 `pip install -r requirements.txt -r requirements-dev.txt` | 사용 가능 |
| 백엔드 테스트 | `cd backend` 후 `python -m pytest` | 사용 가능 |
| 백엔드 개발 서버 | `cd backend` 후 `python -m app` (안전한 JSON 로그, API 문서는 `APP_ENV=development`일 때만 `/docs`, 2절) | 사용 가능. DB·Redis 연결은 [#18](https://github.com/YongSamGo/RE_CONNECT/issues/18) |
| 프론트엔드 의존성 설치 | `cd frontend` 후 `npm ci --ignore-scripts` | 사용 가능 ([실행 안내](../frontend/DEVELOPMENT.md)) |
| 프론트엔드 개발 서버 | `cd frontend` 후 `npm run dev` | 사용 가능 ([실행 안내](../frontend/DEVELOPMENT.md)) |
| 프론트엔드 검사·빌드 | `cd frontend` 후 `npm run lint`, `npm run build` | 사용 가능 ([실행 안내](../frontend/DEVELOPMENT.md)) |
| 공고 샘플 수집 | `python worker/tools/fetch_source_samples.py <source> --operation <op>` | 사용 가능 |

가상환경 활성화는 macOS·Linux에서 `source .venv/bin/activate`, PowerShell에서 `.venv\Scripts\Activate.ps1`이다.

명령이 바뀌면 이 표를 같은 PR에서 고친다.

## 5. 버전 고정

| 대상 | 방식 |
| --- | --- |
| Python 패키지 | `requirements.in` → pip-tools로 해시 포함 `requirements.txt` 생성. 컴파일 이미지는 digest, pip-tools는 해시 잠금 파일로 고정 ([backend](../backend/README.md#의존성-고정)) |
| npm 패키지 | `package-lock.json` 커밋, `npm ci --ignore-scripts`로 설치 |
| CI 액션 | 커밋 SHA로 고정 ([CI 문서](security/ci-pipeline.md)) |
| 컨테이너 이미지 | digest 고정 ([infra](../infra/README.md)) |
| 모델 가중치 | 공식 배포원 revision·digest 고정, 저장소에 넣지 않음 ([speech](../speech/README.md)) |

Dependabot이 새 버전을 7일 기다린 뒤 업데이트 PR을 만든다. 직접 버전을 올릴 때도 배포된 지 7일이 지나지 않은 버전은 피한다.

예외: 알려진 취약점(`pip-audit`·`npm audit`에 걸린 권고)의 수정판은 7일을 기다리지 않고 올릴 수 있다. PR에 권고 ID, 공식 배포물과의 해시 대조, 바뀐 패키지가 수정 대상 하나뿐인지를 적고 Code Owner 승인을 받는다. 7일이 지난 뒤 같은 버전에 새 경보가 없는지 다시 확인한다(첫 사례: certifi 2026.10.19, PYSEC-2026-4320, #212).

## 6. 줄바꿈·편집기

- [.gitattributes](../.gitattributes)가 텍스트 파일을 LF로 통일한다. Windows에서 CRLF로 바뀐 셸 스크립트·Dockerfile은 Linux 컨테이너에서 실행되지 않기 때문이다.
- [.editorconfig](../.editorconfig)가 인코딩(UTF-8)·들여쓰기(Python 4칸, 그 외 2칸)를 맞춘다. VS Code는 EditorConfig 확장을 설치하면 적용된다.

## 7. 비밀값

- 비밀값은 루트 `.env`에만 둔다. 코드·테스트·로그·이슈·PR에 적지 않는다.
- 프론트엔드의 `VITE_` 환경변수는 브라우저에 그대로 공개되므로 비밀값을 넣지 않는다.
- Docker 빌드 컨텍스트마다 `.dockerignore`가 `.env`·키 파일을 이미지에서 뺀다.
- 운영 RDS 접속 정보·AWS 자격증명은 `.env.example`에 적지 않고 운영 환경에서만 설정한다.
