# 공고 출처 조사 (W01-05)

> 기준일: 2026-10-14 · 담당: B(AI·데이터) · 관련 이슈: #8 → 후속 #44(출처 설정과 실제 필드 매핑)
>
> 샘플 수집: `python worker/tools/fetch_source_samples.py <source> --operation <op>` (키는 `.env`, 원본 응답은 커밋하지 않는 `worker/samples/`에 저장)

## 1. 출처별 접근 상태

| 출처 | 분류 | 접근 상태 | 승인 방식·한도 | 이용 조건 |
|---|---|---|---|---|
| [한국노인인력개발원 노인 구인정보](https://www.data.go.kr/data/15015153/openapi.do) | 취업·공공일자리 | **실제 호출 성공** (목록·상세) | 개발·운영 모두 자동승인, 개발계정 일 10,000건 | 이용허락범위 제한 없음 |
| [행정안전부 봉사참여정보서비스_GW (1365)](https://www.data.go.kr/data/15157582/openapi.do) | 봉사 | **실제 호출 성공** (목록·지역 필터·상세) | 개발 자동승인 / 운영 심의승인, 개발계정 1,000건 | 이용허락범위 제한 없음 |
| [서울50플러스 API](https://www.50plus.or.kr/apiIndex.do) | 교육·사회참여 일자리·인턴십 | **승인 대기** (2026-10-14 신청) | 관리자 승인, 소요기간 미안내 | 약관(`/fpp/terms.do`) 확인 필요. 미승인 시 같은 데이터의 CSV를 수동 자료 경로로 사용 |

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
- 샘플 공고 대부분의 원 시스템이 `워크넷`(고용24)이다. 공식 접수 경로는 고용24 상세 페이지가 유력하지만 **URL 형식은 아직 확인하지 못했다**(curl로는 JS 렌더링 페이지라 내용 확인 불가, 브라우저 확인 필요).
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
- `progrmSttusSe` 코드의 의미(모집중/마감 등)가 응답에 없다. 공식 코드표를 확인하기 전에는 모집 중 판정에 `noticeEndde`(모집 종료일)를 함께 쓴다.
- 시니어 대상 판정은 `adultPosblAt`만 있고 연령 조건 필드는 없다. 본문(`progrmCn`)의 연령 표현은 F07 원칙대로 **추정하지 않고 "확인 필요"**로 둔다.
- 공식 신청 경로는 `https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=<번호>` 형식이 HTTP 200을 반환하지만 공고 내용 표시 여부는 **브라우저 확인 필요**.

## 4. 개인정보 취급

두 API 모두 담당자 이름·전화·이메일·상세주소를 준다. 서비스 화면에는 공식 링크로 대신 안내하고, 수집 단계에서 이 필드를 저장할지는 #46(정규화)에서 최소 수집 기준으로 정한다. 원본 샘플(`worker/samples/`)은 `.gitignore`로 커밋을 막았다.

## 5. 남은 확인 사항

- [ ] 서울50플러스 인증키 승인 → 교육·가치동행 일자리 샘플 (미승인 시 CSV 경로)
- [ ] 고용24·1365 공식 상세 URL을 브라우저로 확인
- [ ] `progrmSttusSe`, `emplymShp`, `acptMthdCd`, `srvcClCode` 코드표 확보
- [ ] `getVltrPeriodList` 요청 변수 확인
- [ ] 노인 구인정보 목록의 검색 조건 지원 여부
