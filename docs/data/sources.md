# 공고 출처 조사 (W01-05)

> 기준일: 2026-10-14 (서울50플러스 2026-10-17) · 담당: B(AI·데이터) · 관련 이슈: #8 → 후속 #44(출처 설정과 실제 필드 매핑)
>
> 샘플 수집: `python worker/tools/fetch_source_samples.py <source> --operation <op>` (키는 `.env`, 원본 응답은 커밋하지 않는 `worker/samples/`에 저장)

필드를 공고 계약(`Opportunity`)으로 옮기는 규칙은 [필드 매핑](field-mapping.md)(W06-01)에 있다.

## 1. 출처별 접근 상태

| 출처 | 분류 | 접근 상태 | 승인 방식·한도 | 이용 조건 |
|---|---|---|---|---|
| [한국노인인력개발원 노인 구인정보](https://www.data.go.kr/data/15015153/openapi.do) | 취업·공공일자리 | **실제 호출 성공** (목록·상세) | 개발·운영 모두 자동승인, 개발계정 일 10,000건 | 이용허락범위 제한 없음 |
| [행정안전부 봉사참여정보서비스_GW (1365)](https://www.data.go.kr/data/15157582/openapi.do) | 봉사 | **실제 호출 성공** (목록·지역 필터·상세) | 개발 자동승인 / 운영 심의승인, 개발계정 1,000건 | 이용허락범위 제한 없음 |
| [서울50플러스 API](https://www.50plus.or.kr/apiIndex.do) | 사회공헌 일자리·중장년 일자리·교육 | **실제 호출 성공** (2026-10-17, 세 데이터셋) | 관리자 승인(2026-10-14 신청, 2026-10-17 발급 확인). 한도 미안내 | **확인 필요**: 데이터 페이지는 "이용허락범위 제한 없음"(교육은 표기 없음)인데 포털 회원 약관은 사전 승낙 없는 제3자 제공·상업적 사용을 금지한다(§5) |

인증키는 data.go.kr 두 API가 같은 일반 인증키(Decoding)를 쓴다. 운영 키는 팀 계정으로 발급해 EC2의 비밀값 저장소에 두고 저장소에 넣지 않는다.

## 2. 노인 구인정보 (`apis.data.go.kr/B552474/SenuriService`)

| 오퍼레이션 | 요청 변수 | 결과 |
|---|---|---|
| `getJobList` | `pageNo`, `numOfRows` | 성공. `totalCount` 762,038 (마감 공고 포함) |
| `getJobInfo` | `id`=`jobId` | 성공 |

**목록 필드:** `jobId`, `recrtTitle`(제목), `emplymShp`/`emplymShpNm`(고용형태), `workPlc`/`workPlcNm`(근무지 코드/이름, 예: `서울 용산구`), `frDd`/`toDd`(접수기간 `YYYYMMDD`), `deadline`(예: `접수중`), `acptMthd`(접수방법), `jobcls`/`jobclsNm`(직종, 10건 중 1건만 값 있음), `oranNm`(기업명), `organYn`, `stmId`/`stmNm`(원 시스템, 예: `워크넷`)

**상세 필드:** `wantedTitle`, `plbizNm`(사업장), `age`(구인 연령, 예: `60`), `clltPrnnum`(모집인원), `frAcptDd`/`toAcptDd`, `acptMthdCd`, `etcItm`(우대·기타, 예: `보훈취업지원대상자, 장애인`), `wantedAuthNo`(구인인증번호), `createDy`, 담당자·주소 필드

**확인된 데이터 문제**
- `emplymShpNm`에 이름 대신 코드(`CM0105`)가 들어온다. 코드표를 따로 두어야 하고 화면에 코드를 그대로 쓰지 않는다.
- 전국 공고가 섞여 있다. MVP(수도권)는 `workPlcNm`의 시·도(`서울`/`경기`/`인천`)로 거르고, 지역코드 매핑은 #46에서 확정한다. `전남광주`처럼 예상과 다른 시·도 표기가 있어 미확인 표기는 자동 확정하지 않는다.
- 샘플 공고 대부분의 원 시스템이 `워크넷`(고용24)이다. 공식 상세 경로는 `https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=<wantedAuthNo>&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet` (2026-10-14 브라우저로 확인). `empDetail.do`는 오류 페이지가 뜬다. 워크넷 외 원 시스템(`stmNm`)의 공고 링크 형식은 따로 확인해야 한다.
- 목록 검색 조건(제목·지역)이 명세 표에 없어, 수집은 전체 페이지를 돌고 우리 쪽에서 거르는 방식을 기본으로 둔다. 일 한도 10,000건 안에서 마감일 기준 증분 수집 전략이 필요하다(#48, #49).

## 3. 1365 봉사참여정보 (`apis.data.go.kr/1741000/volunteerPartcptnService`)

data.go.kr 페이지에는 오퍼레이션명이 없지만 기존 1365 API와 같은 이름으로 동작한다.

| 오퍼레이션 | 결과 |
|---|---|
| `getVltrSearchWordList` | 성공 (`totalCount` 11,215) |
| `getVltrAreaList` | 성공. `schSido=6110000`(서울)로 2,785건 |
| `getVltrCategoryList` | 성공 |
| `getVltrPeriodList` | HTTP 400 — 기간 파라미터 필수로 추정, 미확인 |
| `getVltrPartcptnItem` | 성공 (`progrmRegistNo` 필수) |

**목록 필드:** `progrmRegistNo`, `progrmSj`(제목), `progrmSttusSe`(모집상태 코드, 샘플에 `2`·`3`), `progrmBgnde`/`progrmEndde`(봉사기간), `nanmmbyNm`(모집기관), `sidoCd`/`gugunCd`(행정 코드)

**상세 필드:** 위 항목 + `noticeBgnde`/`noticeEndde`(모집기간), `actBeginTm`/`actEndTm`, `actWkdy`(활동요일), `actPlace`, `rcritNmpr`(모집인원), `appTotal`(신청인원), `srvcClCode`(봉사분야), `adultPosblAt`/`yngbgsPosblAt`/`grpPosblAt`/`familyPosblAt`/`pbsvntPosblAt`(대상 가능 여부), `progrmCn`(본문), `areaAddress1~3`/`areaLalo1~3`(주소·좌표), `mnnstNm`, `nanmmbyNmAdmn`, 담당자 연락처

**확인된 데이터 문제**
- `progrmSttusSe`: **`2` = 모집중, `3` = 마감** (2026-10-14 1365 상세 페이지와 대조해 확인). 다른 값은 미확인이므로 "확인 필요"로 둔다.
- 상태 코드와 날짜가 서로 맞지 않을 수 있다. 모집기간이 남아도 기관이 먼저 마감하면 `3`이 되고(`3519585`: 모집 ~10/17인데 `3`), `2`여도 모집 종료일 당일 사이트에서 "모집기간이 아닙니다"가 뜬 사례가 있다(`3487369`). 그래서 **추천 대상 = `progrmSttusSe == 2` 이면서 오늘이 `noticeBgnde`~`noticeEndde` 안**으로 하고, 종료일 당일 공고는 "마감 임박·확인 필요"로 표시한다.
- 시니어 대상 판정은 `adultPosblAt`만 있고 연령 조건 필드는 없다. 본문(`progrmCn`)의 연령 표현은 F07 원칙대로 **추정하지 않고 "확인 필요"**로 둔다.
- 공식 신청 경로: `https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=<번호>` (브라우저로 확인). 모집기간이 아닌 공고는 안내 후 목록 페이지로 이동한다.

## 4. 서울50플러스 (`openapi.50plus.or.kr/openapi/service`)

요청은 `GET <경로>?_type=json&year=<연도>&pageNo=&numOfRows=&accessKey=<키>`, 응답은 JSON(`response.header.resultCode` `0000` = 정상)이다. 경로는 **API 매뉴얼 PDF(2025-10)** 기준이다. 웹페이지 설명의 `job/list`·`internship/list`는 404("No service was found")다.

| 데이터셋 | 경로 | 2026년 `totalCount` | 필드 |
|---|---|---|---|
| 가치동행 일자리(사회공헌) | `job1/list` | 99 | `bizYear`, `orgNm`(운영 기관), `bizNm`(사업명), `rcrtPpl`(모집 인원), `actamtHamt`(활동비 시급), `actperStartDe`/`actperEndDe`(활동기간), `appdurngStartDe`/`appdurngEndDe`(신청기간), `annApprvStatView`(공고 승인 상태) |
| 일자리(구 인턴십) | `job2/list` | 421 | 위와 같은 구조 + `bizSeNm`(사업 구분: 취업훈련·채용설명회·경력인재지원·시니어 특화), `annRcrtStatNm`(모집 상태) |
| 교육 | `education/list` | 2,686 | `lctNm`(강좌명), `lctCtt`(강좌 설명), `orgNm`, `crStartDe`/`crEndDe`, `regStartDe`/`regEndDe`(접수기간), `crPpl`, `lctCost`, `lctTypeView`(유료/무료·선착순/승인), `lctStatView`(모집 상태), `rpstLctr`(대표 강사명), `schdCnt` |

**확인된 데이터 문제**
- **공고 ID·공식 상세/신청 URL이 없다.** 계약의 `application_url`·`source_url`을 응답만으로 만들 수 없다. 중복 판정 키도 `(bizYear, orgNm, bizNm, 신청기간)` 같은 조합으로 만들어야 한다.
- **지역 필드가 없다.** `orgNm`(예: `성동센터`, `동부캠퍼스`)으로만 추정할 수 있다. 센터는 이름의 자치구, 캠퍼스는 소재지 확인이 필요하다.
- 가치동행 일자리의 `annApprvStatView`는 샘플 199건 모두 `승인완료`로 **모집 상태가 아니다**. 모집 여부는 신청기간으로 판단한다. 일자리는 `annRcrtStatNm`(`마감`, `신청·접수중`), 교육은 `lctStatView`(샘플에 `마감`, `폐강`)가 있다.
- 날짜는 매뉴얼의 `YYYYMMDD`가 아니라 실제로는 `YYYY-MM-DD`다. 일자리의 활동기간에는 `-`가 온다.
- 교육 `lctCtt`에 담당자 이름·전화가, `rpstLctr`에 강사 이름이 들어 있다(개인정보).
- 교육은 공고 계약의 `activity_type`(`employment`·`volunteering`)에 맞는 값이 없다. MVP에서 교육을 공고로 넣을지 팀 결정이 필요하다.

## 5. 개인정보 취급

두 API 모두 담당자 이름·전화·이메일·상세주소를 준다. 서비스 화면에는 공식 링크로 대신 안내하고, 수집 단계에서 이 필드를 저장할지는 #46(정규화)에서 최소 수집 기준으로 정한다. 원본 샘플(`worker/samples/`)은 `.gitignore`로 커밋을 막았다.

## 6. 남은 확인 사항

- [x] 서울50플러스 인증키 승인 → 세 데이터셋 2025·2026년 샘플 (§4)
- [ ] 서울50플러스 이용 조건: 회원 약관의 제3자 제공·상업적 사용 금지와 데이터 페이지의 "이용허락범위 제한 없음" 중 어느 것이 API 데이터에 적용되는지 재단에 서면 확인
- [ ] 서울50플러스 공고별 공식 안내 페이지 URL 형식 (응답에 없음)
- [ ] 서울50플러스 `orgNm` → 자치구 대응표 (캠퍼스 소재지)
- [x] 고용24·1365 공식 상세 URL을 브라우저로 확인
- [ ] `emplymShp`, `acptMthdCd`, `srvcClCode` 코드표 확보 (`progrmSttusSe`는 2·3만 확인)
- [ ] `getVltrPeriodList` 요청 변수 확인
- [ ] 노인 구인정보 목록의 검색 조건 지원 여부
