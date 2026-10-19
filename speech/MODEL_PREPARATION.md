# 고정 모델 파일 준비

`python -I speech/prepare_models.py --model all`은 저장소의 `speech/models/`에만 모델 파일을 받는다. `--model stt`·`--model tts`로 나눌 수 있고, `--verify-only`는 네트워크 요청 없이 이미 받은 파일의 크기·SHA-256과 허용 파일 목록을 검사한다. Python 3.12 표준 라이브러리만 사용하며 모델이나 받은 코드를 실행하지 않는다.

고정값은 [model-manifest.json](model-manifest.json)과 [모델 선정 기록](../docs/ai/models.md)을 함께 따른다. 파일 합계는 2,984,595,982바이트다. 모델 파일은 Git에서 제외하며 API 요청 중에 이 스크립트를 호출하지 않는다.

| 모델 | 준비 파일 | 크기 |
|---|---|---|
| STT | CTranslate2 model.bin, config.json, tokenizer.json, vocabulary.txt | 486,212,372바이트 |
| TTS | safetensors 2개, 설정·토크나이저·merges/vocab의 허용 파일 11개 | 2,498,383,610바이트 |

## 고정값 확인 경로

2026-10-18 공식 Hugging Face API의 고정 revision 메타데이터와 파일을 확인했다.

- [Systran/faster-whisper-small 고정 파일](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120)
- [Qwen3-TTS 고정 파일](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/85e237c12c027371202489a0ec509ded67b5e4b5)

LFS 가중치의 SHA-256과 크기는 해당 revision의 공식 메타데이터를 고정했다. 작은 파일은 같은 revision에서 받은 bytes의 Git blob SHA-1을 메타데이터와 대조한 뒤 SHA-256을 계산했다. 준비 시 원격 명세로 해시를 자동 갱신하지 않는다. revision·목록·크기·해시 변경은 코드와 함께 검토할 변경이다.

## 준비·실패 처리

- HTTPS의 공식 배포 호스트만 허용하고 리다이렉트마다 검사한다. proxy 환경변수·쿠키·토큰을 쓰지 않으며 서명 URL을 출력하지 않는다.
- 고정 파일명만 허용한다. Python·pickle·사용자 화자/참조 오디오를 받지 않는다. CTranslate2 model.bin은 고정 해시의 전용 형식이다.
- 받는 중에는 임의 이름의 partial 파일을 쓰고, 전체 크기와 SHA-256을 확인한 뒤 최종 경로로 반영한다. 실패·키보드 중단 때 자체 partial과 잠금을 정리한다. 강제 프로세스 종료/전원 중단까지 정리를 보장하지는 않는다.
- 이미 정상인 파일은 다시 받지 않는다. 손상 파일과 알 수 없는 파일은 자동 삭제·덮어쓰기하지 않고 실패한다. 심볼릭 링크·Windows junction·경로 탈출을 거절한다.
- 다른 준비 작업의 잠금을 지우지 않는다. 비정상 종료로 `speech/models/.prepare.lock`이 남았다면 실제 준비 프로세스가 종료됐는지 확인한 뒤 로컬에서 정리해야 한다. 남은 partial도 검사 후 직접 정리한다.

파일 준비는 모델 적재/추론 성공의 증거가 아니다. 다음 단계는 오프라인 로더·디코더·실제 한국어 결과·CPU/GPU 자원 제한·런타임 의존성 고정이다. 가중치만으로 speech readiness를 성공 처리하지 않는다.

2026-10-18 로컬에서 허용 파일15개 다운로드와 별도 `--verify-only` 재검사를 모두 완료했다. 모델 파일은 Git 제외 상태를 확인했다. STT의 실제 CPU 적재와 합성 한국어 결과는 [런타임 검증 범위](STT_RUNTIME.md)에 별도로 기록했다. TTS 가중치 준비를 실제 TTS 추론 성공으로 계산하지 않는다.
