# 내부 음성 HTTP와 모델 프로세스 (#33 진행)

`app.main:app`은 ASGI 진입점이고 `app/service.py`가 내부 HTTP를 처리한다. `ProcessRuntime`은 `spawn`으로 모델 프로세스 하나를 만들고 STT·TTS를 그 안에 적재한다. 네이티브 디코딩/추론과 IPC 대기를 FastAPI event loop에서 실행하지 않는다. 한 worker·한 공통 잠금으로 STT/TTS 동시 실행을 거절하며 공개 백엔드의 Redis 공통 LLM/STT/TTS 슬롯도 계속 필요하다. uvicorn은 반드시 `--workers 1`로 실행한다.

## 준비·로컬 실행

먼저 [모델](MODEL_PREPARATION.md)과 [고정 TTS source](tts_compat/README.md)를 준비한다. Python3.12의 새 격리 환경에서 저장소 루트 기준으로 설치한다.

```sh
python -m pip install --require-hashes -r speech/requirements.txt -r speech/requirements-dev.txt -r speech/tts_compat/requirements.txt -r speech/tts_compat/requirements-dev.txt
cd speech
python -B -m pytest -q
python -B -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 --no-access-log
```

이 명령은 로컬 검증용 loopback 서비스다. 운영 배치의 내부 네트워크·호스트 포트 미공개·읽기 전용 source/모델·tmpfs·CPU/메모리/프로세스 제한은 별도로 연결해야 한다. 현재 문서나 CPU 실행으로 컨테이너 격리를 입증하지 않는다. 기본 STT 잠금만 설치해도 STT 로더 단독 시험은 가능하지만 전체 서비스에는 TTS 잠금도 필요하다.

시작 시 두 로더가 각각 고정 파일의 크기/해시를 오프라인 검증한다. 한쪽만 성공하면 readiness는503이다. 둘 다 적재되고 프로세스가 살아 있을 때만200과 `{protocol_version:1,status:"ready",stt:true,tts:true}`를 반환한다. readiness는 적재/생존 상태이며 발화 품질 통과 판정은 아니다. 시작 확인 제한은120초다. 실패/취소로 worker를 정지하면 readiness는 실패 상태로 유지하고 서비스 재시작 때만 재적재한다. 요청 중 다운로드나 자동 모델 대체는 없다.

## 입력·완료와 실패

- `/internal/transcriptions`는 UUID 요청 ID와 허용 Content-Type의 원문 binary를 받는다. stream 수신10초/6MiB 제한 뒤 실제 디코더가 형식·90초·무음을 검사한다.
- `/internal/speech`는 UUID와 `application/json`의 정확한 `{text}`만 받는다.32KiB 제한은2000자의 JSON surrogate escape도 수용한다. 중복 키·추가 필드·잘린 JSON·압축 body·숨은 문자·모델 대화 토큰을 거절한다. 화자/언어/지시/참조 URL을 받지 않는다.
- 몸체 수신을 포함한55초 예산 안에서 최대50초의 모델 작업과 프로세스 종료/IPC 배출용5초를 배정한다. body 수신에 사용한 시간만큼 모델 예산을 줄인다. event loop는 모델 작업 중에도 readiness/혼잡 응답을 처리한다.
- IPC는 크기를 제한한 JSON/bytes이며 `Connection.recv()`의 pickle 역직렬화를 사용하지 않는다. 자식은 결과를 전송한 뒤 요청/출력 참조와 mutable 음성 버퍼를 비우고 별도 완료 ACK를 보낸다. 부모는 결과 전체와 ACK를 모두 확인해야 현재 ID의 `Completed:1`을 반환한다. WAV 전송 버퍼도 ASGI send 완료/연결 취소 뒤0으로 채운다.
- 시간 초과/HTTP task 취소/IPC 오류는 소유한 자식 프로세스만 terminate·join하고 필요하면 kill·join한다. 실제 TCP 연결 해제가 endpoint task를 자동 취소한다고 가정하지 않고, body 수신 뒤 `http.disconnect`도 별도로 감시한다. 실제 사망과 부모 IPC thread 종료를 확인한 뒤에만 잠금을 해제한다. 종료가 불명확하면 완료 헤더를 보내지 않고 잠금을 유지한다. 그 상태를 readiness 성공으로 바꾸지 않는다. Python/네이티브 라이브러리의 immutable 임시 복사본까지 완전히 소거한다고 주장하지 않는다.

HTTP 연결이 이미 사라지면 백엔드가 완료 헤더를 받을 수 없으므로 Redis lease를 자동 해제할 증거도 없다. [내부 전송 계약](PROTOCOL.md)의 보수적 복구 정책은 유지한다. 모델 실패/시간 초과는 `RUNTIME_UNAVAILABLE`이며 자동 재시도 대상으로 가장하지 않는다. 자체 요청의 연산을 시작하지 않은 미준비/혼잡만 `RUNTIME_TEMPORARILY_UNAVAILABLE`로 반환한다.

## 확인한 범위

Linux/Python3.12에서 기본 시험38개를 통과했다. 실제 spawn 프로세스의 정상 STT/TTS·공통 혼잡·event loop 응답·시간 초과·요청 취소·자식 비정상 사망·SIGTERM 무시 후 SIGKILL·종료 ACK 누락·미확인 종료 시 헤더/잠금 유지·WAV 전송 실패 정리를 검사한다. 모델은 시험 대역이다. 직접 ASGI disconnect 통지와 실제 loopback TCP client만 취소하는 회귀 시험도 포함한다. Windows에서도37개가 통과했고 POSIX 전용 SIGKILL 시험1개만 제외했다. 실제 모델 호환/로더 시험35개는 별도다.

같은 Linux 환경의 실제 CPU 모델로 ASGI 호출도 수행했다. 두 모델 적재27.481초 후 readiness200, 고정 Sohee 인사 WAV는24kHz/mono/16bit·3.6초이며 호출10.486초였다. 공개 합성 녹음4.07초의 STT 호출1.503초가 “저는 도서관에서 책을 정리하는 일을 했습니다.”로 전사됐다. 둘 다 현재 요청 ID/완료 헤더를 반환했고 호출 후 준비 상태와 shutdown 뒤 자식 사망을 확인했다.

## 실제 TCP·백엔드·Redis 연결 확인

Windows의 실제 `InternalSpeechAdapter`를 WSL loopback uvicorn과 연결했다. 제품의 고정 origin `http://speech:8001`은 유지하고, 시험 전용 transport에서 그 정확한 origin만 `127.0.0.1:18001`의 실제 TCP로 보냈다. MockTransport/ASGITransport 응답을 사용하지 않았다. 이 시험은 Compose DNS/내부 네트워크 격리 증거가 아니다.

readiness와 실제 전사/합성 POST7건의 전체 응답을 백엔드가 받아 검증했다. 모두 현재 ID의 종료 헤더와 실제 완료 callback을 확인했고 WAV는 백엔드의 PCM 재조립 검사도 통과했다. 공개 합성 녹음 전사는1.703초였다. TTS 인사/공고 숫자/두 줄 안내의 각각 합성 호출은5.860/7.938/12.687초였다. 별도 [발화 비교](TTS_RUNTIME.md)의 실패 기록을 품질 통과로 바꾸지 않는다.

새 비영속 Redis와 실제 `ControlledSpeechAdapter`도 함께 연결했다. 실제 TTS 실행의 Redis 슬롯이 유지되는 동안 다른 STT와 LLM 실행 시도는 각각 `INFERENCE_BUSY`로 거절됐다. LLM 모델 자체는 실행하지 않았다. 실제 TTS와 STT가 완료된 뒤 각각 슬롯이 해제됐고 일일 집계는 각1회, 합계2회였다.

이후 긴 공개 문장 TTS가 내부 잠금을 가진 것을 확인하고 실제 TCP client 요청을 취소했다. endpoint task에 직접 cancel을 주지 않았다. 모델 자식 PID/시작 시각을 관찰해 실제 사망을 확인했고 readiness도503이었다. 반면 완료 헤더를 받지 못한 백엔드 Redis lease는 그대로 유지됐다. 이 상태를 임의로 복구하지 않았다. 시험 뒤 비영속 Redis를 종료했고, uvicorn 정상 종료와 남은 소유 자식 PID 없음도 확인했다.

실제 연결 시험에는 공개 가상 문장과 합성 녹음만 사용했다. 이후 [CPU 컨테이너 검증](CONTAINER_RUNTIME.md)에서 origin 재작성 없이 Compose 내부 DNS 연결과 커널 자원 제한을 확인했다. EC2/GPU·기기/브라우저 재생 검증은 남아 있다.

[숫자 문장 재전사 불일치](TTS_RUNTIME.md)는 남아 있고 사람 청취 평가를 대신하지 않는다. 운영 동의 정보도 미정이므로 실제 시작은 계속 비활성이다. #31/#32/#33 전체 완료나 배포 검증으로 처리하지 않는다.
