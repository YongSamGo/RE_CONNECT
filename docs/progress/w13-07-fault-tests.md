# W13-07 장애·배포·롤백 시험 진행 기록

[진행 상태 기록 양식](../progress.md#기록-방법)을 따른다. Related to #104.
이 기록과 PR은 이슈를 닫지 않으며 실제 배포 증거 전에는 통과로 옮기지 않는다.

```text
작업: #104 / W13-07
담당·협력: C(SeungwonKwon) · 협력 B, A
상태·확인 시각(KST)·확인자: 검토 · 2026-10-29 · SeungwonKwon
코드 작성 / 계약 예제 연결 / 실제 연동 / 배포 검증: 로컬 장애 도구·초기화 구현 / 백엔드 시험 / 로컬 Docker만 확인 / 미검증
commit·PR·CI: 기준 develop dfcba3e. PR·CI는 이 기록을 추가한 PR에서 확인
환경·모델·프롬프트·공고 버전: Windows·Python 3.12.13·PostgreSQL 16·Redis 7, 개발 Compose, 모델 닫힌 포트, 공개 공고 목록 조회(최신 실제 공고 증거 아님)
사례 ID / 기대 / 실제 / 판정: 아래 장애 결과표·시험 대응표 참조
완료 증거: 로컬 Docker 장애 도구 6단계·42개 확인 항목 완료. 아래 검증 명령과 PR의 CI 참조
미구현·미검증·후속 담당: 실제 Ollama·음성 종료/재시작 B·C, EC2/RDS·HTTPS·롤백 C, 화면과 최신 실제 공고 A·C (#98), 인수 #105
차단 원인 / 영향 / 해제 조건 / 해결 담당: EC2·RDS 비용 미승인 및 릴리스 증거 없음 / ③ 배포 게이트 / 비용 승인·#97/#98와 릴리스 준비 후 실제 재시험 / A·B·C
다음 확인 시각(KST) / 확인할 대상: 미정 — 담당자 확인 필요 / #313 머지 뒤 runbook 수정, 비용 승인 뒤 배포 시험
실제 시작 / 종료 / 제외 시간 / 작업 분 / 작성자: 미기록
기존 목표 / 변경 제안 / 결정자·결정일: 기존 계획 참조 / 없음 / -
재시험 결과: 로컬 결과만 아래에 기록. 배포 재시험 미실행
```

## 로컬 장애 결과

모든 단계에서 LLM·음성 readiness는 `fail`이다. 모델은 닫힌 포트, 음성은 미구성이다.
`run`은 실제 admission 서비스에 종료 확인 콜백을 넣은 결과이며 모델·음성 서버 호출 성공이 아니다.
`/me`는 익명 세션 확인이며 DB 저장·회원 로그인 성공 증거가 아니다.

| 단계 | 기대 | 실제 readiness / checks(db, redis, llm, speech) | regions / opportunities / me | admission run(LLM·STT·TTS) | 판정 |
| --- | --- | --- | --- | --- | --- |
| 기준: 확인된 0 init | 모델만 저하, 공개 조회 유지 | 200 degraded / ok, ok, fail, fail | 200 / 200 / 200 | 모두 허용(종료 확인 콜백) | 로컬 통과 |
| Redis stop | 준비 불가, 사적 처리 거부 | 503 unavailable / ok, fail, fail, fail | 200 / 200 / 503 SERVICE_UNAVAILABLE | 모두 503 SERVICE_UNAVAILABLE | 로컬 통과 |
| Redis start, init 전 | Redis 연결과 추론 준비를 구분 | 200 degraded / ok, ok, fail, fail | 200 / 200 / 200 | 모두 503 SERVICE_UNAVAILABLE | 로컬 통과 |
| 기본 init | 기록 유실 시 당일 추론 차단 | 200 degraded / ok, ok, fail, fail | 200 / 200 / 200 | 모두 429 DAILY_QUOTA_EXCEEDED, Retry-After 20719초 | 로컬 통과 |
| PostgreSQL pause | DB 의존 조회 실패, 정적 지역 유지 | 503 unavailable / fail, ok, fail, fail | 200 / 503 SERVICE_UNAVAILABLE / 200 | 당일 차단 유지, 모두 429·Retry-After 있음 | 로컬 통과 |
| PostgreSQL unpause | DB 조회 복구, 당일 차단 유지 | 200 degraded / ok, ok, fail, fail | 200 / 200 / 200 | 모두 429·Retry-After 있음 | 로컬 통과 |

이번 실행에 15초 요청 시간 초과는 없었다. DB는 tmpfs이므로 stop 대신 pause/unpause로
연결 장애만 재현했다. 이는 RDS 재시작·데이터 보존·백업 복구 시험을 대신하지 않는다.
readiness의 Redis `ok`는 연결·비영속화 확인이며 추론 제어 해시 준비까지 보장하지 않는다.

## 준비 상태별 사용 경로

| 상태 | 사용 경로 | 근거와 제한 |
| --- | --- | --- |
| ready | 의존성 준비 후 공개 조회·직접 작성·AI 경로 사용 | test_health의 주입 probe 시험. 실제 모든 서버 ready는 이번에 미검증. 동의·세션·일일 한도·슬롯 검사는 별도 |
| degraded | 공개 공고 조회, Redis·세션이 정상이고 자료가 남아 있으면 직접 작성. AI 실패 시 직접 작성 유지 | 로컬 모델 미연결·공개 조회 200, test_journey_drafts의 실패 후 본문 보존 시험. 실제 화면 전환은 #98 이후 |
| unavailable | 정적 지역은 조회 가능. Redis만 실패하면 DB 공개 공고 조회 가능, DB 실패면 공고 조회도 503 | 로컬 장애 결과. 사적 처리에는 실패한 의존성을 우회하는 대체 저장소를 쓰지 않음 |

429는 일일 한도(`DAILY_QUOTA_EXCEEDED`), 분당 요청(`RATE_LIMITED`), 공유 슬롯
(`INFERENCE_BUSY`)을 구분하며 Retry-After를 따른다. 503은 의존성/제어 기록 준비 실패
(`SERVICE_UNAVAILABLE`), 모델 미연결(`MODEL_UNAVAILABLE`), 실행 시간 초과(`AI_TIMEOUT`)를
구분한다. 준비 상태만으로 요청 성공을 보장하거나 재시도로 집계를 초기화하지 않는다.

## 시험 대응과 운영 절차

| 시험 | 확인하는 경계 | 증거 범위 |
| --- | --- | --- |
| test_admission | Redis 유실→503→기본 init→429→다음 KST 날짜 재개, 세 실행 종류, 기존 해시·점유·TTL 비덮어쓰기, 잘못된 입력·키·연결 실패, CLI 확인 플래그와 종료 코드 | 실제 Redis. 날짜 전환은 필드를 전날로 옮겨 분기 재현 |
| test_journeys | 기본 복구 날짜의 새 대화 거절, 확인된 0 시작 허용, 다음 날짜 재개, 잘못된 복구 날짜 거부 | 실제 Redis. 복구 당일에는 새 대화도 429 |
| test_health | ready/degraded/unavailable 분기·probe 오류/시간 초과와 고정 응답 | 주입 probe 계약 시험 |
| test_operations_status | 구성 요소·추론 제어·슬롯과 운영 상태 분리 | 기존 운영 상태 시험 |
| test_journey_drafts | 모델 실패 후 직접 고친 본문·revision 보존, 새 키 재시도, 안전한 근거가 없으면 모델 생략 | 가상 모델·실제 Redis, 화면·실제 모델은 미검증 |
| test_fault_drill | 오류 원문 미출력·15초 제한·고정 Docker 인자·외부 DB 거부 | 도구 단위 시험 |

운영자 init의 두 모드와 금지 상황은 [추론 제어 절차](../security/inference-admission.md#설정과-제어-레코드-준비)를 따른다.
기본 init은 오늘 전역 집계 500과 복구 날짜를 기록한다. 확인된 0 시작은 오늘 실행이
없음을 확인했을 때만 사용한다. 같은 날 재기동이나 운영 중 Redis 장애에 0 시작을 쓰지 않는다.
기존 해시는 init으로 덮어쓰지 않고 점유 슬롯은 런타임 종료 확인 후 release 절차를 따른다.
#313의 runbook 수정은 #313 머지 뒤 이 PR에 추가한다.

`backend/`에서 개발 Compose용 환경변수(`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`REDIS_PASSWORD`)와 루프백 시험 URL(`PERSISTENCE_TEST_DATABASE_URL`, `PERSISTENCE_TEST_REDIS_URL`)을
셸에 설정한다. URL·비밀값은 출력하거나 커밋하지 않는다.

```powershell
.venv/Scripts/python.exe -m tools.fault_drill --confirm-disposable-local
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m bandit -r . --exclude ./tests,./.venv --severity-level low --confidence-level medium
git diff --check
```

장애 도구는 **폐기 가능한 로컬 환경 전용**이며 Redis 재시작이 임시 자료를 지운다.
다른 시험·백엔드와 동시에 실행하지 않는다. 기존 제어 해시가 있으면 도구는 중단한다.
별도의 폐기용 환경을 준비하고 다시 실행하며 기존 운영 해시를 지우지 않는다.
실패 시 Redis start·DB unpause를 시도한다. 명령 자체가 실패하면 컨테이너 상태를 운영자가 확인한다.
출력은 상태·고정 코드·checks·Retry-After와 timeout/probe_failed만 담는다.
검증 원문은 공개하지 않는 `security-reports/`에 보관한다.

변경 영역 재시험(`test_admission`, `test_journeys`, `test_fault_drill`)은 40개 통과했다.
전체 backend 시험 결과와 CI는 PR 검증란에 기록한다. Bandit 1.9.4의 요청된 전체 검사,
숨은 문자 검사, `git diff --check`는 통과했다.

## 배포 게이트

| 항목 | 판정 | 차단 사유·해제 조건 |
| --- | --- | --- |
| 실제 모델·음성 장애와 재시작·GPU 슬롯 종료 | 차단 | 실제 런타임 미기동. B·C의 고정 런타임 종료 증거 필요 |
| HTTPS·인증서·보안 헤더·세션 쿠키 | 차단 | 로컬 ASGI는 TLS 증거가 아님. #97과 배포된 HTTPS 환경 필요 |
| 새 EC2/RDS 환경·마이그레이션·준비 상태 | 차단 | 비용 미승인. EC2/RDS를 켜지 않음. 비용 승인 후 실제 시험 |
| 릴리스 배포·이전 릴리스 롤백·데이터/삭제 상태 보존 | 차단 | 릴리스·실제 배포 증거 없음. #97 준비 후 운영 절차로 시험 |
| 최신 실제 공고·공개 조회/직접 작성 화면 | 차단 | #98과 실제 검수 공고·브라우저 연결 증거 필요 |

위 차단 항목이 남아 있으므로 #104는 검토 상태를 유지한다. #105 인수에는 실제 환경의
증거와 차단 해제 확인을 추가해야 한다.
