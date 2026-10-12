# CI 보안 파이프라인

모든 PR과 `main` push에 보안 점검을 자동으로 겁니다. README 5.2절 흐름의 **⑤ 자동 점검**을 맡는 부분입니다.

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `.github/workflows/ci.yml` | 테스트·보안약점·의존성·비밀값·워크플로 점검, 최종 판정 `CI 통과` |
| `.github/workflows/codeql.yml` | CodeQL 정적 분석 (결과는 Security 탭 → Code scanning) |
| `.github/dependabot.yml` | 의존성 업데이트 PR 자동 생성 |
| `.gitleaks.toml` | 비밀값 탐지 규칙 (KISA 원문·[점검 키트](kisa-review.md) 참조 문서의 예제 코드만 예외) |

## 점검 항목

| 잡 | 도구 | 무엇을 막나 | 관련 KISA 보안약점 | 실행 조건 |
| --- | --- | --- | --- | --- |
| 비밀값 유출 점검 | gitleaks | API 키·비밀번호·개인키 커밋 (지워진 커밋 포함) | 하드코드된 중요정보 | 항상 |
| 워크플로 보안 점검 | zizmor | CI 자체의 권한 과다, 스크립트 삽입, 고정 안 된 액션 | — (공급망 보안) | 항상 |
| Python 점검 | pytest | 기능 오류, 약점별 공격 시나리오 | 약점별 테스트 전체 | `backend/` 또는 `worker/`에 `requirements.txt`가 있을 때 |
| | bandit | SQL 삽입, 명령어 삽입, 취약한 해시·난수, 하드코드 비밀값 등 | SQL 삽입, 운영체제 명령어 삽입, 취약한 암호화 알고리즘 사용 등 | 〃 |
| | pip-audit | 알려진 취약점(CVE)이 있는 라이브러리 | 취약한 API 사용 | 〃 |
| 프론트엔드 점검 | npm audit signatures | 서명·출처가 검증되지 않은 패키지 | — (공급망 보안) | `frontend/package-lock.json`이 있을 때 |
| | npm audit | 운영 의존성의 높음 이상 취약점 | 취약한 API 사용 | 〃 |
| | lint / test / build | 코드 품질, 타입 오류 | — | 〃 |
| 새 의존성 검토 | dependency-review | PR에서 새로 들어오는 취약 패키지 (중간 이상) | 취약한 API 사용 | PR이고 의존성 파일이 있을 때 (Dependency graph 필요) |
| CodeQL | CodeQL `security-extended` | 데이터 흐름 기반 XSS·SSRF·경로 조작·SQL 삽입 등 | 입력데이터 검증 및 표현 전반 | 항상 (언어 자동 감지) |

`backend/`, `frontend/`가 아직 없어서 지금은 해당 점검이 **Skipped**로 표시됩니다. 폴더가 생기면 별도 수정 없이 자동으로 켜집니다.

## CI 자체에 적용한 보안 원칙

- **액션을 커밋 SHA로 고정** — 태그(`@v7`)는 바뀔 수 있어서, 액션 저장소가 탈취되면 악성 코드가 그대로 실행됩니다. SHA 옆 주석이 버전이며, Dependabot이 둘을 함께 갱신합니다.
- **최소 권한 토큰** — 워크플로 기본 권한은 없음(`{}`)이고, 잡마다 필요한 권한만 줍니다. 쓰기 권한은 CodeQL 결과 업로드(`security-events: write`) 하나뿐입니다.
- **토큰을 디스크에 남기지 않음** — 모든 checkout에 `persist-credentials: false`.
- **스크립트 삽입 방지** — `${{ }}` 값을 `run` 스크립트에 직접 넣지 않고 `env`로 넘깁니다.
- **도구 무결성 검증** — gitleaks는 공식 릴리스를 받아 SHA-256 체크섬이 맞을 때만 실행합니다. 점검 도구 버전은 `ci.yml` 상단 `env`에 고정합니다.
- **npm 설치 스크립트 차단** — `npm ci --ignore-scripts`로 악성 `postinstall`이 CI에서 실행되지 않게 합니다.
- **캐시 미사용** — 의존성 캐시 오염 공격을 피하려고 캐시를 쓰지 않습니다. 대신 실행이 조금 느립니다.
- **로그 비밀값 가림** — 공개 레포라 gitleaks는 `--redact`로 발견한 값을 로그에 찍지 않습니다.
- **새 버전 7일 대기** — Dependabot `cooldown`으로 배포 직후 악성 버전이 섞이는 공급망 공격에 대비합니다.
- **정기 재검사** — 코드가 그대로여도 새 CVE가 공개되므로 매주 월요일 오전에 다시 돕니다.

## 저장소 소유자 설정 (admin 권한 필요)

이 PR이 병합되고 CI가 **한 번 실행된 뒤** 소유자가 설정합니다. 체크 이름은 한 번 실행돼야 목록에 나타납니다.

1. **Settings → Branches → `main` 보호 규칙**
   - Require a pull request before merging (승인 1명 이상)
   - Require status checks to pass → **`CI 통과`** 하나만 지정
   - Do not allow bypassing the above settings
2. **Settings → Code security** (공개 레포는 무료)
   - **Dependency graph** — 꺼져 있으면 `새 의존성 검토`가 "Dependency review is not supported" 오류로 실패
   - Secret scanning + **Push protection** — 비밀값이 든 push 자체를 GitHub가 거부
   - Dependabot alerts
   - Code scanning → Rulesets에서 CodeQL 결과 기준 병합 차단 (선택)
3. **Settings → Actions → General**
   - Workflow permissions: **Read repository contents** (기본 읽기 전용)
   - Fork PR 실행 전 승인 필요

## 실패했을 때

| 실패한 잡 | 할 일 |
| --- | --- |
| 비밀값 유출 점검 | **키를 즉시 폐기·재발급**하고 팀에 알립니다. 커밋을 지워도 이력에 남습니다. 오탐이면 `.gitleaks.toml` 예외를 PR로 제안합니다. |
| bandit | 코드를 고치는 것이 원칙입니다. 오탐이면 해당 줄에 `# nosec B000 - 사유`를 적고 PR에서 리뷰어 승인을 받습니다. |
| pip-audit / npm audit | 패치된 버전으로 올립니다. 패치가 없으면 이슈로 남기고 팀이 판단합니다. |
| zizmor | 워크플로 수정 시 권한·삽입 경고를 고칩니다. |

## 로컬에서 먼저 돌려보기

push 전에 같은 점검을 돌리면 CI 실패를 줄일 수 있습니다.

```bash
# backend/ 안에서
python -m pytest
bandit -r . --exclude ./tests,./.venv --severity-level low --confidence-level medium
pip-audit -r requirements.txt --strict
```

## backend/ 를 만들 때 필요한 것

- `backend/requirements.txt` — 운영 의존성 (버전 고정 권장)
- `backend/requirements-dev.txt` — `pytest` 등 개발 도구
- `backend/tests/` — 테스트가 하나도 없으면 pytest가 실패합니다
- `.github/dependabot.yml`의 pip 항목 주석 해제
