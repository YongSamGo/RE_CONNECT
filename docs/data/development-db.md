# 개발 DB·Redis와 마이그레이션 (W02-07)

관련 #18. 선행 #16/#17의 15개 물리 테이블에 Alembic을 적용한다. 운영 RDS·EC2 배포는 별도다.

## 로컬 실행

루트 `.env.example`을 `.env`로 복사하고 개발용 POSTGRES_PASSWORD·REDIS_PASSWORD를 채운다.
각각 `python -c "import secrets; print(secrets.token_hex(24))"`로 만든 서로 다른 값을 쓸 수 있다.
Redis 비밀번호는 32자 이상 hex만 허용하며 argv나 임시 파일 대신 stdin으로 서버에 전달한다.
설정 파일의 실제 값·URL을 대화·로그·커밋에 옮기지 않는다.

`DATABASE_URL`은 `postgresql+psycopg://사용자:비밀번호@127.0.0.1:5432/DB`,
`REDIS_URL`은 `redis://:비밀번호@127.0.0.1:6379/0` 형식이다. 예제의 APP_ENV=development
주석을 개발 PC에서만 해제한다. 설정 객체는 URL을 SecretStr로 받고 repr에서 숨긴다.

저장소 루트에서 실행한다:

```powershell
docker compose --env-file .env -f infra/compose.dev.yaml up -d --wait
```

이후 backend 가상환경을 활성화하고 `backend/`에서 실행한다:

```powershell
python -m alembic upgrade head
python -m alembic check
```

종료는 루트에서 `docker compose --env-file .env -f infra/compose.dev.yaml down`이다.
개발 PostgreSQL과 Redis는 모두 tmpfs이며 영구 볼륨·파일 로그가 없다. 컨테이너 종료/재생성 시
데이터가 사라질 수 있으므로 실제 개인정보를 넣지 않는다. 운영 DB로 쓰면 안 된다.
호스트 포트는 127.0.0.1에만 바인딩한다. 컨테이너 간 `data` 네트워크는 internal이며,
호스트 개발 백엔드가 접속할 수 있도록 별도 `local` 브리지에도 연결한다. internal 네트워크만
연결하면 Docker가 호스트 포트를 게시하지 않는다. local 브리지가 있으므로 두 컨테이너의
인터넷 송신까지 격리한 구성이 아니며, 운영의 비공개 네트워크 구성을 대신하지 않는다.
Redis RDB save와 AOF를 모두 끈다. 호스트의 swap·Docker VM snapshot은 tmpfs만으로
통제되지 않으므로 운영 음성/개인정보의 저장 경계 검증은 #92/#102에서 별도로 한다.

## 스키마와 불변 버전

- 0001은 모델의 독립 스냅샷으로 15개 테이블을 만든다. 현재 모델을 import해 과거 스키마를 바꾸지 않는다.
- 0002는 프로필/지원서 저장본의 SQL UPDATE를 차단하고 공고 콘텐츠 변경은 새 버전으로 강제한다.
  공고의 검수 상태·검수 시각·확인 시각·모집 종료 방향 변경은 허용한다. 재개는 새 pending 버전이 필요하다.
- `downgrade 0001_persistent_schema`는 추가 트리거만 되돌린다. `downgrade base`는 테이블/자료를 삭제한다.
  후자는 CI의 가상 DB 재현 시험용이며 운영 롤백 절차로 쓰지 않는다.

SQLAlchemy는 URL·SQL 파라미터를 echo하지 않는다. 앱은 설정된 DB·Redis의 실제 probe를
readiness에 사용하고 종료 시 연결 풀을 정리한다. DB는 SELECT 1, Redis는 PING과
save/appendonly 설정을 검사한다. Redis 권한이 설정 조회를 허용하지 않거나 영속화가 켜져 있으면
readiness는 실패한다. 앱 시작 시 자동 마이그레이션은 하지 않는다.

운영 PostgreSQL 연결은 sslmode=verify-full·sslrootcert가 있어야 한다. 실제 CA·호스트 검증은
psycopg가 연결할 때 수행하며 구성 문자열 검사만으로 TLS 연결 성공을 주장하지 않는다.
Redis 운영 ACL/TLS·공개 정책·컨테이너 로그 수집은 후속 배포 작업이다.

## 검증

로컬 PostgreSQL/Redis가 없는 환경에서는 해당 시험을 명시적으로 skip한다.
CI의 `PostgreSQL Redis 통합` 잡은 같은 Compose를 실제로 올리고 아래를 검증한다:

1. 빈 PostgreSQL DB에서 upgrade head·alembic check.
2. 소유권·버전·공개 포인터·삭제 제약을 SQLite와 PostgreSQL에서 반복 검증.
3. 초기/추가 마이그레이션의 정상 조회·자료 보존·downgrade/재upgrade와 스키마 일치.
4. 직접 SQL UPDATE 차단과 허용된 운영 상태 갱신.
5. 실제 DB/Redis probe, Redis 영속화가 켜지면 readiness 거절.

실제 서버로 로컬에서 반복하려면 PERSISTENCE_TEST_DATABASE_URL·PERSISTENCE_TEST_REDIS_URL을
가상 시험용 DB로 설정하고 해당 pytest를 실행한다. 각 PostgreSQL 시험은 임의의 별도 schema를
만들고 제거하므로 운영 DB URL을 지정하지 않는다. CI에는 한 번 쓰고 폐기하는 공개 가상 자격증명만 둔다.

## 공식 참조와 적용 범위

Security/INDEX.md에서 선택한 SQL 삽입·부적절한 인가·암호화되지 않은 중요정보 원문 경로와
장절·PDF 페이지는 [영구 모델 기록](persistence.md#보안-원문-연결)에 명시했다.
RDS TLS·개발 tmpfs·비영속 Redis와 트리거의 구체 구성은 프로젝트 설계다.
Alembic은 [공식 튜토리얼](https://alembic.sqlalchemy.org/en/latest/tutorial.html), Redis 비영속화는
[공식 문서](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/), Compose internal은
[공식 문서](https://docs.docker.com/reference/compose-file/networks/)를 확인했다.
