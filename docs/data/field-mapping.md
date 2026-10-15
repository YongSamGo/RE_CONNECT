# 출처 필드 → 공고 계약 매핑 (W06-01)

> 기준일: 2026-10-15 · 담당: B(AI·데이터) · 관련 이슈: #44 · 앞선 작업: [출처 조사](sources.md)(#8), [API 계약](../api/openapi.yaml) `Opportunity`·`Requirement`
>
> 근거는 `worker/samples/`의 실제 응답(2026-10-14 수집, 노인 구인정보 목록 10건·상세 1건, 1365 목록 48건·상세 4건)이다. 표의 "샘플 값"은 기관·공고 정보만 옮겼고 담당자 이름·연락처·상세주소는 옮기지 않았다.

수집기(#45~#47)는 이 표대로 출처 응답을 `Opportunity` 후보로 바꾼다. 후보는 운영자 검수(`review_status`, 내부 필드)를 거쳐야 공개되므로, 이 단계의 목표는 **원문에 있는 값을 잃지 않고, 없는 값을 만들지 않는 것**이다.

## 1. 출처 설정

| 항목 | 노인 구인정보 (`senuri`) | 1365 봉사참여정보 (`volunteer`) |
|---|---|---|
| 고정 목적지 | `https://apis.data.go.kr/B552474/SenuriService` | `https://apis.data.go.kr/1741000/volunteerPartcptnService` |
| 목록·상세 | `getJobList` → `getJobInfo(id=jobId)` | `getVltrAreaList(schSido=…)` → `getVltrPartcptnItem(progrmRegistNo=…)` |
| 인증키 | `DATA_GO_KR_SERVICE_KEY` (두 출처 공통, `.env`·운영 비밀값 저장소) | 같음 |
| 일 한도(개발계정) | 10,000건 | 1,000건 |
| 지역 범위 | 검색 조건이 없어 전체 페이지를 받고 `workPlcNm` 시·도로 거른다 | `schSido`로 서울·경기·인천만 요청한다 |
| `activity_type` | `employment` 고정 | `volunteering` 고정 |
| 이용 조건 | 이용허락범위 제한 없음 | 이용허락범위 제한 없음 |
| 공식 상세(= `source_url`·`application_url`) | `https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=<wantedAuthNo>&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet` (원 시스템 `stmNm=워크넷`일 때만) | `https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=<progrmRegistNo>` |

- 목적지는 이 표의 두 호스트로 고정하고, 공고 원문에 든 URL을 따라 수집하지 않는다(#45, SSRF).
- 공식 상세 URL은 위 형식에 **식별자만 끼워 넣어** 만든다. 식별자는 노인 구인정보 `^[A-Z0-9]{1,30}$`, 1365 `^[0-9]{1,12}$`에 맞지 않으면 후보를 만들지 않는다. 원문 필드의 URL을 `application_url`로 쓰지 않는다.
- 서울50플러스는 인증키 승인 대기라 이 문서에 넣지 않았다. 승인되거나 CSV 수동 경로로 정해지면 같은 형식으로 더한다.

## 2. 필드 매핑

표기: **직접** = 값을 그대로(형식만 맞춰) 옮김 · **변환** = 정해진 규칙으로 바꿈 · **없음** = 출처에 없어 `null`/빈 값 · **검수** = 후보만 만들고 운영자가 확정

| 계약 필드 | 노인 구인정보 | 1365 봉사참여정보 | 비고 |
|---|---|---|---|
| `title` | 직접: 상세 `wantedTitle`, 없으면 목록 `recrtTitle` | 직접: `progrmSj` | 200자 넘으면 후보 거절(자르지 않음). 앞뒤 공백·제어 문자 제거 |
| `organization_name` | 직접: 상세 `plbizNm`, 없으면 목록 `oranNm` | 직접: `mnnstNm` | 1365 `nanmmbyNm`은 등록 센터(예: `서울특별시 노원구`)라 쓰지 않는다. **확인 필요:** 1365 화면의 "모집기관"이 `mnnstNm`과 같은지 |
| `activity_type` | 고정 `employment` | 고정 `volunteering` | |
| `is_public_job` | 없음 → `null` | 고정 `false` | `organYn`(샘플 `N`)은 뜻이 확인되지 않아 쓰지 않는다 |
| `role_tags` | 검수: 빈 배열로 시작 | 검수: 빈 배열로 시작 | 역할 사전(W08-04)이 정해지면 `jobclsNm`·`srvcClCode`로 후보를 제안한다 |
| `skill_tags` | 검수: 빈 배열로 시작 | 검수: 빈 배열로 시작 | 원문에서 추정해 채우지 않는다 |
| `activity_region` | 변환: `workPlcNm`(예: `경기 안양시 동안구`) 앞 두 토큰 → `Region` | 변환: `sidoCd`·`gugunCd` 행정 코드 → `Region` | 지역 목록(W02-04)의 ID로 바꾼다. 목록에 없는 표기는 `null`(지역 추천 제외) |
| `location_text` | 직접: `workPlcNm` | 직접: `actPlace` | 상세주소(`plDetAddr`·`areaAddress*`)·좌표(`areaLalo*`)는 옮기지 않는다 |
| `remote_allowed` | 없음 → `null` | 없음 → `null` | |
| `schedule_text` | 없음 → `null` | 변환: `actWkdy`·`actBeginTm`~`actEndTm`·`progrmBgnde`~`progrmEndde` → 예: `목 14~16시 (2026-07-14 ~ 2026-10-14)` | 원문 값을 사람이 읽는 형식으로만 바꾼다 |
| `hours_per_week` | 없음 → `null` | 없음 → `null` | 1365 하루 시간 × 요일 수는 "매주 활동"이 확인되지 않아 계산하지 않는다(예: `3490135`는 "주 1회 정기봉사"인데 `actWkdy`는 목요일 하나뿐) |
| `paid` | 고정 `true` | 고정 `false` | |
| `compensation_text` | 없음 → `null` | 없음 → `null` | 노인 구인정보 상세 샘플에 임금 필드가 없다. 다른 상세 응답에 있는지 확인 필요 |
| `description_text` | 없음 → `null` | 직접: `progrmCn` | `\r`을 줄바꿈으로, HTML 태그가 있으면 일반 텍스트로. 5,000자 초과는 앞부분 + `description_truncated=true` |
| `requirements` | 검수: §3 | 검수: §3 | 수집 단계에서 빈 배열을 "조건 없음"으로 내보내지 않는다 |
| `required_documents` | 없음 → `null` | 없음 → `null` | |
| `application_method` | 변환: `acptMthd`(`방문` → `visit`, …) 또는 `acptMthdCd` 코드표 | 고정 `online` | 코드표 미확보(§4). 모르는 값이면 후보 거절이 아니라 검수 대기 |
| `application_instructions` | 변환: 접수기간·접수방법을 고정 문구로 | 변환: 모집기간·"1365 자원봉사 포털에서 신청" | 원문 문장을 그대로 넣지 않는다(2,000자) |
| `source_url` / `application_url` | 변환: §1 형식 | 변환: §1 형식 | `stmNm`이 워크넷이 아니면 형식을 몰라 후보 거절 |
| `deadline_date` | 변환: 상세 `toAcptDd`, 없으면 목록 `toDd` (`YYYYMMDD` → 날짜) | 변환: `noticeEndde` | 날짜가 틀리면(예: `20261332`) 후보 거절 |
| `deadline_at` | 없음 → `null` | 없음 → `null` | 시각을 만들어 붙이지 않는다 |
| `recruitment_status` | 변환: §5 | 변환: §5 | |
| `source_checked_at` | 수집 시각 | 수집 시각 | |
| `id`·`version`·`reviewed_at`·`change_pending` | 서버 | 서버 | 수집기가 정하지 않는다 |

옮기지 않는 필드: 담당자 이름·연락처(`clerk`, `clerkContt`, `repr`, `telno`, `email`, `fxnum`, `nanmmbyNmAdmn`), 상세주소·좌표, 신청인원(`appTotal`), 내부 코드(`stmId`, `lnkStmId`, `updrId`). 화면에서는 공식 링크로 안내한다(sources.md §4). 저장 여부의 최종 기준은 #46에서 정한다.

## 3. 조건(`Requirement`) 후보

원문 필드로 조건을 만들 때도 [자격 판정 원칙](../../eval/README.md#채점-기준)처럼 **모르면 통과시키지 않는다**. 아래는 모두 `clarity`와 `source_evidence`를 채운 후보이고 운영자 검수로 확정한다.

| 출처 필드 | 후보 | 이유 |
|---|---|---|
| 노인 구인정보 상세 `age`(샘플 `60`) | `field=other`, `operator=null`, `clarity=needs_review`, `source_evidence="구인 연령: 60"` | 명세에 "구인 연령"으로만 있어 "60세 이상"인지 "60세"인지 확인되지 않았다. 확인되면 `age gte 60`으로 바꾼다 |
| 노인 구인정보 `etcItm`(예: `보훈취업지원대상자, 장애인`) | 조건으로 만들지 않음 | 우대 사항이지 필수조건이 아니다. `description_text`가 없으므로 상세 화면용 우대 정보 칸은 별도 논의 |
| 1365 `adultPosblAt`·`yngbgsPosblAt` 등 | 조건으로 만들지 않음 | 대상 가능 여부 표시이고 연령 조건이 아니다. `adultPosblAt=N`인 공고는 수도권 시니어 대상이 아니므로 **후보에서 제외** |
| 1365 `actWkdy` | `weekday includes_any [요일…]`, `clarity=needs_review` | "그 요일 중 하루"인지 "전부"인지 원문마다 다르다(`3490135`는 주 1회 목요일, `3520623`은 `1111110`인데 본문에 활동 요일 조건이 없음). 운영자가 `includes_any`/`includes_all`을 고른다 |
| 1365 `progrmCn` 본문의 연령·자격 문장 | 수집기는 만들지 않음 | 본문 해석은 LLM 보조 + 검수 단계(W06-03 이후)에서 한다 |

## 4. 코드·형식 변환

| 값 | 규칙 | 근거·상태 |
|---|---|---|
| `actWkdy` (7자리 `0/1`) | **1번째 자리 = 월요일 … 7번째 = 일요일**로 보고 `1`인 자리를 ISO 요일(1=월~7=일)로 | `3490135` "목요일 정기봉사" = `0001000`(4번째). 샘플 1건뿐이라 **추가 확인 필요**: 주말 공고 1건 이상으로 6·7번째 자리 대조 |
| `actBeginTm`·`actEndTm` | 정수 시(`9`, `14`) → `HH시` | 분 단위 값은 샘플에 없음 |
| `YYYYMMDD` 날짜 | 달력 검증 후 `date` | |
| 1365 `sidoCd` | `6110000` 서울 · `6410000` 경기 · `6280000` 인천 → `province` | 서울·경기는 샘플 확인. **인천 `6280000`은 행정표준코드 기준값이고 샘플 미확인** |
| 1365 `gugunCd` | 행정 코드 → 지역 목록 ID (W02-04) | 코드표를 지역 목록과 같이 만든다 |
| 노인 구인정보 `workPlcNm` | 첫 토큰 `서울`/`경기`/`인천` → `province`, 둘째 토큰 → 시·군·구 | `전남광주`처럼 예상 밖 표기는 수도권 아님으로 보고 제외. 셋째 토큰(구)은 `location_text`에만 남긴다 |
| 노인 구인정보 `emplymShp`·`acptMthdCd` | 코드표 필요 | **미확보** (sources.md §5). 코드를 화면에 그대로 쓰지 않는다 |
| 1365 `srvcClCode` | 이름이 그대로 온다(예: `교육`, `환경ㆍ생태계보호`) | 역할 후보 제안에만 쓴다 |

## 5. 모집 상태

| 출처 | `open` | `closed` | `unknown` |
|---|---|---|---|
| 노인 구인정보 | `deadline=접수중` **이고** 오늘 ≤ 마감일 | 마감일이 지남 | 그 밖의 `deadline` 값, 마감일 없음 |
| 1365 | `progrmSttusSe=2` **이고** `noticeBgnde` ≤ 오늘 ≤ `noticeEndde` | `progrmSttusSe=3`, 또는 `noticeEndde`가 지남 | 그 밖의 상태 코드, 모집 시작 전 |

- 날짜 비교는 Asia/Seoul 기준이다.
- 마감일 당일은 `open`으로 두되 화면에 "마감 임박·공식 페이지 확인"을 표시한다(sources.md §3, `3487369` 사례).
- `unknown`은 추천 후보에서 뺀다(W08-06).

## 6. 후보를 만들지 않는 경우

| 경우 | 처리 |
|---|---|
| 필수 필드(`title`·`organization_name`·공식 URL·`application_method`) 중 하나를 만들 수 없음 | 후보 거절, 수집 집계에 사유 코드 기록(#49) |
| 수도권 밖 (`workPlcNm` 첫 토큰, `sidoCd`) | 거절(정상 제외로 집계) |
| 1365 `adultPosblAt=N` | 거절(정상 제외) |
| 노인 구인정보 원 시스템이 워크넷이 아님 | 거절. 공식 링크 형식을 확인하면 §1에 더한다 |
| 문자열이 계약 최대 길이 초과 | `description_text`만 자르고 나머지는 거절 |

거절은 조용히 버리지 않고 출처·식별자·사유 코드만 남긴다. 원문 내용은 로그에 남기지 않는다.

## 7. 남은 확인 사항

- [ ] `actWkdy` 자리 순서를 주말 공고로 한 번 더 대조 (§4)
- [ ] 1365 화면의 "모집기관"이 `mnnstNm`인지 (§2)
- [ ] 노인 구인정보 `age`의 의미, 임금 필드 유무 — 상세 응답을 더 받아 확인 (§2, §3)
- [ ] `emplymShp`·`acptMthdCd` 코드표 (sources.md §5와 같음)
- [ ] 인천 `sidoCd`를 실제 응답으로 확인 (§4)
- [ ] 워크넷 외 원 시스템의 공식 링크 형식
- [ ] 지역 목록 ID(W02-04)가 정해지면 §4의 지역 변환표를 코드로 만든다
