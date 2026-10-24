# 영구 저장 스키마 구현 (W02-05/06)

관련: #16·#17. 기준: Plan/02 §1·§3·§4·§5·§6, API의 SavedProfile/SavedDraft/ConsentPurpose.
SQLAlchemy 메타데이터 구현과 SQLite 제약 시험 단계다. PostgreSQL 실행·마이그레이션은 #18,
암호화·저장 API는 #25/#75/#76에서 검증한다.

## 논리 엔터티와 물리 테이블

| 논리 엔터티 | 테이블 | 저장 내용 |
| --- | --- | --- |
| User | users | 내부 UUID·카카오 연결 식별자·역할·계정 상태·생성 시각 |
| Consent | consents | 회원 FK·처리 목적(ai_processing/storage)·안내문 버전·동의/철회 시각 |
| ProfileVersion | profile_documents + profile_versions | 안정 프로필 ID·소유자, 불변 확정 버전의 암호화 봉투 |
| ApplicationDraft | application_documents + application_drafts | 안정 문서 ID·소유자, 승인 저장 버전·프로필/공고 버전 근거·암호화 봉투 |

identity 테이블 2개는 논리 엔터티를 추가한 것이 아니라 여러 버전에 같은 ID·소유자를
강제하기 위한 물리 구조다. 회원당 저장 프로필 계열은 하나이고 계열마다 여러 버전이 있다.
서로 다른 회원이 같은 프로필 ID의 후속 버전을 차지할 수 없도록 복합 FK를 사용한다.
지원서는 문서 소유자·프로필 계열·프로필 버전의 소유자가 모두 같아야 INSERT할 수 있다.

프로필 계열 삭제는 전체 버전 및 파생 문서/지원서 버전을 CASCADE로 삭제한다.
회원 삭제는 동의와 저장 자료까지 CASCADE다. 개별 버전 삭제는 그 버전에 근거한 지원서를 삭제한다.
개인정보 복구 삭제 이력·감사 기록의 별도 수명은 #17/#95에서 다룬다.

키 원문·평문 프로필/지원서·대화·전사·임시 편집본·Journey·OAuth 토큰을 저장하는 칸은 없다.
암호화 봉투에는 ciphertext(태그 포함), 12바이트 nonce, key_id(키의 참조), algorithm,
schema_version만 둔다. DB에 별도 키 테이블을 만들지 않는다.
같은 테이블의 key_id/nonce 중복도 거절한다. 테이블 간 nonce 재사용 방지와 실제 암호화·AAD·
키 존재/회전은 #25의 책임이다. bytes 형식만으로 실제 암호문임을 증명할 수는 없다.

필수 승인/확정 시각, 양의 버전, 저장 시각 순서, envelope 길이·알고리즘을 CHECK/NOT NULL로
검사한다. 모델이 시각을 자동 확정하지 않으며 서비스가 검증한 시각을 넣어야 한다.
ORM UPDATE는 거절하고 새 승인 버전을 INSERT한다. Core/bulk SQL도 차단하는 PostgreSQL
트리거는 #18에서 연결한다. 메타데이터만으로 서비스의 동의·권한·확정 검사를 대신하지 않는다.

ApplicationDraft의 공고 ID/버전은 공고 모델의 복합 FK와 연결했다. 참조한 과거 공고 버전은
지원서/신고가 남아 있으면 삭제할 수 없다. 공개/추천용 모델과 암호화 저장 모델을 혼합하지 않는다.

## 공고·수집·운영 모델

| 논리 엔터티 | 테이블 | 저장 경계 |
| --- | --- | --- |
| Source | sources | 코드·고정 출처 설정·이용 조건 URL·최종 성공 시각. 서비스 키 없음 |
| IngestionRun | ingestion_runs | 출처 FK·실행/종료 시각·상태·건수·고정 실패 코드. 원문 예외 없음 |
| RoleDefinition | role_definitions | 역할 ID·표시명·설명·태그·별칭·경험 연결 규칙. 실제 후보 경험은 체험에 보관 |
| OpportunityVersion | opportunity_documents + opportunity_versions + opportunity_publications | 출처별 안정 ID, 검색 가능한 공고 버전/조건, 승인 공개 포인터 |
| Report | reports | 대상 공고 버전·유형·상태·버전, 선택 설명/처리 문구는 암호화 봉투 |
| AuditEvent | audit_events | 행위·결과 허용표·주체/대상 UUID·추적 ID·만료 시각. 임의 메시지 없음 |
| DeletionRecord | deletion_records | 삭제 주체/대상 내부 UUID·범위·상태·시각·만료. 원문·외부 계정 식별자 없음 |

영구 논리 엔터티는 11개이며 Journey를 더한 12개 논리 엔터티의 저장 경계를 구분했다.
Journey는 Redis 대상이라 RDS 테이블이나 FK가 없다. 물리 테이블은 안정 ID 3개와 공개
포인터 1개를 더해 15개다. 감사·삭제 UUID는 User FK로 묶지 않아 회원 삭제로 함께 사라지지 않는다.
30일 보관의 만료 시각은 쓰기 서비스가 정하고 #57/#96에서 실제 정리한다. DB에 만료 인덱스를 둔다.

출처별 `(source_id, external_id)`는 유일하다. 외부 ID 없는 수동 공고는 서로 자동 병합하지 않고
#47에서 공식 URL·기관·제목·모집기간을 대조한다. 출처 URL의 DB HTTPS 접두사 제약은 SSRF
허용표가 아니다. #45는 통신 전에 고정 출처 레지스트리와 실제 목적지·리다이렉트를 별도 검증해야 한다.

공고 scalar 필드는 검색 가능한 칼럼, 역할/역량·조건·서류는 PostgreSQL JSONB다.
JSON 구조·지역 목록·원문 조건·URL 검증은 공통 OpportunityContent와 저장 서비스의 책임이다.
`change_pending`은 저장 필드가 아니라 공개본/새 버전의 차이로 계산한다(#47).
content_hash는 변경 감지용이며 공개 승인이나 콘텐츠의 진위를 증명하지 않는다.

공개 포인터의 PK로 공고당 공개본 하나를 강제한다. `(공고 ID, 버전, approved)` 복합 FK로
미승인·다른 공고 버전 공개를 거절한다. 승인본을 숨길 때는 같은 트랜잭션에서 먼저 공개 포인터를
제거한다. 새 pending 버전은 이전 공개 포인터를 변경하지 않는다. 실제 승인·반려·동시성은 #54이다.
신고 설명의 선택 암호화 봉투 형식은 AES-256-GCM(태그 포함)이며 키 원문은 두지 않는다.

운영 모델 시험은 출처 ID 중복, pending/다른 공고 공개, 공개 포인터 중복·숨김 순서,
설명 길이·검수 시각, 신고 대상/암호화 봉투, 실행 종료 시각·음수 집계, 감사/삭제 기록의
회원 삭제 후 생존을 포함한다. 실제 PostgreSQL 실행 증거는 #18에서 추가한다.

## 검증 범위

실제 SQLite FK를 켜고 정상 저장, 다른 회원의 프로필 참조, 없는 버전, 중복/0 버전,
승인 전 저장 시각, 불완전 봉투, nonce 재사용, 철회 시각 순서, 연쇄 삭제, ORM 덮어쓰기
거절을 시험했다. 쿼리 값은 바인딩하고 SQL 삽입 문자열이 조회 조건을 바꾸지 않는지 확인했다.
시간대 없는 시각을 거절하며 UTC로 정규화한다. PostgreSQL DDL은 UUID/BYTEA/timestamptz로
컴파일한다. 실제 PostgreSQL의 무결성·트리거·동시성은 아직 검증하지 않았다.

## 보안 원문 연결

`SW개발보안_obsidian/Security/INDEX.md`에서 선택한 원문의 저장소 상대경로다.
Python 가이드는 구현 원칙, 2021 가이드는 진단 관점으로 구분해 사용했다.

- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제1절-입력데이터-검증-및-표현/006-1.-SQL-삽입.md`:
  제2장 제1절 1항, PDF 14~19쪽. 바인딩된 쿼리 사용.
- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제2절-보안기능/024-2.-부적절한-인가.md`:
  제2장 제2절 2항, PDF 78~80쪽. 소유자 관계를 복합 FK로 추가 방어. API 인가는 후속 서비스에서 별도 검사.
- `team-vault/SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제2절-보안기능/027-5.-암호화되지-않은-중요정보.md`:
  제2장 제2절 5항, PDF 87~90쪽. 평문 저장 칸·키 원문 저장을 배제. 암호화 안전성은 #25에서 검증.
- `team-vault/SW개발보안_obsidian/Security/SW-Diagnosis-2021/제4장-구현단계-보안약점-진단/제1절-입력데이터-검증-및-표현/044-1.-SQL-삽입.md`:
  제4장 제1절 1항, PDF 180~193쪽.
- 같은 진단가이드 `제2절-보안기능/063-2.-부적절한-인가.md`: 제4장 제2절 2항, PDF 319~325쪽.
- 같은 진단가이드 `제2절-보안기능/066-5.-암호화되지-않은-중요정보.md`: 제4장 제2절 5항, PDF 337~349쪽.

SQLAlchemy 2.1의 선언형 타입·제약을 사용한다. 가이드의 Django/Java 예제를 그대로 실행하지 않았다.
보관기간·프로필 계열 구조·nonce/봉투 형식은 프로젝트 설계 결정이며 공식 가이드의 스키마 규정이 아니다.
