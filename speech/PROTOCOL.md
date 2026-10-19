# 내부 음성 전송 계약 (#33의 백엔드 경계)

이 문서는 백엔드 InternalSpeechAdapter와 별도 모델 서비스 사이의 계약이다. [프로세스 서비스](PROCESS_RUNTIME.md)에서 실제 CPU STT/TTS 적재·ASGI/TCP 전사/합성·Redis 슬롯·연결 해제와 종료를 확인했다. Compose 연결·운영 컨테이너·대상 기기/사용자 음성·발화 품질 검증은 남아 있으며, 전송 대역 시험을 실제 STT/TTS 성공으로 계산하지 않는다. readiness는 살아 있는 프로세스에서 두 모델이 준비된 경우에만 성공한다. 공개 /speech·전사 API는 연결됐다.

주소는 코드의 `http://speech:8001`로 고정한다. 사용자 URL·모델·화자·파일 경로를 받지 않는다. 프록시 환경변수와 리다이렉트는 사용하지 않고 재시도·외부 모델 대체·파일 저장을 하지 않는다. 후속 서비스는 내부 네트워크에만 두고 호스트 포트/Nginx 공개 없이 tmpfs·읽기 전용 모델·메모리/프로세스 제한을 적용해야 한다. 서비스 배치가 아직 없으므로 현재 전송 구현만으로 컨테이너 격리를 검증했다고 주장하지 않는다.

GET /health/ready는 200 application/json과 정확한 `{protocol_version:1,status:"ready",stt:true,tts:true}` 객체를 반환한다. 두 모델 적재/요청 준비를 실제 확인한 경우만 ready다. 확인 제한2초·응답4KiB이며 추론 예산을 소비하지 않는다. 백엔드 readiness는 공통 Redis 제어 상태도 확인한다.

POST /internal/transcriptions는 녹음 원문 bytes를 body로 받는다. Content-Type은 audio/wav·audio/webm·audio/ogg·audio/mp4 중 하나이고 X-Speech-Request-ID는 백엔드 발급 UUID다. 백엔드는6MiB와 시그니처를 검사하고 WAV는16kHz·16bit·mono PCM/실재 프레임/최대90초를 검증한다. 압축 음성의 실제 codec·길이·무음·비디오 포함 여부/디코더 자원 제한은 #31의 내부 서비스가 추론 전에 검증해야 한다. 시그니처 통과가 압축 디코드 성공을 의미하지 않는다.

정상 전사 응답은200 application/json의 `{text, duration_seconds}`만 담는다. 추가 필드·빈 전사·2000자 초과/숨은 문자·0초 이하/90초 초과·잘린 JSON은 거절한다. STT 원문을 프로필 추출에 자동 전달하지 않는다. 사용자가 확인/수정한 텍스트의 messages 연결은 #38의 책임이다.

내부 디코더가 입력을 거절할 때는 현재 요청의 종료 헤더와422 JSON `{code:"AUDIO_TOO_LONG"}` 또는 `{code:"AUDIO_INVALID"}`만 반환할 수 있다. 백엔드는 이 두 고정 코드만 공개 audio 필드 오류로 바꾸며 나머지 서비스 오류 본문은 내보내지 않는다. 이 매핑은 실제 디코더를 실행/검증한 증거가 아니다.

POST /internal/speech는 `{text}`만 받는다. 호출자는 서버에서 소유권·표시 버전·AI 동의를 검사한 최대2000자 표시 문장을 전달해야 하며 일반 사용자 자유 문장을 그대로 전달하는 공개 API를 만들면 안 된다. 고정 한국어 화자는 내부 모델 적재 단계 #32에서 정한다. 사용자 화자/복제/참조 음성 URL은 이 계약에 없다. 응답은200 audio/wav, mono16bit PCM,8~48kHz, 최대16MiB다. 백엔드는 실재 프레임을 검사하고 PCM만 새 WAV로 조립해 JUNK 등 비음성 메타데이터를 제거한다. 이 범위는 전송 상한이고 실제 모델의 sample rate/발화 품질을 실측한 값은 아니다.

모든 추론 응답은 해당 연산/버퍼 정리가 **실제로 끝난 뒤** 같은 X-Speech-Request-ID와 X-Speech-Completed:1을 반환해야 한다. 다른 요청 ID·미완료·헤더 누락·잘린/과대 body는 종료 증거가 아니다. 백엔드는 제한 안의 body를 끝까지 읽고 현재 ID의 종료 헤더를 확인해야 Redis 슬롯 해제를 허용한다. 그 뒤 출력 검증이 실패하더라도 실제 연산 종료 증거는 유지한다. 시간 초과/연결 취소/응답 유실은 종료 확인이 아니어서 슬롯을 유지한다. 연결 장애만으로도 종료를 확인하지 못하면 운영자의 런타임 정지/배출 확인 후 제어 복구가 필요할 수 있다. 오류 본문/오디오/전사 원문은 예외나 로그로 노출하지 않는다.

ControlledSpeechAdapter는 주체 없는 호출을 거절하고 LLM과 같은 AdmissionService의 stt/tts 종류로 요청한다. STT는 생성 예산, TTS는 기존 TTS 주체/IP 예산과 전역 한도를 쓰며 전역 실행 슬롯을 공유한다. 전송 timeout은60초 이내다. 업무 라우터의 동의/소유권/HTTP 제한은 이 adapter를 호출하기 전에 별도로 연결해야 한다.

일시 오류를 반환하려면 실제 종료 헤더와 503 application/json의 정확한 `{code:"RUNTIME_TEMPORARILY_UNAVAILABLE"}`를 함께 보내야 한다. 추가 필드·다른 코드·다른 media type·현재 ID가 아닌 종료는 자동 재시도 근거가 아니다. 이 응답도 내부 작업/버퍼가 정리된 뒤에만 보낼 수 있다. ControlledSpeechAdapter가 동일 예산/lease의 전체 60초 안에서 한 번 재시도한다. 직접 전송 어댑터는 재시도하지 않는다. 연결 미성립(HTTPX ConnectError/ConnectTimeout)도 요청이 시작되지 않은 경우로 분류한다. 응답 읽기/쓰기 실패·전체 시간 초과·임의 503/429는 이 분류에 포함하지 않는다. 상세는 [재시도 경계](../docs/ai/retry-boundaries.md)를 따른다.

백엔드 전송 경계 도입 당시 추가34건 포함 실제 PostgreSQL/Redis 전체978건/0skip을 통과했다. 이때 음성 서비스와 모델은 대역이었다. 고정 목적지/현재 요청 종료 신호·WAV 메타데이터 제거·readiness·크기/시간·형태/숨은 문자·출력 실패·프록시/redirect/압축 응답 거절·timeout/cancel·공유 슬롯을 검증했다. 큰 가상 오디오를 pytest ID에 넣어 Windows 준비 오류가 난 첫 실행은 짧은 ID로 수정 후 다시 통과했다. 이후 실제 decoder·모델·TCP·Redis 연결은 [STT](STT_RUNTIME.md)와 [프로세스 서비스](PROCESS_RUNTIME.md)의 별도 증거를 따른다. 이들 결과로 EC2/GPU·컨테이너/tmpfs·기기나 발화 품질 통과를 주장하지 않는다.
