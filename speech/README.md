# speech — 로컬 음성 서비스

담당: B · AI·데이터 (협력 C)

faster-whisper(STT)와 Qwen3-TTS를 실행하는 별도 컨테이너다. FastAPI의 Speech Adapter만 Compose 내부 네트워크로 호출한다 ([Plan/03](../Plan/03_Architecture_and_Dependencies.md)).

## 규칙

- 호스트 포트를 공개하지 않고 Nginx로 프록시하지 않는다. 브라우저는 이 서비스에 직접 접근하지 않는다.
- 모델 가중치는 저장소에 커밋하지 않는다. 공식 배포원의 revision·digest를 고정해 준비 단계에서 받고, 사용자 요청 중에는 받지 않는다.
- 저장소 안에 받을 때는 `speech/models/`에만 둔다 (`.gitignore` 처리됨). 다른 위치를 쓰려면 `.gitignore`를 같은 PR에서 고친다. Ollama 모델은 Compose 이름 있는 볼륨에 두고 저장소 폴더에 바인드하지 않는다.
- 임의 모델·원격 코드 실행(`trust_remote_code` 등)을 쓰지 않는다.

모델·라이선스·revision과 런타임·CUDA·컨테이너 조합은 [#28 W04-01](https://github.com/YongSamGo/RE_CONNECT/issues/28)에서 정하고, 구현은 [#31](https://github.com/YongSamGo/RE_CONNECT/issues/31)·[#32](https://github.com/YongSamGo/RE_CONNECT/issues/32)·[#33](https://github.com/YongSamGo/RE_CONNECT/issues/33)에서 한다.

## 의존성

Python 3.12와 [backend](../backend/README.md#의존성-고정)와 같은 pip-tools 고정 방식을 쓴다. `requirements.txt`를 처음 추가할 때 CI [`detect`](../.github/workflows/ci.yml) 잡의 폴더 목록과 [dependabot.yml](../.github/dependabot.yml)에 `speech`를 함께 추가한다. 지금 CI는 `backend`·`worker`만 찾는다.
