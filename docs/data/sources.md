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
| [서울50플러스 API](https://www.50plus.or.kr/apiIndex.do) | 사회공헌 일자리·중장년 일자리·교육 | **실제 호출 성공** (2026-10-17, 세 데이터셋) | 관리자 승인(2026-10-14 신청, 2026-10-17 발급 확인). 한도 미안내 | **이용 가능** (2026-10-29 재단 서면 회신): 인증키 승인으로 이용 승인 완료, 아래 조건이면 약관 제5조에 저촉되지 않음. 출처 표시 필수(§4) |

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
- 목록 검색 조건은 명세 표에 없지만 2026-10-28에 실제 호출로 확인했다. **새 공고는 `frDd`로 증분 수집**하고 지역·제목은 우리 쪽에서 거른다(#48, #49).

  | 요청 변수 | 결과 |
  |---|---|
  | `frDd=YYYYMMDD` | **동작.** 접수 시작일이 그 날짜 이상인 공고만 준다(`20261001` → 240건, `20261026` → 32건). 다른 형식(`202610`)은 오류 |
  | `emplymShp` | 동작. 값은 `CM0103`(137,742건)·`CM0105`(624,431건) 두 개뿐이고 합이 같은 날 전체 건수(762,173건)와 같다. 위 표의 762,038건은 10-14 측정값이다. `CM0101`·`CM0102`·`CM0104`·`CM0106`은 0건 |
  | `workPlcNm` | 값을 넣으면 0건(`서울`, `서울 용산구` 모두). 형식 미확인이라 쓰지 않는다 |
  | `toDd` | 제공기관 서버 오류(`resultCode` 99). **보내지 않는다** |
  | `recrtTitle`·`oranNm`·`workPlc`·`jobcls`·`stmId`·`keyword`·`deadline` | 무시됨(전체 건수 그대로) |

  `frDd`만으로는 부족한 점이 두 가지 있어 수집 계획(#48, #49)에 함께 넣는다.
  - **늦게 등록된 공고:** 접수 시작일이 실행일보다 앞선 날짜로 뒤늦게 올라온 공고는 그 창을 지나쳐 빠질 수 있다. `frDd`를 직전 성공 실행보다 며칠 앞당겨 겹치게 요청하고, 겹친 공고는 기존 버전 비교로 중복 저장하지 않는다.
  - **이미 받은 공고의 마감·변경:** 접수 시작일이 지난 공고는 다음 날부터 `frDd` 응답에 나오지 않는다. 기관이 일찍 마감하거나 내용을 고친 것을 알려면 저장된 열린 공고를 `getJobInfo(id=jobId)`로 다시 확인해야 한다([수명 규칙](ingestion-versions.md)). 열린 공고 수만큼 상세 호출이 들므로 개발계정 일 한도(10,000건) 안에서 주기를 정한다.

- 오류는 HTTP 200에 `resultCode` 99로 온다. 수집기는 HTTP 상태만 보지 말고 `resultCode`가 `00`인지 확인해야 하며, 오류 메시지(제공기관 DB 정보 포함)를 로그에 그대로 남기지 않는다.

## 3. 1365 봉사참여정보 (`apis.data.go.kr/1741000/volunteerPartcptnService`)

data.go.kr 페이지에는 오퍼레이션명이 없지만 기존 1365 API와 같은 이름으로 동작한다.

| 오퍼레이션 | 결과 |
|---|---|
| `getVltrSearchWordList` | 성공 (`totalCount` 11,215) |
| `getVltrAreaList` | 성공. `schSido=6110000`(서울)로 2,785건 |
| `getVltrCategoryList` | 성공 |
| `getVltrPeriodList` | HTTP 400. 2026-10-28에 `progrmBgnde`/`progrmEndde`·`schBgnde`/`schEndde`·`noticeBgnde`/`noticeEndde`·`bgnde`/`endde`(`YYYYMMDD`)를 넣어도 400. 지역·검색어 목록으로 충분해 더 찾지 않는다 |
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
- 포털의 공고 상세 경로는 2026-10-22에 확인했다: 가치동행일자리 `https://www.50plus.or.kr/appView.do?ANN_NO=<번호>`(예: `ANN_NO=1549`), 일자리(구 인턴십) `/in_appView.do?ANN_NO=<번호>`(2026-10-25 [공식 상세 페이지](https://www.50plus.or.kr/in_appView.do?ANN_NO=1271)에서 쿼리 키까지 확인). `/detail.do?id=`·`/life/detail.do?id=`는 공고가 아닌 안내 게시글이다. API 응답에 `ANN_NO`가 없어 응답과 상세 페이지를 자동으로 잇지는 못한다.
- **포털 목록에는 `ANN_NO`가 있다**(2026-10-28 확인). 가치동행일자리 목록 화면이 부르는 `POST /appListAjax.do`(`pageIndex`)가 `ANN_NO`·`ANN_NM`(공고명)·`OPER_ORG_NM`(운영 기관)·`APPDURNG_STED`(신청기간)·`ANN_RCRT_STAT_NM`(모집 상태)을 JSON으로 준다. 공개 API가 아니라 화면용 내부 경로이므로 수집기에 넣지 않고, 운영자가 대조할 때만 참고한다. 일자리 목록(`/in_appListAjax`)은 같은 날 0건이었다.
- API `job1/list` 2026년 99건을 포털 99건과 대조하면 **포털 공고 하나에 사업 여러 개가 묶인 경우가 많다**(예: "남부권 학교안전 2차 공동모집"). 사업명으로 한 건이 특정되는 것은 26건, 기관+신청 시작일로 특정되는 것은 17건, 나머지 56건은 후보가 여럿이다. 자동 연결은 하지 않고 운영자가 대조한다.
- **이용 조건 (2026-10-29 재단 오픈API 담당자 서면 회신).** 인증키 발급 승인으로 공공데이터 이용 승인이 끝났고 별도 사전 승낙은 필요 없다. 약관 제5조는 API 데이터 자체를 제3자에게 넘기거나 상업적으로 쓰는 것을 막는 조항이며, 아래 방식은 저촉되지 않는다고 확인받았다.
  - 허용으로 확인된 방식: 공고 정보(사업명·운영 기관·모집/활동 기간·활동비) 화면 표시, 이용자 조건에 맞는 추천 목록, 신청은 대신하지 않고 포털 공식 공고 페이지로 연결, 무료·비영리 운영
  - **지켜야 할 것:** 화면에 "출처: 서울시50플러스재단"을 표시한다(필수). 원본 정보를 임의로 수정·변형하지 않고 그대로 보여 주는 것을 권장한다. 유료화·상업적 이용으로 바뀌면 재단과 사전에 협의한다.
  - 데이터 원본(API 응답)을 그대로 내려받게 하거나 다른 서비스에 넘기는 기능은 만들지 않는다.
- 2026-10-27 기준 포털의 가치동행일자리 99건은 모두 마감, 일자리 목록은 0건이다. 현재 신청 가능한 50플러스 공고가 없다(#51).
- **지역 필드가 없다.** `orgNm`(예: `성동센터`, `동부캠퍼스`)으로만 추정할 수 있다. 센터는 이름의 자치구, 캠퍼스는 소재지 확인이 필요하다.
- `orgNm` → 운영 기관 소재지 (2026-10-28 [위치 안내](https://www.50plus.or.kr/location_information.do)의 공식 주소로 확인)

  | `orgNm` | 소재 자치구 |
  |---|---|
  | `<자치구>50플러스센터` (강동·강북·강서·관악·금천·노원·동작·서대문·서초·성동·성북·양천 등) | 이름의 자치구. 위 12곳은 주소로 확인 |
  | 중부캠퍼스 | 마포구 |
  | 서부캠퍼스 | 은평구 |
  | 남부캠퍼스 | 구로구 |
  | 북부캠퍼스 | **도봉구**(창동) |
  | 동부캠퍼스 | 광진구 |
  | 외부 기관(예: `(사)한국치매협회`) | 대응 없음 |

  이 표는 **운영 기관의 소재지이지 활동 장소가 아니다.** 사업명에 다른 자치구가 나오거나(예: "지역복지사업단-금천,구로") 권역 단위로 모집하는 경우가 있어, `activity_region`으로 자동 확정하지 않고 검수에서 공고 원문으로 정한다.
- 가치동행 일자리의 `annApprvStatView`는 샘플 199건 모두 `승인완료`로 **모집 상태가 아니다**. 모집 여부는 신청기간으로 판단한다. 일자리는 `annRcrtStatNm`(`마감`, `신청·접수중`), 교육은 `lctStatView`(샘플에 `마감`, `폐강`)가 있다.
- 날짜는 매뉴얼의 `YYYYMMDD`가 아니라 실제로는 `YYYY-MM-DD`다. 일자리의 활동기간에는 `-`가 온다.
- 교육 `lctCtt`에 담당자 이름·전화가, `rpstLctr`에 강사 이름이 들어 있다(개인정보).
- 교육은 공고 계약의 `activity_type`(`employment`·`volunteering`)에 맞는 값이 없다. MVP에서 교육을 공고로 넣을지 팀 결정이 필요하다.

## 5. 개인정보 취급

두 API 모두 담당자 이름·전화·이메일·상세주소를 준다. 서비스 화면에는 공식 링크로 대신 안내하고, 수집 단계에서 이 필드를 저장할지는 #46(정규화)에서 최소 수집 기준으로 정한다. 원본 샘플(`worker/samples/`)은 `.gitignore`로 커밋을 막았다.

## 6. 남은 확인 사항

- [x] 서울50플러스 인증키 승인 → 세 데이터셋 2025·2026년 샘플 (§4)
- [x] 서울50플러스 이용 조건: 2026-10-29 재단 서면 회신으로 이용 가능 확인. 출처 표시 필수, 원본 그대로 표시 권장, 유료화 시 사전 협의 (§4)
- [x] 서울50플러스 공고 상세 URL 형식: `/appView.do?ANN_NO=`, `/in_appView.do?ANN_NO=` (§4)
- [x] API 응답 항목과 포털 `ANN_NO`를 잇는 방법: 자동 연결 불가, 운영자가 포털 목록과 대조 (§4, 사업 여러 개가 공고 하나에 묶임)
- [x] 서울50플러스 `orgNm` → 자치구 대응표: 운영 기관 소재지만 (§4). 활동 지역은 검수에서 정함
- [x] 고용24·1365 공식 상세 URL을 브라우저로 확인
- [ ] `emplymShp`, `acptMthdCd`, `srvcClCode` 코드표 확보 (`progrmSttusSe`는 2·3만 확인. `emplymShp`는 `CM0103`·`CM0105` 두 값만 존재, 이름은 미확인)
- [x] `getVltrPeriodList` 요청 변수 확인: 네 가지 기간 변수 모두 400. 필요 없어 중단 (§3)
- [x] 노인 구인정보 목록의 검색 조건 지원 여부: `frDd`·`emplymShp`만 동작 (§2)
