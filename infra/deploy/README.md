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
2. `Release` 워크플로가 `release` 환경 승인을 기다린다. 승인 뒤 첫 단계에서 태그 형식(`vX.Y.Z`, `-rc.N` 허용)과 태그 커밋이 `main` 이력에 있는지 확인하고, 아니면 아무것도 게시하지 않고 멈춘다.
3. backend·frontend·speech를 빌드하고 Trivy로 검사한다. 기준은 아래 3절이다. 하나라도 실패하면 아무것도 게시하지 않는다.
4. GitHub OIDC로 받은 임시 역할로 ECR에 올리고, 빌드 출처 증명(provenance)을 붙인다.
5. `release-manifest.json`과 SBOM(CycloneDX)을 **초안** Release에 첨부한다. 사람이 확인한 뒤 공개한다.

manifest에는 이미지 digest, 베이스 이미지 digest, 잠금 파일·모델 manifest·운영 Compose의 SHA-256,
프롬프트 버전, Alembic head, SBOM 해시가 들어간다. 비밀값·개인정보는 넣지 않는다.

공개 저장소라 Actions 로그·Release·빌드 출처 증명이 모두 공개되고, 증명은 Sigstore 공개 로그에 영구히 남는다.
그래서 AWS 계정 ID가 든 값(역할 ARN·ECR 주소)은 환경 **시크릿**으로 받아 로그에서 가리고, manifest와 증명에는
레지스트리 주소 없이 `reconnect-<이름>@sha256:<digest>`만 기록한다. 레지스트리 주소는 EC2가 자기 계정에서 만든다(6절).

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
음성 이미지는 같은 베이스에 OS 패키지를 추가하지 않아 같은 목록을 적용했다. 음성 빌드 파일(`speech/Dockerfile`·잠금 파일·`tts_compat`)이나
판정 도구·release 워크플로가 바뀐 PR에서는 `이미지 빌드·검사 (speech)`가 빌드·판정까지 확인한다.

## 4. 저장소·AWS 준비 (admin, 1회)

- GitHub **Settings → Environments → `release`**: 필수 승인자(자기 승인 금지), 배포 대상은 `v*` 태그만.
  - 환경 변수(Variables): `AWS_REGION`
  - 환경 시크릿(Secrets): `AWS_ACCOUNT_ID`(12자리, 로그 가리기용), `AWS_RELEASE_ROLE_ARN`, `ECR_REGISTRY`(`<계정>.dkr.ecr.<리전>.amazonaws.com`).
    셋 다 계정 ID가 들어 있어 Variables에 두지 않는다. Variables 값은 공개 로그에 그대로 찍힌다.
- IAM OIDC 역할 신뢰 조건: `token.actions.githubusercontent.com:aud = sts.amazonaws.com`, `sub = <접두어>:environment:release`.
  이 저장소는 변경 불가 주체 형식을 쓰므로 접두어는 `repo:YongSamGo/RE_CONNECT`가 아니라
  `gh api repos/YongSamGo/RE_CONNECT/actions/oidc/customization/sub --jq .sub_claim_prefix`의 값(`repo:<owner>@<id>/<repo>@<id>`)이다.
  옛 형식으로 두면 역할을 맡지 못해 릴리스가 실패한다. 권한은 세 ECR 저장소의 push만.
- ECR 저장소 `reconnect-backend`·`reconnect-frontend`·`reconnect-speech`: 태그 불변(IMMUTABLE), push 시 검사.
- EC2 인스턴스 역할: 세 저장소 pull, `ssm:GetParametersByPath`(`/re-connect/<env>/*`, 기본 `aws/ssm` 키면 KMS 권한 불필요),
  운영 로그 그룹 쓰기. 그 밖의 쓰기·삭제 권한은 주지 않는다.
  삭제 이력 버킷은 해당 접두어의 쓰기·읽기·목록과 보호 설정 조회만 준다(삭제·수명주기·정책 변경 없음, [백업·복원](../../docs/security/backup-restore.md), #94).
- 관리 명령은 backend 이미지의 `manage_*.py`를 모두 담는다: `docker compose --env-file /run/reconnect/images.env -f infra/compose.prod.yaml run --rm --entrypoint /opt/venv/bin/python backend -B manage_<이름>.py ...`

## 5. 비밀값 (SSM Parameter Store)

모든 값은 `SecureString`으로 둔다. 경로마다 받는 이름이 정해져 있고 그 밖의 이름은 거절한다.

| 경로 | 필수 | 선택 |
| --- | --- | --- |
| `/re-connect/<env>/app/` | `DATABASE_URL`(reconnect_runtime), `REDIS_URL`, `REQUEST_LIMIT_KEY`, `PUBLIC_ORIGIN`, `DATA_ENCRYPTION_KEYS`, `DATA_ENCRYPTION_ACTIVE_KEY_ID` | 카카오 3종, `DATA_GO_KR_SERVICE_KEY`, `INFERENCE_CONTROL_EPOCH`, 안내문 버전·본문, `OLLAMA_MODEL`, 삭제 이력 버킷 3종(`DELETION_JOURNAL_BUCKET`·`_BUCKET_OWNER`·`_REGION`, 함께 설정, #94) |
| `/re-connect/<env>/redis/` | `REDIS_PASSWORD`(hex 32자 이상) | — |
| `/re-connect/<env>/migrate/` | `DATABASE_URL`(reconnect_migrator) | — |

- `DATABASE_URL`은 `sslmode=verify-full&sslrootcert=/run/rds-ca.pem`이 없으면 거절한다.
- `REDIS_URL`은 내부 `redis` 서비스만 가리킬 수 있다.
- 삭제 이력 버킷 3종은 backend 설정과 같은 형식만 받고, 일부만 있으면 거절한다. 셋이 없으면 운영 회원 저장은 비활성이다.
- `APP_ENV`·`TRUSTED_PROXY_IPS`는 Compose `environment:`에 고정돼 있다. `OLLAMA_BASE_URL`은 코드 기본값(내부 `ollama` 서비스)을 쓴다. 세 값 모두 렌더러 허용 목록에 없어 SSM으로 바꿀 수 없다.
- 값은 줄바꿈 없이 한 줄로 저장한다(JSON은 압축해서 저장). Compose는 env 파일을 `format: raw`로 읽어 `$`·따옴표를 해석하지 않는다.

## 6. 배포 (운영자, EC2)

root 셸(Session Manager)에서 저장소의 릴리스 태그 체크아웃을 기준으로 실행한다. `/run`은 tmpfs라 재부팅하면 env 파일이 사라진다.
초안 Release를 확인해 공개한 뒤 배포한다. 공개 Release의 manifest는 GitHub 로그인 없이 받는다.

```bash
install -d -m 700 /run/reconnect
curl -fsSL --proto '=https' -o /run/reconnect/release-manifest.json \
  https://github.com/YongSamGo/RE_CONNECT/releases/download/vX.Y.Z/release-manifest.json
# 레지스트리 주소는 manifest에 없다. 인스턴스 역할의 계정으로 만든다
REGISTRY="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com"
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin "$REGISTRY"
python3 -I infra/release/release_manifest.py images-env /run/reconnect/release-manifest.json \
  --registry "$REGISTRY" --output /run/reconnect/images.env
printf 'AWS_REGION=%s\nDEPLOY_ENV=%s\n' ap-northeast-2 production >> /run/reconnect/images.env
```

빌드 출처 증명은 digest로 검증한다(세 이미지 모두). gh는 GitHub 토큰이 있어야 동작하므로, 권한을 하나도 주지 않은
fine-grained 토큰(공개 저장소 읽기만 가능)을 **그 셸에서만** `GH_TOKEN`으로 넣고 끝나면 지운다. 서버 파일·프로필에 저장하지 않는다.
증명의 대상 이름은 레지스트리 없는 `reconnect-<이름>`이다. 첫 릴리스에서 digest만으로 통과하는지 확인하고 결과를 여기에 적는다.

```bash
read -rs GH_TOKEN && export GH_TOKEN
for image in backend frontend speech; do
  ref="$(grep -m1 "^$(echo "$image" | tr a-z A-Z)_IMAGE=" /run/reconnect/images.env | cut -d= -f2)"
  gh attestation verify "oci://$ref" -R YongSamGo/RE_CONNECT
done
unset GH_TOKEN
```

SSM 비밀값으로 env 파일을 만든다.

```bash
for role in app redis migrate; do
  aws ssm get-parameters-by-path --region ap-northeast-2 --path "/re-connect/production/$role/" --with-decryption --output json \
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
되돌리기 전에 `release_manifest.py rollback-check`로 이미지만 되돌려도 되는지 판정한다. 운영 DB는 downgrade하지 않는다.
판정별 절차와 마이그레이션 작성 규칙은 [운영 절차 · 롤백](../../docs/operations/rollback.md)(#97)에 있다.

## 7. 시험

```bash
python -I -m unittest discover -s infra/release/tests
python -I -m unittest discover -s infra/deploy/tests   # POSIX 권한 검사라 Linux에서 실행
```

## 모델 서비스 연결 (#92)

GPU Ollama·GPU STT/TTS는 [모델 실행 절차](../models/README.md)의 운영 overlay를 추가한다.
기존 images.env의 CPU SPEECH_IMAGE와 구분하여, 별도 빌드/스캔한 SPEECH_GPU_IMAGE와 실측 자원 상한을 지정한다. Ollama 공식 digest는 overlay 기본값에 고정돼 있다.
Ollama 외부 이미지는 현재 Release 자동 빌드/검사 대상이 아니므로 별도 공급망 검증 기록이 필요하다.
모델 준비·host/config 검사·warmup 후 공개 진입점을 시작하며, 실제 EC2 검증 전 이슈를 종료하지 않는다.
