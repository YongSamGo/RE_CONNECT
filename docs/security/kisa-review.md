# KISA 보안 점검 키트 (Claude Code)

KISA 시큐어코딩 기준과 SW 공급망 보안 기준으로 저장소를 정적 점검하는 Claude Code 스킬과 슬래시 명령입니다. README 5.2절 흐름의 **② 설계 · ⑥ 리뷰** 단계에서 씁니다. 매 PR에 자동으로 도는 점검은 [CI 보안 파이프라인](ci-pipeline.md)이 맡고, 이 키트는 사람이 코드 흐름을 따라가며 판정해야 하는 항목(인증·인가·IDOR·경쟁조건 등)을 맡습니다.

## 설치

저장소에 포함되어 있어 따로 설치할 것이 없습니다. 저장소를 받은 뒤 최상위 폴더에서 Claude Code를 열면 바로 쓸 수 있습니다.

```
RE_CONNECT/
└── .claude/
    ├── commands/kisa-review.md              ← /kisa-review 명령 (실행 지시서 + 다시잇다 맥락)
    └── skills/kisa-secure-coding-python/    ← 스킬 (판정 기준)
```

## 사용

Claude Code에서:

```
/kisa-review                      # 저장소 전체: 코드 + 공급망 + 설계 기준
/kisa-review backend/             # 특정 경로만
/kisa-review --code-only          # 코드(구현 49개)만
/kisa-review --supply-chain       # 의존성·CI·Dockerfile·SBOM만
/kisa-review --roadmap            # 로드맵(2026) 대비 현황까지 포함
/kisa-review PR 111               # PR 변경분만 점검 (결과는 보고서로만)
/kisa-review PR 111 --comment     # PR 변경분 점검 + 승인 후 PR 리뷰 댓글
```

- `--comment`는 PR 대상일 때만 동작합니다. **PR이 추가·변경한 코드에서 생긴 발견만** 인라인 댓글로 올리고, PR이 건드리지 않은 기존 코드의 발견은 요약에 건수만 적습니다. 댓글은 올리기 전에 대화창에서 확인을 받습니다.
- 댓글에는 P1~P4 배지와 Claude 리뷰 표시가 붙고, 리뷰 상태는 항상 `Comment`입니다(승인·변경 요청은 사람이 합니다). 등급 기준은 [명령 파일](../../.claude/commands/kisa-review.md) 4절에 있습니다.

- 명령 이름이 `/security-review`가 아닌 이유: Claude Code에 같은 이름의 기본 명령(현재 브랜치 변경분 보안 리뷰)이 있어서 겹치지 않게 바꿨습니다.
- 명령 없이 "KISA 기준으로 보안 점검해줘"라고 해도 스킬이 사용됩니다.

## 결과 보관

| 위치 | 내용 | 커밋 |
| --- | --- | --- |
| `security-reports/kisa-review-YYYY-MM-DD.md` | 점검 보고서 원본 | ❌ `.gitignore` 처리 |
| `security-reports/*.json` | bandit·pip-audit·SBOM 등 도구 출력 | ❌ `.gitignore` 처리 |
| `security-reports/kisa-review-pr-<번호>-comments.json` | `--comment`로 올린 PR 리뷰 원본 | ❌ `.gitignore` 처리 |
| PR 리뷰 댓글 | `--comment`일 때, PR이 추가·변경한 코드의 발견만 | 공개 (GitHub PR) |
| `docs/security/` | 조치가 끝난 항목의 요약 진단 기록 | ✅ |

공개 저장소라 미조치 취약점의 위치·재현 방법이 담긴 보고서 원본은 커밋하지 않습니다. 발견 사항은 **비공개로 공유**하고(팀 채널 등), 조치 후 "무엇을 · 어떤 테스트로 막았는지"만 `docs/security/`에 남깁니다.

예외는 PR 변경분의 발견입니다. 그 코드는 이미 PR에 공개되어 있고 아직 머지 전이라, 머지 전에 PR 댓글로 지적하는 것은 일반 코드 리뷰와 같습니다. 이미 머지된 기존 코드의 발견은 PR 댓글에도 위치·항목을 적지 않습니다.

## 다시잇다에 맞춘 부분

`/kisa-review` 명령의 `0-1. 다시잇다 프로젝트 맥락` 절에 있습니다.

- **비신뢰 데이터 범위 확대**: 사용자 입력뿐 아니라 외부 공고 원문과 LLM 출력도 외부 입력(Source)으로 추적합니다 (README 5.1 원칙 3).
- **FastAPI 기준 인증·인가 점검**: 라우트마다 `Depends()` 체인과 프로필·지원서의 소유자 확인을 표로 확인합니다.
- **개인정보 로그·LLM 마스킹** 확인 (SEC-05, ERR-01).
- **KISA 밖 위험** 섹션: 프롬프트 인젝션, LLM 비용 상한, 동의·삭제 정책, React/TS 프런트엔드는 키트 49개 항목에 없어서 보고서에 따로 `확인 필요`로 적습니다 (README 5.3).
- **CI 연계**: 공급망 항목(SCP-06·10·11·17)은 `.github/` 설정을 근거로 판정합니다.

## 구성

| 경로 (`.claude/skills/kisa-secure-coding-python/` 기준) | 역할 |
| --- | --- |
| `SKILL.md` | 스킬 본체: 검사 절차, 판정 원칙, 전체 항목 인덱스, 빠른 탐지 패턴 |
| `references/kisa2021-diagnosis-reference.md` | 진단가이드(2021) 항목별 판정 기준 (언어 공통, Java·C 예제 중심) |
| `references/design-SR.md` | 설계단계 보안설계 기준 20개 (Python 적용) |
| `references/impl-1~3*.md` | 구현단계 49개: KISA 2021 + Python 가이드(2023) 원문 + Python 판정 기준 |
| `references/supply-chain-guideline.md` | SW 공급망 보안 가이드라인 1.0: SC-01~30, SCP-01~20 |
| `references/supply-chain-roadmap.md` | SW 공급망 보안 강화 로드맵(2026.6): RM-01~12 |
| `scripts/sbom_check.py` | SBOM 필드(NTIA·NIS-SBOM) 점검 |
| `scripts/typo_check.py` | 타이포스쿼팅 의심 패키지 탐지 (다시잇다 스택 패키지 포함) |

## 직접 돌려볼 때 필요한 것

Claude Code로 점검할 때는 따로 설치할 것이 없습니다. `SKILL.md`의 탐지 패턴을 사람이 터미널에서 직접 돌리려면:

- **ripgrep** (`rg`): Windows `winget install BurntSushi.ripgrep.MSVC`, macOS `brew install ripgrep`. Windows는 Git Bash에서 실행합니다.
- **Python 도구**: `bandit`, `pip-audit` (CI와 같은 버전은 `.github/workflows/ci.yml` 상단 `env` 참고)
- Windows에서 `python3`가 없으면 `python` 또는 `py -3`을 씁니다.

## 기준 문서

- KISA·행정안전부 「소프트웨어 개발보안 가이드」(2021.12), 「소프트웨어 보안약점 진단가이드」(2021.11)
- KISA 「Python 시큐어코딩 가이드」(2023)
- 국가정보원·과기정통부·디지털플랫폼정부위원회 「SW 공급망 보안 가이드라인 1.0」(2024.05)
- 관계부처 합동 「SW 공급망 보안 강화 로드맵」(2026.06)

## 키트 원본 대비 변경 사항

| 변경 | 이유 |
| --- | --- |
| 명령 `security-review` → `kisa-review` | Claude Code 기본 명령과 이름 충돌 |
| SKILL.md CSRF 토큰 누락 탐지 `rg -L` → `rg --files-without-match`, `-i` 추가 | `-L`은 심볼릭 링크 따라가기 옵션이라 탐지가 동작하지 않았음. `method="POST"` 대문자도 잡도록 |
| 보고서·도구 출력 → `security-reports/` + `.gitignore` | 공개 저장소에 미조치 취약점 노출 방지 (RM-05) |
| 도구 명령의 스크립트 경로를 저장소 최상위 기준으로 | 원본은 스킬 폴더 기준 상대경로라 최상위에서 실행하면 실패 |
| `design-SR.md`의 `implementation-*.md` → `impl-*.md` | 예전 파일명 |
| `typo_check.py`에 다시잇다 스택 패키지 추가, `with open`, 사용법 안내 | `psycopg`를 `psycopg2` 오타로 오탐, 자원 해제(COD-02) |
| `sbom_check.py` 인자 검사, `with open` | 인자 없이 실행 시 `IndexError` |
| 가이드라인 문서의 스크립트 사본 제거 → 스크립트 파일 안내 | 사본과 원본이 어긋나는 것을 방지 |
| SKILL.md ENC-01 CWE `488` → `488, 543` | 명령·진단 레퍼런스와 불일치 |
| `rg`·Windows 실행 안내 추가 | `rg`가 없는 환경에서 패턴 실행 실패 |
| 명령에 `0-1. 다시잇다 프로젝트 맥락`, 보고서에 `KISA 밖 위험` 섹션 추가 | 프로젝트 스택·README 보안 원칙 반영 |
| 명령에 PR 대상 점검과 `--comment`(4절) 추가 | PR 변경분 발견을 머지 전에 리뷰 댓글로 전달. 기존 코드 발견은 비공개 유지 |
