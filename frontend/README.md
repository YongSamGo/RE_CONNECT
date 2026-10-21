# frontend — React 클라이언트

담당: A · 기획·프론트엔드

React·TypeScript·Vite로 만든다. 운영에서는 빌드한 정적 파일을 Nginx 컨테이너가 제공하고, Vite 개발 서버는 로컬 개발에서만 쓴다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)). 실행·검사 방법은 [개발 안내](DEVELOPMENT.md), 구현 범위와 연동 대기 사항은 [진행 기록](PROGRESS.md)을 따른다.

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

## 버전과 패키지 매니저

- Node는 루트 [.nvmrc](../.nvmrc)의 버전(24)을 쓴다. CI도 같은 버전이다.
- 패키지 매니저는 npm이다. `package-lock.json`을 커밋하고, 설치는 `npm ci --ignore-scripts`로 한다. CI도 같은 명령으로 설치 스크립트 실행을 막는다.
- `package.json`에 `lint`·`build` 스크립트를 둔다. CI가 `npm run lint`, `npm test --if-present`, `npm run build`를 실행한다.

`package-lock.json`이 생기면 CI의 프론트엔드 점검이 자동으로 켜진다. 같은 PR에서 [dependabot.yml](../.github/dependabot.yml)의 `npm` 항목 주석을 해제한다.

## 설정

Vite는 `VITE_`로 시작하는 환경변수를 브라우저 번들에 그대로 넣는다. 비밀값·API 키는 `VITE_` 변수에 두지 않는다. 화면이 필요한 값은 모두 백엔드 `/api`를 거친다.
