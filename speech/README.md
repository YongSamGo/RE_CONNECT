# speech — 로컬 음성 서비스

담당: B · AI·데이터 (협력 C)

faster-whisper(STT)와 Qwen3-TTS를 실행하는 별도 컨테이너다. FastAPI의 Speech Adapter만 Compose 내부 네트워크로 호출한다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)).

백엔드의 고정 내부 전송·readiness·STT/TTS 공통 슬롯 경계는 [내부 음성 계약](PROTOCOL.md)을 따른다. [로컬 STT 런타임](STT_RUNTIME.md)은 고정 Whisper의 실제 CPU 적재·합성 한국어 전사를 확인했다. TTS 실행·운영 컨테이너·전체 준비 검증은 남아 있다.

공식 고정 revision의 파일 준비·크기/SHA-256 검사는 [모델 준비 도구](MODEL_PREPARATION.md)를 따른다. 모델 실행 의존성을 설치하지 않고 준비 또는 오프라인 검증할 수 있다.

## 규칙

- 호스트 포트를 공개하지 않고 Nginx로 프록시하지 않는다. 브라우저는 이 서비스에 직접 접근하지 않는다.
- 모델 가중치는 저장소에 커밋하지 않는다. 공식 배포원의 revision·digest를 고정해 준비 단계에서 받고, 사용자 요청 중에는 받지 않는다.
- 저장소 안에 받을 때는 `speech/models/`에만 둔다 (`.gitignore` 처리됨). 다른 위치를 쓰려면 `.gitignore`를 같은 PR에서 고친다. Ollama 모델은 Compose 이름 있는 볼륨에 두고 저장소 폴더에 바인드하지 않는다.
- 임의 모델·원격 코드 실행(`trust_remote_code` 등)을 쓰지 않는다.

모델·라이선스·revision과 런타임·CUDA·컨테이너 조합은 [#28 W04-01](https://github.com/YongSamGo/RE_CONNECT/issues/28)에서 정하고([모델 후보·고정값](../docs/ai/models.md)), 구현은 [#31](https://github.com/YongSamGo/RE_CONNECT/issues/31)·[#32](https://github.com/YongSamGo/RE_CONNECT/issues/32)·[#33](https://github.com/YongSamGo/RE_CONNECT/issues/33)에서 한다.

## 의존성

Python 3.12와 [backend](../backend/README.md#의존성-고정)와 같은 해시 고정 방식을 쓴다. STT/내부 HTTP 런타임의 `requirements.in/txt`와 개발 의존성을 추가했고 CI detect와 Dependabot에도 speech를 연결했다. Qwen3-TTS·CUDA와의 공존 및 별도 의존성 잠금은 후속 검증이다.
