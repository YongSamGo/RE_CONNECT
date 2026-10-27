# 오류·운영 로그 처리 (W03-07)

관련 이슈: #26. 구현·로컬 검증 완료, 실제 배포 로그·보관 검증은 미완료다.

## 고정 업무 오류

서비스는 `app.core.business_errors.AppError`에 계약의 코드만 넣는다.
예: `raise AppError("VERSION_CONFLICT")` 또는
`raise AppError("REQUEST_IN_PROGRESS", retry_after=2)`.
HTTP 상태와 안내 문구는 중앙 레지스트리에서 정한다. 원문·예외 메시지·임의 헤더를 받지 않는다.
진행 중 요청은 대기 시간을 반드시 지정한다. 대기 시간은 정수 1~86,400초만 허용한다.

모든 오류에 `Cache-Control: no-store`와 서버의 요청 ID를 붙인다.
422에만 필드 오류를 포함하고 입력값·Pydantic 메시지를 버린다. 소유하지 않은 자원은
없는 자원과 같은 `NOT_FOUND`를 사용해야 한다. 이 예외 클래스가 소유권을 대신 검사하지 않는다.
LLM/Speech 실패를 어떤 업무 코드로 바꿀지는 호출 서비스가 선택한다.

## 안전한 실행과 로그

`backend/`에서 `python -m app`으로 실행한다. Uvicorn의 원본 접속 로그는 끄고
`SafeJsonFormatter`를 루트·서버·앱 로그에 적용한다. 기존 외부 라이브러리의 별도 핸들러는
비활성화한다. 다른 실행 명령을 사용할 때도 `LOGGING_CONFIG`를 적용해야 한다.
기본 실행은 로컬 인터페이스 127.0.0.1:8000이며 운영 바인딩·프로세스 관리는 #93에서 연결한다.

요청 로그는 서버 요청 ID, 허용된 HTTP 메서드, 상태, 처리 시간과 UTC 시각만 기록한다.
임의 로그 메시지·포맷 인자·logger 이름·소스 경로·스택·예외·임의 extra를 출력하지 않는다.
따라서 콜백 query(code/state), Authorization/Cookie, OTP, 전사·음성·프로필·지원서 본문을
로그 메시지로 전달해도 이 formatter에서 출력하지 않는다. 라이브러리 원문 대신 일반
`runtime_event`만 남으므로 진단 상세는 줄어든다. request_id로 요청 처리 결과를 연결한다.

이 설정은 `print`, 별도 파일 쓰기, 이후 추가하는 비관리 핸들러, Nginx·Docker·Ollama 자체 로그를
통제하지 않는다. 입력을 그런 경로에 기록하지 않고 배포 시 각 수집 경로도 확인해야 한다.
stdout은 로컬 파일로 복제하지 않으며, 운영 수집 경로에만 필요한 보관기간을 적용한다.

## 보관 설정과 남은 배포 검증

`infra/logging/log-groups.json`은 CloudFormation 로그 그룹 설정이다. 일반 운영 로그는
14일, 보안·운영자 감사는 30일로 설정한다(Plan/02 §5). 이 기간은 프로젝트 정책이다.
`RetentionInDays`는 [AWS 공식 문서](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-logs-loggroup.html#cfn-logs-loggroup-retentionindays)를 확인했다.

아직 AWS에 적용하지 않았다. 이 템플릿은 로그 그룹만 정의하며 EC2 수집기·IAM 권한·
stdout 전달·감사 기록 저장소는 구성하지 않는다. #57·#93·#96에서 수집과 삭제 작업을 연결하고
실제 로그 그룹 보관 값, 오래된 이벤트 만료, Docker·호스트 중복본과 백업의 보관 경계를 확인한다.
CloudWatch의 만료 처리를 물리적 즉시 삭제로 주장하지 않는다. DB 감사 기록의 조회·정리는 아래 절(#57)이다.

## 운영자 감사 기록 (W07-06)

관련 이슈: #57. 코드·로컬 시험 완료. 운영자 MFA(#52) 연결 전이라 실제 운영자 호출은 아직 `MFA_REQUIRED`로 막힌다.

- **저장 칸:** `audit_events`에는 시각·행위자 UUID·역할·행위(허용표 13종)·대상 종류/UUID·결과·`request_id`·만료 시각만 둔다.
  임의 메시지 칸이 없다. 공고 검수의 사유 코드·메모는 같은 `request_id`의 `opportunity_reviews`에 둔다.
- **보관:** 기록할 때 만료 시각을 30일 뒤로 정한다(`AUDIT_RETENTION`). 조회는 `expires_at > 현재`인 기록만 보여주므로
  정리 작업이 늦어도 30일이 지난 기록은 나오지 않는다.
- **조회:** `GET /api/v1/admin/audit?from=&to=&page=&page_size=`. 매 요청 세션·요청 제한·운영자 역할·MFA를 다시 본다.
  기간은 `[from, to)`, 최대 30일이고 최신순이다. 행위자·행위 필터 같은 계약 밖 쿼리는 422로 거절한다.
- **정리:** `backend/`에서 `python manage_audit.py prune`. 만료된 기록을 지우고 처리 건수만 JSON으로 출력한다.
  DB만 쓰며 Redis가 필요 없다. 주기 실행 연결은 #96(W12-07)이다.
- **기록하지 않는 것:** 감사 조회 자체와 운영자 경로 접근 거부는 아직 남기지 않는다. 거부 기록(`access.denied`)은 #52에서 MFA와 함께 다룬다.
  정정(`opportunity.update`)은 #53, 신고 처리(`report.update`)는 #56, 역할 부여·회수는 #52가 같은 표에 남긴다.

### 개인 본문 조회 경로 점검

`backend/tests/test_admin_routes.py`가 앱의 `/admin/*` 경로와 각 응답 칸을 검토한 목록으로 고정한다. 현재 운영자 경로는
공고 검수 4개(응답: 공고 ID·버전·검수 상태·검수 시각)와 감사 조회 1개(응답: 위 최소 메타데이터)뿐이고,
프로필·지원서·대화·신고 상세 본문을 돌려주는 경로는 없다. 운영자 경로나 응답 칸이 새로 생기면 이 시험이 실패하므로
그때 다시 검토하고 목록을 고친다.

## 검증과 공식 참조

정상 요청·검증 실패·예외·업무 오류에 대해 콜백 query, 토큰, OTP, 본문과 추적 정보의
비노출을 검사했다. 30개 오류 코드를 OpenAPI enum과 대조하고 상태·고정 문구·재시도 헤더를 검증했다.
형식화할 때 입력 객체의 문자열 변환도 호출하지 않는지 검사했다.

`SW개발보안_obsidian/Security/INDEX.md` → 아래 원문을 사용했다. 저장소의 전사본 경로:

- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제4절-에러처리/043-1.-오류-메시지-정보노출.md`:
  제2장 제4절 1항, PDF 131~134쪽. 최소 정보와 미리 정의한 오류 메시지를 구현에 반영했다.
- `team-vault/SW개발보안_obsidian/Security/SW-Diagnosis-2021/제4장-구현단계-보안약점-진단/제4절-에러처리/082-1.-오류-메시지-정보노출.md`:
  제4장 제4절 1항, PDF 419~425쪽. 응답의 오류 원문·내부 구조 노출을 진단했다.

가이드 예제의 Django/Java 코드와 현재 FastAPI 구현은 구분했다. 로그의 14일/30일 정책과
허용 메타데이터 목록은 프로젝트 설계이며 공식 가이드의 보관기간 규정이 아니다.
