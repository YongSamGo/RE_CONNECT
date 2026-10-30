# frontend — React 클라이언트

## 프론트 완성 계획

앞으로의 화면 구현과 최종 검수는 [프론트 완성 계획](../Plan/08_Frontend_Completion_Plan.md)을 기준으로 한다. 사용자가 정한 간결한 화면 원칙, 기존 화면 보존 기준, 실제 기능 연결 순서와 완료 조건을 함께 기록했다. 과거 진행 문서와 현재 연결 상태가 다르면 실제 라우트와 제품 코드로 확인한다.

작업 전 [프론트 지침](AGENTS.md), [스타일 보존 기준](DESIGN_BASELINE.md), [실행 준비서](../Plan/09_Frontend_Execution_Runbook.md)를 읽는다. 문구 정적 검사는 `npm run ui:copy`로 실행한다. 실제 화면 비교와 기능 검수는 별도로 수행한다.

## 현재 시작 흐름 (2026-10-26)

첫 화면과 공개 공고 상세에서 `/start`로 이동한다. 서버가 게시한 AI 처리 안내문을
조회하고 사용자가 명시적으로 동의하면 실제 체험을 생성해 기존 대화·프로필·추천·신청
준비 화면으로 연결한다. 게시 안내문이 없으면 체험 생성은 제공하지 않는다. 로그인과
회원 저장은 별도의 게시 안내와 사용자 선택을 따른다. `/consent` 등 기존 미리보기는
가상 자료용으로 분리하며, 개발 화면 목록은 개발 빌드에만 표시한다.

요청 결과가 유실되면 같은 생성 키·본문으로 재확인한다. 세션 변경이나 화면 이탈 뒤의
늦은 결과는 적용하지 않는다. 실제 처리 동의·회원 저장·신청 완료를 미리보기 상태나
네트워크 요청 시작만으로 표시하지 않는다. 운영자 화면은 필요할 때 별도 번들을 읽으며,
서버가 확인한 운영자에게만 내 정보의 진입 링크를 보여준다. 인가는 서버에서 다시 검사한다.

아래 진행·인계 기록의 과거 미연결 설명은 당시 이력이다. 현재 구현 판단에는 코드와
해당 변경의 검사 결과를 사용한다. 운영 주체·문의처·리전·정책 확정, 실제 카카오·음성·
기기 검증은 코드 연결과 별도로 필요하다.

담당: A · 기획·프론트엔드

React·TypeScript·Vite로 만든다. 운영에서는 빌드한 정적 파일을 Nginx 컨테이너가 제공하고, Vite 개발 서버는 로컬 개발에서만 쓴다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)). 실행·검사 방법은 [개발 안내](DEVELOPMENT.md), 구현 범위와 연동 대기 사항은 [진행 기록](PROGRESS.md)을 따른다.

사용자용 화면과 호환 주소의 이동 경로는 [서비스 화면 안내](SERVICE_SCREENS.md)를 따른다. 개발 서버의 `/guide`에서 실제 이용 화면을 열어 확인할 수 있다. 대화·내 경험 확인의 전면 개편 첫 구현과 미검증 범위는 [개편 진행 기록](REDESIGN_PROGRESS.md)에 정리했다.

로컬 별도 구현과의 통합 기준·제외 범위·이전 주소 전환·검증 결과는 [중복 정리 기록](CONSOLIDATION.md)을 참고한다.

다음 작업의 맥락은 [짧은 인계 요약](HANDOFF.md), 이슈별 현재 증거·남은 조건·검증 게이트·시간 기록은 [이슈 진행표](ISSUE_STATUS.md)에서 확인한다. GitHub 상태는 작업 착수 때 다시 조회한다.

공통 UI의 자동 접근성 회귀 검사와 실제 기기 검증의 구분은 [접근성 검증 기록](ACCESSIBILITY.md)을 따른다.

실제 지역 라우터의 응답을 OpenAPI와 프론트 파서에 대조하는 `npm run test:backend-contract`는 [계약 대조 안내](contract-tests/README.md)를 따른다. Python 3.12·backend 의존성이 필요하며 기존 CI에서도 실행한다.

로컬 Vite는 `127.0.0.1`에서만 열고 `/api/v1`을 `http://127.0.0.1:8000`의 backend로 전달한다. 화면 경로는 SPA로 유지한다. backend를 실행하지 않으면 API 연결 오류가 나며 예시 성공 응답으로 대체하지 않는다. 운영 proxy·HTTPS·인증 검증은 별도다.

공고별 공식 준비 안내와 임시 서류 체크의 부분 구현 범위·실제 API 연동 대기는 [준비 안내 구현 기록](src/features/preparation/OFFICIAL.md)을 따른다.

서버 체험 ID의 프로필 편집·확정·역할 제외/복원 화면과 시작 진입점·실제 기기 검증의 남은 범위는 [프로필 서버 연결 기록](src/features/profile/SERVER.md)을 따른다.

로그인 복귀·현재 회원 상태 확인과 운영 안내 미정에 따른 저장 동의 연결 대기는 [로그인·내 정보 연결 기록](src/features/account/SERVER.md)을 따른다.

서버 메시지 API에 연결한 한 질문 대화 화면과 입력 유지·멱등 재확인·프로필 이동 경계는 [대화 서버 연결 기록](src/features/conversation/SERVER.md)을 따른다. 실제 동의·체험 시작은 운영 안내 확정 전까지 연결하지 않는다.

확정 프로필 추천·범위 필터·공고별 자격 대조와 실제 표본 평가/기기 검증의 남은 범위는 [추천 서버 연결 기록](src/features/recommendations/SERVER.md)을 따른다.

체험 공고의 생성/직접 작성·편집/서버 승인·현재 승인본 복사와 남은 범위는 [신청 준비 연결 기록](src/features/preparation/JOURNEY.md)을 따른다.

실제 대화 화면의 녹음/전사 수정 패널과 오디오 정리·수정 텍스트 전달 경계는 [음성 연결 기록](src/features/voice/TRANSCRIPTION.md)을 따른다.

## 버전과 패키지 매니저

- Node는 루트 [.nvmrc](../.nvmrc)의 버전(24)을 쓴다. CI도 같은 버전이다.
- `npm run typecheck`는 `typescript-compiler` 별칭으로 설치한 TypeScript 7.0.2 컴파일러를 사용한다. `npm run build`도 이 명령을 실행한다. API 타입 생성기는 `openapi-typescript` 7.13.0의 peer 요구와 `ts.factory` API에 맞춰 `typescript` 5.9.3을 별도로 사용한다. 두 패키지가 제공하는 `tsc` 실행 파일 이름이 같으므로 컴파일러 경로를 명시한다. API 생성기가 새 컴파일러 API를 지원하면 이 분리를 재검토한다.
- 패키지 매니저는 npm이다. `package-lock.json`을 커밋하고, 설치는 `npm ci --ignore-scripts`로 한다. CI도 같은 명령으로 설치 스크립트 실행을 막는다.
- `package.json`에 `lint`·`build` 스크립트를 둔다. CI가 `npm run lint`, `npm test --if-present`, `npm run build`를 실행한다.
- `.oxlintrc.json`의 `react/exhaustive-deps`와 `promise/catch-or-return`을 오류로 검사한다. 효과의 누락된 의존성과 실패 처리 없는 `.then()` 체인을 확인한다. 경고를 없애려고 의존성을 일괄 추가하지 말고 화면 수명·요청 중복 여부를 먼저 확인한다. 이 규칙이 모든 비동기 실패를 검증하는 것은 아니다.

`package-lock.json`이 생기면 CI의 프론트엔드 점검이 자동으로 켜진다. 같은 PR에서 [dependabot.yml](../.github/dependabot.yml)의 `npm` 항목 주석을 해제한다.

## 설정

Vite는 `VITE_`로 시작하는 환경변수를 브라우저 번들에 그대로 넣는다. 비밀값·API 키는 `VITE_` 변수에 두지 않는다. 화면이 필요한 값은 모두 백엔드 `/api`를 거친다.
