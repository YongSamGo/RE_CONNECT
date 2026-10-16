# 다음 세션용 작업 요약

최종 확인: 2026-10-16. 이 문서는 맥락 인계용이며 GitHub 이슈·계약·코드를 대신하지 않는다.

- 사용자 지시: 중복을 먼저 정리하고 이후에는 GitHub 이슈의 우선순위·선행 조건을 보고 작업한다. 이미 허용된 로컬 개발을 매번 재확인하지 않는다.
- 작업 저장소: `YongSamGo/RE_CONNECT`. 원래 remote URL `jokebear117/RE_CONNECT`는 이전 주소다.
- **현재 작업 폴더:** `C:/Users/seong/.codex/worktrees/frontend-deduplicate/SW개발보안`. 원래 `Documents/ChatGPT/SW개발보안` 폴더에서 새 기능을 작성하지 않는다. 그 폴더는 이전 구현·미추적 Vault/PDF 등을 보존 중이다.
- **현재 브랜치:** `feat/w02-08-region-contract`, 정리 기준 `4513c77`, 진행 기록 기준 `dfd4cbf`에서 후속 작업.
- 단일 프론트: PR #118의 `891c8e2` 기반. `origin/develop`의 `10d196f` 포함. 원래 자체 구현 `c733f0e`·`d29b4f0`는 이력에 보존했지만 중복 소스는 실행 트리에서 제외했다. [정리 기록](CONSOLIDATION.md).
- API 계약은 `docs/api/openapi.yaml`, 생성 타입·클라이언트는 `src/api/`. 기존 기능에 이어 작성하고 두 번째 상태/통신/스타일 체계를 만들지 않는다.
- 기동 중인 미리보기: `http://127.0.0.1:5173/`는 현재 작업트리의 Vite. 실제 서버·AI·인증·음성 연동 성공과 구분한다.
- 확인된 검증: Node 24, 기존 프론트 319건 + `npm run test:backend-contract` 5건, lint, build(API 타입 비교+TS+Vite), audit(0건)·패키지 서명 통과. backend Python 3.12 `.venv`에 고정 해시 의존성 설치 후 지역·공통 계약 pytest 127건 통과. 화면 기능은 바꾸지 않았다. 문서만 바꾸면 전체 시험을 불필요하게 반복하지 않는다.
- 2026-10-16 조회에서 #5·#12·#14·#15는 CLOSED. #13은 PR #118에 구현되어 있으나 OPEN이고 Code Owner 승인이 필요하다. #19·#80~89는 코드가 있어도 실제 연동/기기 검증 미완료. 상태를 새로 조회한 뒤 판단한다.
- #11의 인계/진행 기록은 `dfd4cbf`에 작성했다. 현재 후속은 **#19 / W02-08.b**: 실제 지역 라우터 ASGI 응답 → OpenAPI 응답 스키마 → 기존 FE 지역 파서를 대조하는 검사와 CI 연결. [실행·범위](contract-tests/README.md). export_regions.py는 전체 앱이 아니라 실제 router를 독립 마운트하며 `.env`·DB·AI·리스닝 포트를 사용하지 않는다. 외부 서버·전체 앱·브라우저 HTTP 통합 성공으로 표현하지 않는다.
- #19 잔여: #13(PR #118) 승인·병합, 전체 앱/같은 origin의 브라우저 HTTP 경로·공통 오류 실응답 대조, 원격 CI. 기존 타입 생성/클라이언트를 재작성하지 않는다. #9 운영 동의문과 #36 체험 API 없이 실제 개인 데이터 처리·서버 여정 연동을 시작하지 않는다. GitHub에 댓글·상태 변경·push·PR 생성은 하지 않았다.
- 보안: 사용자가 제공한 AGENTS.md → 원래 폴더의 `SW개발보안_obsidian/Security/INDEX.md` → 관련 원문을 선택 참조한다. 배포본은 현재 작업트리 `team-vault/SW개발보안_obsidian/Security/`에도 있다. 기존 원문·PDF·Obsidian 설정 보존. 새 기술 판단을 공식 가이드 정책으로 설명하지 않는다.
- 위험한 저장소 변경·원격 병합·보호 우회·실제 인증/개인 자료 삭제는 이 인계의 자동 허가가 아니다.
