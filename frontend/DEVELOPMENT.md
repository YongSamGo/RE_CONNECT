# 프론트엔드 초기 화면 — W02-02 / #13

담당 A. 기준은 `Plan/01_UX_Flow.md`와 `Plan/03_Architecture_and_Dependencies.md` v1.1이다. 이 PR은 React·TypeScript·Vite 실행 기반, UX01~10 경로, 오류 경계를 제공한다. W02-08 API 타입·클라이언트, W11의 실제 기능 구현은 후속 작업이다.

## 실행

Node 24와 npm을 사용한다. 저장소 루트에서 `cd frontend` 후:

```powershell
npm ci --ignore-scripts
npm run dev
```

`http://127.0.0.1:5173`에서 확인한다. 로컬 루프백으로만 연다. `npm run build`는 엄격한 타입 검사와 `dist/` 정적 빌드를 수행한다. 운영에서는 Nginx의 SPA fallback이 필요하며 Vite 개발 서버를 배포하지 않는다. `/api/*`는 화면 fallback으로 처리하지 않고 FastAPI로 전달해야 한다.

```powershell
npm run lint
npm test
npm run build
npm audit signatures
npm audit --omit=dev --audit-level=high
```

기존 CI는 lockfile을 감지해 위 검사를 자동 실행한다. 설치 스크립트 없이 빌드·테스트가 가능하다. 직접 의존성은 정확한 버전, 전이 의존성은 `package-lock.json`으로 고정했다. `VITE_` 값은 브라우저에 공개되므로 키·토큰을 넣지 않는다.

## 화면 검토

시작 → 안내 확인 → 가상의 경험 입력 → 작성 내용 확인·수정 → 종료하고 삭제를 살펴본다. 하단의 **개발 화면 목록**에서 UX01~10 경로를 연다. 사적 체험 경로는 안내 확인부터 시작한다. 없는 주소에는 복귀 경로가 있다.

| UX | 경로 | 현재 제공 |
|---|---|---|
| 01 | `/` | 소개·비회원 진입·공개 화면 이동 |
| 02 | `/consent` | 안내문 초안·미리보기 확인 선택 |
| 03 | `/conversation` | 가상 경험 입력·글자 수·내용 확인 이동 |
| 04 | `/transcription` | 음성 연동 대기·텍스트 복귀 |
| 05 | `/profile` | 직접 작성한 텍스트 확인·수정 복귀 |
| 06 | `/opportunities` | 공개 공고 연동 대기 |
| 07 | `/opportunities/:id` | 공고 상세 연동 대기 |
| 08 | `/preparation` | 신청 준비 연동 대기 |
| 09 | `/me` | 로그인·저장 연동 대기 |
| 10 | `/admin/*` | 서버 역할·MFA 연동 대기 |

API·AI·음성·인증·공고를 호출하거나 가상의 성공 응답을 생성하지 않는다. 안내 선택은 운영 동의가 아니며 직접 쓴 경험은 확정 프로필이 아니다. 회원 저장·추천을 완료한 것으로 표시하지 않는다. 실제 운영 주체·문의처·리전은 W01-06에서 확정한다.

입력은 React 메모리에만 있고 URL·localStorage·sessionStorage·IndexedDB·Service Worker에 쓰지 않는다. 종료·새로고침·전체 페이지 이탈에서 비운다. 브라우저 이탈 처리는 보조 수단이며 서버 세션 만료·삭제의 대체가 아니다. 메모리 참조 제거는 메모리의 물리적 완전 소거를 의미하지 않는다.

18px 기본 본문, 44px 이상 주요 조작, 폼 레이블, 포커스 표시, 본문 바로가기, 경로 이동 시 본문 포커스·제목 갱신을 제공한다. 반응형 CSS는 작성했으나 실제 Android Chrome·iPhone Safari·PC Chrome의 200% 확대·스크린리더 검증은 W13-06에서 별도로 수행한다.

## 단일 PR 범위와 인계

- 작업 단위: #13 W02-02. 선행 #12 / PR #115가 병합되기 전에는 초안·검토 대기다. 다른 작업 카드를 완료로 바꾸지 않는다.
- `frontend/README.md`는 #115 소유 파일이므로 이 PR에서 만들거나 덮어쓰지 않는다. 현재 파일은 초기 구현의 실행·검증 안내다.
- W02-08은 #116·#117의 API 계약 확정과 공통 타입을 받은 뒤 진행한다. 화면 경로는 프론트엔드 라우트이며 API 경로를 새로 정의한 것이 아니다.
- 개발 화면 목록과 미연동 표시는 공개 릴리스 전에 실제 기능·인증·정책과 함께 재검토한다. 현재 빌드는 개발 검토용이다.

## 보안 근거와 검증 범위

다음은 `AGENTS.md → SW개발보안_obsidian/Security/INDEX.md`를 통해 확인한 원문이다. Python 구현 예제를 React에 복사하지 않고 원칙을 프레임워크에 맞게 적용했다.

| 참고 문서의 프로젝트 상대경로 | 장·절·PDF 페이지 | 적용·검증 |
|---|---|---|
| `SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제1절-입력데이터-검증-및-표현/009-4.-크로스사이트-스크립트(XSS).md` | 제2장 제1절 4, PDF 28~34쪽(안전한 코딩기법 30쪽) | React 텍스트 출력, 공격 문자열이 img/script 요소를 만들지 않는 시험 |
| `SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제4절-에러처리/043-1.-오류-메시지-정보노출.md` | 제2장 제4절 1, PDF 131~134쪽 | 오류 경계의 고정 메시지, 내부 오류 문자열 비노출 시험 |
| `SW개발보안_obsidian/Security/SW-Diagnosis-2021/제2장-소프트웨어-개발보안/제3절-설계단계-보안설계-기준/041-4.1-세션-통제.md` | 제2장 제3절 4.1, PDF 171~179쪽 | 종료 UI·임시 상태 분리 설계 참고. 서버 세션 통제 구현 완료 주장은 아님 |

메모리 전용 보관·미리보기 동의 구분은 프로젝트 01 §4·02 §5·05 §2의 설계다. 공식 가이드가 이 UI나 구체적 보관 정책을 직접 요구한다고 해석하지 않는다.

로컬 검증: `npm ci --ignore-scripts`, lint, Vitest 16건, 엄격한 타입 검사·빌드 통과. 의존성 감사는 전체 의존성에서 취약점 0건이며 레지스트리 서명 검증을 통과했다. 현재 Vitest는 DOM 환경에서 입력·수정·종료·재마운트·pagehide/pageshow·키보드·오류·XSS 경계를 검증한다. 인앱 Chromium에서 안내 → 입력 → 내용 확인 → 종료·삭제도 수동 확인했다. 실제 브라우저 bfcache·모바일 음성·서버 삭제·권한 통제는 별도 통합 검증 대상이다. 원격 CI는 PR의 결과를 따르며 로컬 검증으로 대체하지 않는다.

기술 구현 시 확인한 공식 문서: [Vite 시작](https://vite.dev/guide/), [React 오류 경계](https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary), [React Router](https://reactrouter.com/start/declarative/installation).
