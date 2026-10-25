# 공식 자료 수동 입력과 20건 목표 추적 — W06-08

API 인증키가 없는 경우에도 운영자가 직접 읽은 공식 채용·봉사 자료를 검수 대기 버전으로 저장한다. 실제 자료만 등록하며 시험 fixture·교육 과정·발견한 제목만으로 공고 수를 채우지 않는다. 이 명령은 서버에 HTTP 경로를 만들거나 외부 신청을 대신하지 않는다. 웹 운영자 인증/MFA·등록 UI는 #52/#53에서 연결한다.

## 실행 권한과 준비

이 명령은 DB 쓰기 권한이 있는 신뢰된 운영자용이다. 공개 API나 일반 사용자 입력에 직접 연결하지 않는다. DB 연결은 기존 `build_engine`을 사용하므로 production의 PostgreSQL verify-full/CA 규칙도 같다. 입력 파일은 커밋하지 않고 접근을 제한한 로컬 경로에 둔다. 실제 API 키나 개인정보는 필요하지 않다.

`python -m alembic upgrade head`로 `0004_manual_evidence`까지 적용한다. 활성 수동 Source를 먼저 준비한다. 아래는 DB 관리자가 고용24 출처를 처음 설정할 때의 SQL이다. 같은 code가 있으면 새로 만들지 말고 기존 설정을 확인한다.

```sql
INSERT INTO sources (id, code, name, base_url, enabled)
VALUES (gen_random_uuid(), 'manual_work24', '고용24 수동 확인', 'https://www.work24.go.kr', true)
RETURNING id;
```

지원하는 code/base_url은 `manual_work24`/`https://www.work24.go.kr`, `manual_50plus`/`https://www.50plus.or.kr`, `manual_volunteer`/`https://www.1365.go.kr`이다. 호스트만 일치하는 임의 경로는 허용하지 않는다. 고용24의 실제 `empDetailAuthView.do`/VALIDATION/tb_workinfoworknet 상세 링크, 50플러스 일자리 `appView.do?ANN_NO=숫자` 또는 `in_appView.do?ANN_NO=숫자`, 1365 `P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=숫자` 형식만 받는다. 1365 실제 정상 자료의 현행 경로/조건 재확인은 남아 있다. 새 기관·경로는 코드 리뷰와 실자료 확인 후 허용표에 추가한다. 노원구청 등 다른 공식 기관의 자료도 현재 허용표 밖이면 보류한다.

## 입력 계약

UTF-8 JSON 한 건에 `source_id`, 선택 `manual_target`, `snapshot`, `evidence`를 넣는다. `snapshot`은 [OpportunityContent](../../backend/app/contracts/opportunity.py)의 모든 키와 `description_truncated`를 가진다. 선택 키도 모르면 null로 명시한다. 알 수 없는 근무시간·원격 여부·지역·기한을 추정하지 않는다. 목록 제목의 마감이 실제 접수처와 다르면 접수처를 재확인한다. 원문에 없는 날짜·24시를 조합해 마감 시각을 만들지 않는다.

`evidence`의 키:

| 키 | 내용 |
| --- | --- |
| `url` | 직접 확인한 공식 상세 주소. snapshot.source_url과 정규화 후 같아야 함 |
| `observed_at` | 실제 확인한 시간대 포함 시각. 저장 시 미래/48시간 초과는 거절 |
| `confirmed_official` | 공식 자료를 직접 확인했다는 명시적 boolean true. 자동 진위 증명이 아님 |
| `quotes` | 필드 이름 → 해당 필드의 짧은 원문 근거(각 300자 이하). 전체 본문 복사 금지 |

quotes에는 title/organization_name/activity_type/application_method/application_instructions/recruitment_status/requirements가 반드시 있어야 한다. 지역·날짜·일정·보수·서류·근무시간·역할 등 추가로 입력하는 필드에도 근거가 필요하다. 별도 application_url에도 근거를 붙인다. 요구사항 빈 배열은 명시된 필수조건이 없음을 확인한 경우에만 사용한다. 아직 해석하지 못한 조건은 `other`/`needs_review`로 남긴다. 역할 태그는 기존 RoleDefinition에 있어야 한다.

출처와 근거에는 연락 담당자의 이름·전화·이메일·세부 개인정보를 옮기지 않는다. 접수 안내는 공식 링크에서 연락처를 확인하도록 작성한다. 일반 텍스트·숨은 문자·길이·타입을 검사하고 흔한 연락처/식별번호 형태는 거절하지만 완전한 개인정보 탐지기는 아니다. 기관명이 개인 이름이거나 예외 형식의 개인정보가 섞였는지는 운영자가 직접 확인해야 한다. 원문은 비신뢰 데이터이며 LLM 프롬프트나 HTML로 실행하지 않는다.

## 명령

backend 폴더에서 POSIX 셸:

```bash
python -m app.manual_intake --validate < ../security-reports/manual-input.json
python -m app.manual_intake --record < ../security-reports/manual-input.json
python -m app.manual_intake --progress
```

PowerShell에서는 입력 리다이렉트를 지원하는 셸로 전달한다.

```powershell
cmd /c "python -m app.manual_intake --validate < ..\security-reports\manual-input.json"
cmd /c "python -m app.manual_intake --record < ..\security-reports\manual-input.json"
python -m app.manual_intake --progress
```

validate는 DB 연결 없이 형식만 검사한다. 실제 자료·모집 상태·시각·출처 활성화·역할 사전은 저장/검수 시 확인하므로 형식 통과를 공고 확보로 세지 않는다. stdin은 64KiB/24단계로 제한하고 중복 JSON 키·NaN·알 수 없는 키·서버가 관리하는 승인/버전을 거절한다. 원문·입력·예외 문자열은 출력하지 않는다.

새 자료는 항상 pending이다. 중복 후보가 있으면 VERSION_CONFLICT이고 자동 병합하지 않는다. 운영자가 공식 자료/모집 기간을 대조한 뒤 기존 공고 UUID를 manual_target으로 명시한다. 오래된 관측은 거절한다. 같은 입력의 명시 재전송은 콘텐츠 버전·근거를 늘리지 않으며, 변경은 새 pending 버전으로 남는다. 이전 공개 포인터는 보존된다. 근거 저장 실패 시 버전 생성/확인 시각 변경도 같은 트랜잭션에서 롤백한다. 출처 last_success_at은 API 전체 순회 성공의 의미를 유지한다.

`manual_evidence`에는 공고 버전 FK·상세 URL·확인/등록 시각·최소 필드 근거·SHA-256을 저장한다. 같은 근거의 중복을 막고 UPDATE를 DB 트리거로 거절한다. 새 확인은 새 근거 기록이다. 해시는 저장 내용의 무결성 식별용이며 공고 진위·승인을 보증하지 않는다. DB 관리자의 원본 접근/삭제 권한까지 차단하는 감사 시스템은 아니다. 다운그레이드는 근거 테이블을 제거하므로 실제 운영에서는 백업과 보관 정책 확정 후 수행한다.

## 20건 집계의 의미

progress는 활성 수동 출처에 근거가 있는 최신 버전만 검사한다. 48시간 이내 실제 확인·모집 중·마감 미경과·활동 지역 또는 명시 원격·미해석 조건 없음·설명 미절단인 자료를 `current_candidates`로 센다. 그중 검수 approved인 수는 `current_approved`다. 두 수를 더하지 않으며 승인 자체가 공개 포인터 생성은 아니다. 목표 20 대비 candidate_shortfall/approved_shortfall을 각각 반환한다.

출처 URL 또는 기관·제목·마감이 같은 후보는 중복 집계하지 않는다. 서로 다르게 표기된 동일 모집의 완전한 식별은 사람 대조가 필요하다. 출처별 필드 진위·전체 조건 누락 여부도 검수로 확인한다. stale/closed/unknown/rejected/hidden/조건 미해석 자료는 현재 유효 후보 수에 넣지 않는다. 테스트용 DB의 가상 fixture 수를 실제 확보 수로 보고하지 않는다.

현재 실제 자료의 개별 확인·보류 이유·목표 미달은 커밋하지 않는 `security-reports/`의 확보 기록으로 관리한다. 접근 불가·자료 부족으로 20건에 못 미치면 부족 수를 그대로 기록한다. 이 PR의 코드/DB 검증은 운영 승인과 20건 실제 확보 완료를 뜻하지 않는다.

2026-10-25 공식 페이지 확인: [가치동행일자리](https://www.50plus.or.kr/appView.do?ANN_NO=1505), [경력인재지원](https://www.50plus.or.kr/in_appView.do?ANN_NO=1271). 일반 센터 게시글 `detail.do?id=`는 일자리 상세 근거로 허용하지 않는다. 추가 쿼리·중복 식별자·유사 호스트도 거절한다. 주소 형식 검증은 내용 검수·공개 승인을 대신하지 않는다.
