# API 요청 위조·과대 입력·응답 캐시 (W03-03)

관련 #22. #20의 세션과 서명된 CSRF 쿠키를 사용한다. 기준은 Plan/03 §4·API 계약 §2.3이다.
실제 프록시/Nginx·HTTPS 배포 검증은 #91에서 별도로 진행한다.

## 변경 요청

등록된 `/api/v1`의 GET 이외 요청은 다음을 모두 충족해야 한다:

1. Origin이 설정한 PUBLIC_ORIGIN과 같은 출처. scheme/host/port로 정규화하고 경로·쿼리·
   fragment·계정 정보·공백/콤마 목록·null·중복 Origin을 거절한다. 운영은 HTTPS만 허용한다.
2. CSRF 헤더와 단일 CSRF 쿠키가 동일하고, 토큰이 현재 세션에 결합된 HMAC 서명일 것.
3. 세션이 존재하고 유휴/절대 수명이 남아 있을 것. Redis 오류는 503으로 실패하고 우회하지 않는다.

PUBLIC_ORIGIN이 없으면 변경 요청을 거절한다. GET은 이 검사로 차단하지 않고, 존재하지 않는
경로/지원하지 않는 메서드는 원래 라우팅의 404를 유지한다. 카카오 GET 왕복의 상태 변경은
#72의 일회 state 검증이 필요하며 이 미들웨어가 대신하지 않는다. 메서드 override 헤더는 쓰지 않는다.
검증 실패 요청은 업무 handler에 도달하지 않는다. CSRF 검증 자체로 세션 유휴 수명을 늘리지 않는다.

CORS 교차 출처 자격증명/와일드카드를 열지 않는다. 프론트는 운영 Nginx 또는 개발 Vite 프록시로
같은 출처의 `/api/v1`에 접근한다. 개발에서는 development 설정과 PUBLIC_ORIGIN=http://localhost:5173
같이 실제 프론트 출처를 명시한다. Origin 검사는 인증·소유권 검사를 대신하지 않는다.

## 입력·캐시

일반 API 본문은 실제 바이트 수 64KiB까지다. Content-Length만 믿지 않고 ASGI chunk를
모아서 세며 초과하면 handler 전에 413을 반환한다. 경계값 64KiB는 허용한다. 선언 길이 불일치,
중복 길이/형식 헤더, Content-Length와 Transfer-Encoding 병기, 잘못된 길이와 gzip 등 압축
본문은 422로 거절한다. 응답에는 원문 값을 넣지 않는다.

`/journeys/{id}/transcriptions`의 multipart 요청에는 파일 6MiB + 봉투 64KiB 상한을 별도로 둔다.
실제 파일 6MiB·형식·시간·필드별 제한은 #33의 업로드 계층에서도 검사해야 한다. 요청은 메모리에
한도 내에서만 보관하고 미들웨어가 파일로 쓰지 않는다. HTTP parser·프록시의 모호한 프레이밍/
읽기 시간·헤더 크기 제한은 ASGI 검사만으로 대체하지 않으며 #91에서 함께 검증한다.

인증·프로필·지원서·AI/복사 응답 등 API 응답은 no-store로 덮어쓴다. 공개 지역 목록·공고 목록/
상세·공식 준비 안내의 GET은 기존 공개 정책을 유지한다. 오류는 공통 오류 처리의 no-store를 쓴다.
공개 경로 아래에 사적 GET을 새로 추가한다면 이 공개 예외 목록도 재검토해야 한다.

## 프록시 경계

`python -m app`은 기본적으로 전달 헤더를 신뢰하지 않는다. TRUSTED_PROXY_IPS의 정확한 IP
목록만 Uvicorn에 넘긴다. wildcard/CIDR을 받지 않는다. 직접 연결 peer가 이 목록에 없으면
X-Forwarded-For/Proto로 client IP·scheme을 바꾸지 못한다. 공개 Origin은 이런 헤더로 계산하지 않는다.
운영자는 Nginx가 전달 헤더를 재설정하고 백엔드에 다른 peer가 접근하지 못하도록 #91에서 검증한다.
기존 `uvicorn ...` CLI를 직접 쓰면 자체 기본값이 적용되므로 위 엔트리의 설정과 동일하게 맞춰야 한다.

## 검증과 공식 원문

정상 요청, Origin 누락/위조/접두사 위장·경로/쿼리/fragment/다중 값, CSRF 누락/위조/다른 세션/
중복 헤더/쿠키, Redis 실패, 64KiB/초과·길이 없는 chunk·모호한 길이/압축, 캐시와 교차 출처
preflight 미허용, 신뢰/비신뢰 직접 peer의 전달 IP를 시험한다. 기존 공개 지역 메서드 404도 유지한다.

Security/INDEX.md에서 선택한 구현 원문:

- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제1절-입력데이터-검증-및-표현/016-11.-크로스사이트-요청-위조(CSRF).md`:
  제2장 제1절 11항, PDF 54~60쪽. 세션 결합 토큰 검증 원칙을 현재 FastAPI에서 구현했다.
- `team-vault/SW개발보안_obsidian/Security/SW-Diagnosis-2021/제4장-구현단계-보안약점-진단/제1절-입력데이터-검증-및-표현/054-11.-크로스사이트-요청-위조.md`:
  제4장 제1절 11항, PDF 272~275쪽. 요청 의도/세션 경계를 진단하는 관점으로 구분했다.

Origin 정규화·구체 쿠키/HMAC·64KiB/6MiB·프록시 IP·캐시 목록은 프로젝트 계약/설계이며 공식
가이드의 고정 숫자나 FastAPI 규격이 아니다. 진단가이드와 가이드의 과거 Django/Flask 예제를 구분한다.
