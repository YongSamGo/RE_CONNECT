# #35 모델 장애·재시도 경계

2026-10-18 백엔드에서 명시적인 일시 오류에 한해 자동 재시도를 최대 한 번 구현했다. 실제 런타임의 일시 오류 구현·EC2 지연·모델 품질·전체 기기 여정은 별도 검증이 남아 있어 #35 전체 통과로 표시하지 않는다.

하나의 `AdmissionService.run`이 단일 acquire와 전체 60초 제한을 제공한다. `ControlledLLMAdapter`와 `ControlledSpeechAdapter`가 `retry_once`를 사용한다. 각 시도의 독립적인 `RuntimeCompletion` 가운데 최신 시도가 종료 또는 연결 미성립을 확인한 경우만 외부 완료를 확인해 release한다. API 오류 변환과 수동 입력/편집/공개 탐색은 기존 연결을 사용한다.

첫 시도의 종료 상태나 늦은 callback은 두 번째 시도의 종료를 확인할 수 없다. 직접 전송 어댑터는 한 번만 호출하고 제어 어댑터에서만 재시도한다. 공개 요청의 멱등 키를 유지하며 내부 음성 시도는 각각 새 request ID를 사용한다.

| 관측 | 자동 재시도 판단 | 슬롯 처리 |
|---|---|---|
| HTTPX ConnectError/ConnectTimeout: 연결 자체가 미성립해 요청 미전송 | 최대 1회 | 같은 lease/예산 유지, 최종 시도도 연결 미성립이면 해제 |
| 내부 음성 응답의 일치 request ID + completed=1 + 제한 내 전체 본문 + 503 JSON의 정확한 일시 오류 코드 | 최대 1회 | 같은 lease/예산 안에서 다음 시도의 독립적인 종료 상태 사용 |
| 타임아웃·연결 단절·종료 헤더 미확인·본문 초과/중단 | 종료를 증명하지 못해 재시도 금지 | 유지 |
| 유효한 종료 뒤 입력 오류·검증 불가능한 출력 | 일시 오류와 구분, 즉시 재시도 금지 | 확인된 해당 시도 종료에 한해 해제 |
| Ollama의 일반 non-200 오류 | 현재 어댑터는 실제 종료를 확인하지 못하므로 재시도 금지 | 유지 |
| HTTP 429/공유 슬롯 혼잡 | 모델 호출 전 차단이며 자동 모델 재호출과 구분 | 기존 실행 슬롯을 해제하지 않음 |

음성의 명시적 일시 오류는 [프로토콜](../../speech/PROTOCOL.md)의 `RUNTIME_TEMPORARILY_UNAVAILABLE`만 허용한다. 일반 Unavailable·일반 503·응답 읽기/쓰기 실패는 재시도하지 않는다. 연결 미성립 분류는 설치된 HTTPX 예외 정의의 “Failed to establish a connection”·“Timed out while connecting to the host” 의미에 따른다. ReadError/ReadTimeout과 구분하며 Ollama 종료 증거 없는 오류를 음성 프로토콜로 추정하지 않는다.

실제 Redis/PostgreSQL 전체 1,047개 시험(건너뜀 없음)이 통과했다. 신규 22개 시험은 예산 1회, 별도 request ID, 최대 2회, 최신 시도 취소/시간 초과 때 lease 유지, 이전 시도의 늦은 callback 격리, 일반 503 및 잘못된 출력의 재시도 금지를 확인한다. 전체 제한은 한 admission 실행의 `asyncio.wait_for`가 적용하며 시험은 짧은 제한값을 주입했다. HTTP 전송과 모델은 대역이다. 문장/오디오/사용자 식별값을 로그에 담지 않고 외부 AI 전환도 추가하지 않는다.
