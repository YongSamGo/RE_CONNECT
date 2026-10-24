# 프론트 중복 정리 · 2026-10-16

## 단일 기준과 보존

- 통합 브랜치: `chore/frontend-deduplicate`.
- 기준: `origin/feat/role-a-frontend-foundation`의 `891c8e2`([PR #118](https://github.com/YongSamGo/RE_CONNECT/pull/118)). 최신 develop(`10d196f`) 변경도 이 기준 브랜치에 포함되어 있다. PR #118의 원격 상태나 승인·병합 여부는 변경하지 않았다.
- 중복 로컬 구현: `codex/frontend-foundation`의 `c733f0e`, `d29b4f0`. 두 커밋은 기존 브랜치에 남아 있으며 통합 브랜치의 병합 이력에서도 도달 가능하다. 이 병합은 의도적으로 기존 프론트의 파일 트리를 선택한 `ours` 전략이다. 로컬 구현이 원격 기능을 덮어쓰거나 모두 이식된 것으로 해석하면 안 된다.
- 별도 작업트리에서 정리해 원래 작업 폴더의 미추적 AGENTS.md·Vault·PDF·출력물을 변경하지 않았다. 기존 브랜치를 원격에 푸시하거나 PR을 추가로 열지 않았다.

## 중복 처리 결과

| 로컬 중복 | 통합 후 기준 | 처리 |
|---|---|---|
| App·엔트리·패키지·ESLint·Vite·TS 설정 | 기존 App·Oxlint·Vite·타입 생성 빌드 | 기존 도구 체계 한 벌만 사용 |
| `journey.ts`, 자체 Profile·임시 확정 버전 | `features/profile`, OpenAPI 생성 타입 | 자체 확정을 서버 확정처럼 사용하는 모델 제거 |
| 가상 예시 공고 3개·필터·상세 | `features/public-opportunities` | 실행용 가상 공고 제거, API 조회·검증·오류 처리 유지 |
| `ApplicationEditor`, `application.ts` | `features/preparation/ManualPreparation` | 직접 작성·수정 후 재확인·복사·실패 대체·메모리 수명을 기존 기능으로 통합 |
| `MyPage` 체험 요약·로컬 삭제 | `features/account` | 회원 자료 API와 같은 화면으로 혼동하지 않도록 로컬 요약 구현 제외 |
| 별도 메모리·초기화 코드 | `state/useMemoryScope`, `useRequest` | 페이지 이탈·bfcache·종료 이후 늦은 응답 폐기를 포함한 기존 경계 사용 |
| 두 번째 CSS·테스트 체계 | 기존 App.css·index.css·feature CSS·Vitest | 중복 전역 스타일·테스트 설정 제거 |
| `/my`, `/transcript` | `/me`, `/transcription` | replace 리다이렉트. 음성 경로는 기존 안내 확인 가드 유지 |
| `/preparation/:id`, `/recommendations` | 전환·미연동 안내 | 가상 ID를 실제 공고나 추천 결과로 사용하지 않으며 명시적으로 기존 화면으로 안내 |

제거한 로컬 파일은 통합 작업트리의 소스·의존성 그래프에 남기지 않았다. 이전 코드가 필요하면 두 원본 커밋에서 확인한다.

## 이식하지 않은 차이와 후속 연결

- 별도 시작 화면 디자인·큰 글씨 버튼: 기존 반응형·접근성 기준에 맞춘 선택적 디자인 변경으로 남긴다(#80). 이번 정리에서 두 CSS 체계를 섞지 않는다.
- 공고별 준비 체크·지원서: 실제 공고·서버 초안 및 승인 계약을 연결할 때 구현한다(#71·#86). 가상 기관·공고를 실행 데이터로 다시 넣지 않는다.
- 프로필 버전별 지원서 재검토: 서버 확정 버전·근거 변경 계약에 연결한다(#84·#86). 기존 구현은 경험·희망 조건 변경 시 직접 작성 문장의 확인 표시를 해제한다.
- 현재 체험 자료 요약: 회원 저장 자료와 구분하는 UX를 #87에서 검토한다. 회원 저장 조회·삭제 API 화면은 기존 것을 유지한다.

실제 서버·운영 동의문·모델·기기 검증이 미완료인 이슈는 닫지 않는다. 이슈 진행은 [PROGRESS.md](PROGRESS.md), API 기준은 [src/api/README.md](src/api/README.md)를 따른다. 이번 변경은 중복 정리이며 새로운 여정·로그인·저장 기능 구현이 아니다.

## 보안 참조와 검증 범위

이번 작업에서는 기존 구현을 단일화하고 정적 경로 호환만 추가했다. 이미 확인한 `SW개발보안_obsidian/Security/INDEX.md`를 통한 진단가이드 원문을 적용한다: `SW개발보안_obsidian/Security/SW-Diagnosis-2021/제4장-구현단계-보안약점-진단/제1절-입력데이터-검증-및-표현/047-4.-크로스사이트-스크립트.md`, 제4장 제1절 4, PDF 211~213쪽 참조. 새 경로 안내는 고정 JSX 문자열이며 URL의 가상 ID를 HTML·API 입력으로 전달하지 않는다. Python 원문의 구현 예제를 복사하지 않았다. 메모리 수명·동의 구분은 프로젝트 정책이며 가이드의 특정 UI 규칙으로 설명하지 않는다.

통합 작업트리에서 `npm ci --ignore-scripts` 후 `npm run lint`, `npm test`(26개 파일·319개 시험), `npm run build`(OpenAPI 생성 타입 비교·엄격한 TS 검사 포함)를 통과했다. 설치 시 npm audit은 취약점 0건이었다. 기존 315개 시험과 경로 전환 4건을 함께 실행했다. 기존 두 로컬 커밋 및 origin/develop이 통합 HEAD의 조상임을 확인했다. 실제 API·기기·배포 검증을 대신하지 않는다.
