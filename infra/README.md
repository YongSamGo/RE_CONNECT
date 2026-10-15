# infra — Compose·Nginx·배포 설정

담당: C · 백엔드·보안

## 예정 파일

| 파일 | 내용 | 이슈 |
| --- | --- | --- |
| `compose.dev.yaml` | 로컬 개발용 PostgreSQL·Redis·내부 네트워크 | [#18 W02-07](https://github.com/YongSamGo/RE_CONNECT/issues/18) |
| `compose.prod.yaml` | EC2용 Nginx·FastAPI·Redis·Ollama·음성 서비스. PostgreSQL은 외부 RDS | [#92](https://github.com/YongSamGo/RE_CONNECT/issues/92)·[#93](https://github.com/YongSamGo/RE_CONNECT/issues/93) |
| `nginx/` | `/`는 React 정적 파일, `/api/*`는 FastAPI로 전달 (접두사 유지) | [#91](https://github.com/YongSamGo/RE_CONNECT/issues/91) |

## 실행 방법

Compose 파일은 이 폴더에 두고 `.env`는 루트에 하나만 둔다. `-f`로 이 폴더의 파일을 지정하면 Compose가 `.env`를 `infra/`에서 찾으므로 항상 `--env-file`을 붙인다. 저장소 루트에서 실행한다.

```bash
docker compose --env-file .env -f infra/compose.dev.yaml up -d
```

## 규칙

- 인터넷에는 Nginx의 HTTPS만 공개한다. Redis·Ollama·음성 서비스는 내부 네트워크에만 둔다.
- Redis는 RDB·AOF 영속화를 끄고, 개인정보를 영구 볼륨에 남기지 않는다.
- 운영 PostgreSQL은 Compose 컨테이너가 아니라 비공개 RDS다. 로컬 개발·시험에서만 Compose PostgreSQL을 쓴다.
- 이미지는 태그 대신 digest로 고정하는 것을 기본으로 한다.
- 빌드 컨텍스트(`backend/`·`frontend/`·`speech/`)마다 `.dockerignore`로 `.env`·키 파일이 이미지에 들어가지 않게 한다.
