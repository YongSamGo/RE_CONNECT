# 전사 확인·수정 경계 (#38)

POST /journeys/{id}/transcriptions는 실제 세션/CSRF/HTTP 제한 뒤 유효한 자기 체험과 현재 AI 동의를 검사한다. multipart audio 하나만 메모리에서 받으며 Python/Starlette 폼 업로드의 디스크 spool을 사용하지 않는다. 파일명·경로는 사용/저장/반환하지 않는다. [RFC7578](https://www.rfc-editor.org/rfc/rfc7578.html)의 part 경계/이름/파일명 규칙을 참고해 이 API가 받는 형식을 좁혔고, [Python BytesHeaderParser](https://docs.python.org/3.12/library/email.parser.html)로 제한된 헤더만 해석한다. 일반 multipart 호환 파서를 구현한 것은 아니다.

한 audio part·명시 MIME·길이70 이하 ASCII boundary·part 헤더4KiB를 허용한다. 추가/중복 part·필드/헤더/매개변수·헤더 접기·transfer encoding·확장 filename*·preamble/epilogue·잘린 경계는 거절한다. 음성6MiB 초과는413, 형식/시그니처 오류는422 audio/invalid_value,16kHz/16bit/mono WAV90초 초과는422 audio/out_of_range다. Content-Type만으로 유효 음성을 판정하지 않는다. WAV는 실제 프레임을 검사한다. 압축 WebM/Ogg/MP4의 codec·길이·무음·디코더 자원 검증은 내부 모델 서버 #31의 구현/실측이 남아 있다. 서비스가 준비되지 않으면503이며 가상 전사로 대체하지 않는다.

내부 음성 호출은 서버 InferenceIdentity의 ControlledSpeechAdapter로 STT 생성 예산/LLM 공통 슬롯을 사용한다.60초 제한·입력 해시·UUID 생성 키를 사용하고 원본 음성/파일명은 Redis에 전달하지 않는다. 종료가 확인되지 않은 timeout/cancel은 실행 슬롯을 임의 반환하지 않는다. 내부 디코더의 현재 요청 완료가 확인된 고정 AUDIO_TOO_LONG/AUDIO_INVALID 오류만 공개 audio 필드 오류로 매핑한다. 임의 모델 오류 본문을 노출하지 않는다.

RedisTranscriptionStore는 전사 ID/text/duration JSON과 생성 저널을 소유 체험 lifecycle 해시 안에 둔다. 원본 음성은 요청/내부 전송 메모리에만 있고 파일·Redis·영구 저장·로그로 쓰지 않는다. Lua가 현재 세션/동의/소유자/digest/체험 수명·generation·captured revision·예약 token을 완료 직전에 다시 검사한 뒤 결과와 멱등 재생 응답을 함께 쓴다. 편집/삭제/철회/만료/세션 폐기/세대 교체 후 늦은 결과는 쓰지 않는다. 성공은 체험 활동 수명을 절대 상한 안에서 갱신하며 단순 재생/참조 읽기는 갱신하지 않는다. 최대 전사64개/예약128회다. DELETE/만료가 전사/저널을 함께 제거한다.

같은 키/파일 해시의 완료 재생은 당시 전사 결과를 반환하고 STT를 다시 실행하지 않는다. 파일이 다르면409, 같은 키 진행 중은409+Retry-After, 실패/취소된 키는 새 키가 필요하다. 리비전은 서버가 캡처하되 입력 해시에는 넣지 않아, 프로필을 직접 수정한 뒤 같은 완료 요청을 확인해도 다른 키 사용으로 오인하지 않는다. 전사는 프로필/문맥/확정본을 변경하지 않으며 공개 전사 목록/복원 GET을 추가하지 않는다. HTTP 클라이언트가 기다리기를 중지했다고 서버 작업 취소가 보장되지는 않는다. 태스크 취소/종료/만료가 확인된 경우의 반영 차단을 구분한다.

messages의 transcription_id는 같은 소유 체험의 실제 전사인지 검사하는 참조다. 모델 입력에는 사용자가 확인/수정해 보낸 MessageCreate.text만 넣고 전사 원문을 덧붙이지 않는다. 임의/타인/다른 체험 ID는404다. 민감/지시문 패턴과 근거 검증, 명시 프로필 확정 경계는 기존 메시지 정책을 따른다. STT 성공을 사실 승인으로 취급하지 않는다.

후속 점검에서 지원서/전사 생성 카운터가 소수·선행0 등으로 손상되면 HINCRBY 오류 전에 부분 쓰기가 발생할 여지를 발견했다. 두 저장소 모두 쓰기 전에 정규 십진 정수 형태를 검사하도록 보강하고 저널/본문 미생성 회귀를 추가했다. 카운터는 HTTP 입력이 아니며 일반 사용자 요청으로 바꾸는 필드는 없다.

신규30건을 포함한 실제 PostgreSQL16/Redis7 전체1008건/0skip/38.50초 통과. multipart 메모리/바이트/경계/중복/추가/잘림, 실제 HTTP 세션/CSRF/음성 크기/시간/형식, 재생/입력 해시/TTL, 프로필 무변경, 수정 텍스트만 추출, 다른 체험/타인 참조, 최종 삭제와 늦은 완료, 동의/세션/세대/편집 경합, pending/busy/cancel/timeout, 내부422 종료 슬롯 처리, 손상 카운터의 원자 쓰기 차단을 검사했다. STT와 LLM 런타임은 전송/모델 대역이며 실제 Redis·ASGI·추론 한도는 사용했다. 첫 전체 실행에서 신규 실제 라우터가 봉투 크기 전용 시험 라우터보다 먼저 매칭되던 문제는 시험 라우터를 먼저 배치해 해당 미들웨어 검증을 유지했다. 수정 후 전체 통과가 최종 근거다.

실제 STT 모델/압축 디코더·무음·한국어 음질/정확도·GPU/EC2·브라우저 녹음/전체 여정은 남아 있다. 운영 정보 미정으로 실제 동의/체험 시작도 비활성이다. #38 전체 통과나 음성 인식 운영 준비 완료를 주장하지 않는다.
