# 고정 공공 API의 안전한 수집·파싱 (W06-02 · #45)

[수집 모듈](../../backend/app/modules/ingestion/fetch.py)은 [기존 출처 조사](sources.md)에서 확인한 노인 구인정보와 1365 API의 목록·상세만 호출한다. URL·임의 오퍼레이션·헤더를 웹 사용자에게 받지 않는다. 서울50플러스나 새 출처는 별도 검토 후 추가한다.

## 호출 계약

운영자/스케줄러가 `FetchRequest`와 환경의 인증키를 `SecretStr`로 전달한다. 이 모듈은 `.env`를 직접 읽지 않고, 앱 시작 시 자동 수집하지 않는다.

```python
from pydantic import SecretStr
from app.modules.ingestion.fetch import FetchRequest, FetchStatus, fetch

result = await fetch(
    FetchRequest(operation="senuri_list", page_no=1, num_rows=10),
    SecretStr(service_key),  # 운영 환경이 주입한 값. 출력하지 않는다.
)
if result.status == FetchStatus.OK:
    # document는 여전히 비신뢰 외부 원문이다. #46 정규화 전에 저장/공개하지 않는다.
    document = result.document
```

| 오퍼레이션 | 고정 경로 (`https://apis.data.go.kr`) | 추가 값 |
| --- | --- | --- |
| `senuri_list` | `/B552474/SenuriService/getJobList` | 페이지/행 수 |
| `senuri_detail` | `/B552474/SenuriService/getJobInfo` | `external_id` → `id` |
| `volunteer_list` | `/1741000/volunteerPartcptnService/getVltrSearchWordList` | 페이지/행 수 |
| `volunteer_detail` | `/1741000/volunteerPartcptnService/getVltrPartcptnItem` | `external_id` → `progrmRegistNo` |

페이지 1~100,000, 행 수 1~100, 상세 ID 영문·숫자·밑줄·하이픈 1~64자를 허용한다. 키는 최대 512자이며 제어 문자를 거절한다. 키 값이 URL에 포함되는 공공 API이므로 URL·예외·원문을 로깅하거나 HTTP 추적 로깅을 켜지 않는다.

## 네트워크 경계

- HTTPS와 443만 사용한다. 모든 3xx를 거절해 인증키를 다른 목적지로 전달하지 않는다.
- DNS가 반환한 **모든 주소**를 확인한다. 하나라도 사설·루프백·link-local·멀티캐스트·예약·IPv6 전환 주소이면 거절한다.
- 검증한 숫자 IP로 직접 연결해 원래 호스트를 다시 DNS 조회하지 않는다. TLS SNI·인증서 검증과 HTTP Host는 원래 `apis.data.go.kr`를 유지한다. 공개 IP의 잘못된 인증서도 거절한다.
- HTTPcore의 공개 [network backend API](https://www.encode.io/httpcore/network-backends/)로 구현했다. proxy 환경변수·쿠키·사용자 인증 설정을 상속하지 않는다. 자동 재시도·keep-alive 재사용은 없다.
- DNS/개별 I/O 5초, 비동기 네트워크 단계 전체 20초 제한이다. 호출자가 취소하면 취소를 전파하고 소유 연결을 닫는다. 운영 네트워크의 egress 제한을 대체하는 것은 아니다.

## 본문·XML 경계

- XML Content-Type만 허용한다. 압축 응답을 거절하고 자동 압축 해제를 하지 않는다.
- Content-Length와 실제 수신 모두 2MiB까지만 허용한다. 길이 초과·잘린 HTTP·중복 헤더는 성공 처리하지 않는다.
- [defusedxml](https://pypi.org/project/defusedxml/0.7.1/)의 `forbid_dtd/entities/external=True`를 사용한다. UTF-8/UTF-16/UTF-16BE의 DTD·외부 엔티티·내부 확장도 거절한다. XInclude 확장·XSLT·외부 문서 조회를 호출하지 않는다.
- 트리를 만들면서 깊이 32, 요소 20,000개, 요소당 속성 32개, 태그 이름 256자, 텍스트 65,536자 상한을 검사한다. 파싱은 수신 상한 안에서 동기 실행하며 비동기 시간 제한이 CPU 연산을 강제 중단한다고 주장하지 않는다.
- 공공 API의 `response/header/resultCode` 성공 코드 `00`/`0`과 `body/items`, `totalCount`를 검사한다. HTTP 200의 인증/한도 오류를 빈 공고로 성공 처리하지 않는다. 계약이 다른 응답은 거절하고 실제 표본으로 확인한 후 명시적으로 지원한다.

파싱한 Element 값은 전부 비신뢰 데이터다. HTML·URL·LLM 지시문처럼 보이는 내용도 실행하지 않는다. 원문과 담당자 개인정보를 저장·정규화·공개하는 작업은 포함하지 않는다. 결과의 기본 repr에도 본문을 넣지 않는다.

## 검증과 남은 작업

2026-10-20 Windows의 새 해시 잠금 환경에서 백엔드 전체 304개 시험을 통과했다. 새 73개 시험은 정상 문서·고정 경로·숫자 IP 연결과 원래 TLS 호스트, 사설/혼합 DNS·리다이렉트·과대·느린 응답·취소·잘린 응답·XXE·오류 본문 비노출을 확인한다.

실제 두 API에 시험용 비인증 값으로 연결해 TLS/HTTPS 요청 후 403을 `http_error`로 반환하고 문서가 없음을 확인했다. 실제 인증키를 읽거나 개인 공고 원문을 저장하지 않았다. **유효 키의 정상 목록·상세 수집은 미검증**이며, 이 기록으로 전체 이슈 통과를 선언하지 않는다.

후속 연결: #44의 실제 출처 설정/표본 확인, #46의 정규화, #47의 저장, #49의 실행 잠금·실패 상태·마지막 성공 시각. 기존 출처 조사 도구는 연구용으로 보존하며 운영 수집기가 대신 사용하지 않는다.
