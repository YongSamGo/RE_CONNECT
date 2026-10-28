# 릴리스와 EC2 배포 (#93 W12-04)

운영 이미지는 `main`의 `v*` 태그에서만 만들고, EC2에는 운영자가 릴리스 manifest의 digest로 직접 반영한다.
GitHub Actions는 EC2에 접속하지 않는다. 실제 AWS 계정·ECR·SSM·EC2 연결은 아직 검증하지 않았다(#90·#91·#92 대기).

## 1. 구성

| 파일 | 내용 |
| --- | --- |
| [`backend/Dockerfile`](../../backend/Dockerfile) | API·마이그레이션 공용 이미지. 해시 잠금 wheel만 설치, uid 10001, 셸 진입점 없음 |
| [`frontend/Dockerfile`](../../frontend/Dockerfile) | React 빌드를 담은 비루트 Nginx. 설정·인증서는 실행 시 연결 ([infra/nginx](../nginx), #91) |
| [`speech/Dockerfile`](../../speech/Dockerfile) | 음성 서비스 (#33). 운영 Compose 연결은 #92 |
| [`infra/compose.prod.yaml`](../compose.prod.yaml) | nginx(443만 공개)·backend·redis(비영속)·migrate(1회성) |
| [`.github/workflows/release.yml`](../../.github/workflows/release.yml) | PR 이미지 검사, 태그 릴리스 게시 |
| [`infra/release/`](../release) | 이미지 검사 판정·수용 목록·manifest 생성 |
| [`render_env.py`](render_env.py) | SSM 응답 → tmpfs env 파일 |

## 2. 릴리스 (CI)

1. `develop → main` 릴리스 PR을 머지한 뒤 `main` 커밋에 `vX.Y.Z` 태그를 push한다.
2. `Release` 워크플로가 태그 커밋이 `main` 이력에 있는지 확인하고 `release` 환경 승인을 기다린다.
3. backend·frontend·speech를 빌드하고 Trivy로 검사한다. 기준은 아래 3절이다. 하나라도 실패하면 아무것도 게시하지 않는다.
4. GitHub OIDC로 받은 임시 역할로 ECR에 올리고, 빌드 출처 증명(provenance)을 붙인다.
5. `release-manifest.json`과 SBOM(CycloneDX)을 **초안** Release에 첨부한다. 사람이 확인한 뒤 공개한다.

manifest에는 이미지 digest, 베이스 이미지 digest, 잠금 파일·모델 manifest·운영 Compose의 SHA-256,
프롬프트 버전, Alembic head, SBOM 해시가 들어간다. 비밀값·개인정보는 넣지 않는다.

Trivy 원본 결과(`*-scan.json`)는 미조치 취약점 목록이라 Release·artifact에 올리지 않는다.

## 3. 이미지 검사 기준

[`check_image_scan.py`](../release/check_image_scan.py)가 판정한다.

- CRITICAL은 수정판 유무와 관계없이 실패한다.
- 수정판이 있는 HIGH는 실패한다. 베이스 이미지나 패키지를 올려 다시 빌드한다.
- 수정판이 없는 HIGH는 [`image-scan-accept.json`](../release/image-scan-accept.json)에 이미지·ID·사유·기록일·만료일(90일 이내)이
  있어야 통과한다. 만료된 항목이 있으면 실패한다. `infra/release/`는 [CODEOWNERS](../../.github/CODEOWNERS) 대상이라
  수용 목록과 판정 기준을 바꾸려면 Code Owner 승인이 필요하다.
- 수용 목록은 공개 저장소에 있다. ID와 사유만 적고 내부 경로·재현 방법은 적지 않는다.

backend·음성 이미지는 같은 Debian 13 베이스라 수정판 없는 OS HIGH가 있다([CONTAINER_RUNTIME.md](../../speech/CONTAINER_RUNTIME.md)).
2026-10-28에 8개 ID를 두 이미지에 대해 검토해 2027-01-26 만료로 수용 목록에 올렸다. 만료 전에 베이스 갱신 여부를 다시 검토한다.
음성 이미지는 같은 베이스에 OS 패키지를 추가하지 않아 같은 목록을 적용했고, 실제 판정은 첫 릴리스 태그에서 확인한다.

## 4. 저장소·AWS 준비 (admin, 1회)

- GitHub **Settings → Environments → `release`**: 필수 승인자, 배포 대상은 `v*` 태그만.
- 저장소 변수(Variables, 비밀 아님): `AWS_REGION`, `AWS_RELEASE_ROLE_ARN`, `ECR_REGISTRY`(`<계정>.dkr.ecr.<리전>.amazonaws.com`).
- IAM OIDC 역할 신뢰 조건: `token.actions.githubusercontent.com:aud = sts.amazonaws.com`,
  `sub = repo:YongSamGo/RE_CONNECT:environment:release`. 권한은 세 ECR 저장소의 push만.
- ECR 저장소 `reconnect-backend`·`reconnect-frontend`·`reconnect-speech`: 태그 불변(IMMUTABLE), push 시 검사.
- EC2 인스턴스 역할: 세 저장소 pull, `ssm:GetParametersByPath`(`/re-connect/<env>/*`), 해당 KMS 키 복호화,
  운영 로그 그룹 쓰기. 쓰기·삭제 권한은 주지 않는다.

## 5. 비밀값 (SSM Parameter Store)

모든 값은 `SecureString`으로 둔다. 경로마다 받는 이름이 정해져 있고 그 밖의 이름은 거절한다.

| 경로 | 필수 | 선택 |
| --- | --- | --- |
| `/re-connect/<env>/app/` | `DATABASE_URL`(reconnect_runtime), `REDIS_URL`, `REQUEST_LIMIT_KEY`, `PUBLIC_ORIGIN`, `DATA_ENCRYPTION_KEYS`, `DATA_ENCRYPTION_ACTIVE_KEY_ID` | 카카오 3종, `DATA_GO_KR_SERVICE_KEY`, `INFERENCE_CONTROL_EPOCH`, 안내문 버전·본문, `OLLAMA_MODEL` |
| `/re-connect/<env>/redis/` | `REDIS_PASSWORD`(hex 32자 이상) | — |
| `/re-connect/<env>/migrate/` | `DATABASE_URL`(reconnect_migrator) | — |

- `DATABASE_URL`은 `sslmode=verify-full&sslrootcert=/run/rds-ca.pem`이 없으면 거절한다.
- `REDIS_URL`은 내부 `redis` 서비스만 가리킬 수 있다.
- `APP_ENV`·`TRUSTED_PROXY_IPS`·`OLLAMA_BASE_URL`은 Compose에 고정돼 있어 SSM으로 바꿀 수 없다.
- 값은 줄바꿈 없이 한 줄로 저장한다(JSON은 압축해서 저장). Compose는 env 파일을 `format: raw`로 읽어 `$`·따옴표를 해석하지 않는다.

## 6. 배포 (운영자, EC2)

root 셸에서 저장소의 릴리스 태그 체크아웃을 기준으로 실행한다. `/run`은 tmpfs라 재부팅하면 env 파일이 사라진다.

```bash
install -d -m 700 /run/reconnect
gh release download vX.Y.Z -R YongSamGo/RE_CONNECT -p release-manifest.json -D /run/reconnect
gh attestation verify oci://<ECR_REGISTRY>/reconnect-backend@<digest> -R YongSamGo/RE_CONNECT   # 세 이미지 모두
python3 -I infra/release/release_manifest.py images-env /run/reconnect/release-manifest.json --output /run/reconnect/images.env
printf 'AWS_REGION=%s\nDEPLOY_ENV=%s\n' ap-northeast-2 production >> /run/reconnect/images.env

for role in app redis migrate; do
  aws ssm get-parameters-by-path --path "/re-connect/production/$role/" --with-decryption --output json \
    | python3 -I infra/deploy/render_env.py --role "$role" --prefix "/re-connect/production/$role/" \
        --output "/run/reconnect/$role.env"
done
```

마이그레이션이 있는 릴리스는 앱을 올리기 전에 실행한다. manifest의 `migrations.heads`를 이전 릴리스와 비교한다.

1. RDS 수동 스냅샷을 만든다 (#94).
2. `docker compose --env-file /run/reconnect/images.env -f infra/compose.prod.yaml run --rm migrate`
3. 같은 migrator 계정으로 `infra/aws/grant_runtime.sql`을 다시 실행한다 (#90).

```bash
docker compose --env-file /run/reconnect/images.env -f infra/compose.prod.yaml up -d --wait
rm /run/reconnect/migrate.env
```

Nginx 설정·TLS 인증서·RDS CA는 `/etc/reconnect/`에 둔다(경로는 Compose 변수로 바꿀 수 있다). TLS 개인키는 uid 101만 읽을 수 있게 한다.
되돌리기는 이전 릴리스의 manifest로 같은 절차를 반복한다. 마이그레이션 되돌리기와 복구는 #97·#95가 다룬다.

## 7. 시험

```bash
python -I -m unittest discover -s infra/release/tests
python -I -m unittest discover -s infra/deploy/tests   # POSIX 권한 검사라 Linux에서 실행
```
