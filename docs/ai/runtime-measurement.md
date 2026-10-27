# EC2 모델 실측 절차 (W04-07)

> 담당: B(AI·데이터) · 관련 이슈: #34(실제 EC2 성능·품질), #30(추출 근거), #31·#32(음성) · 도구: [eval/check_extraction.py](../../eval/check_extraction.py), [eval/measure_speech.py](../../eval/measure_speech.py)
>
> 2026-10-28 CPU 인스턴스에서 이 순서로 측정했다([추출 결과](extraction-eval-2026-10-28.md), #34 댓글). GPU 할당량이 승인되면 같은 명령으로 다시 잰다.

운영 배포 절차가 아니다. 개발용 인스턴스에서 모델을 띄워 지연·메모리·품질을 재는 순서다. 입력은 모두 `eval/`의 가상 인물·문장이고, 결과는 커밋하지 않는 `security-reports/`에 둔다.

## 1. 준비

저장소 루트(`~/RE_CONNECT`)에서 실행한다. Docker와 백엔드 가상환경(`backend/.venv`)이 있어야 한다([개발 환경](../development.md)).

```bash
python3 -I speech/prepare_models.py --model all && python3 -I speech/prepare_models.py --verify-only --model all
python3 -I backend/tools/prepare_ollama.py prepare && python3 -I backend/tools/prepare_ollama.py verify
```

**Linux 서버에서는 모델 폴더 권한을 컨테이너 사용자에게 열어야 한다.** 준비 스크립트는 파일을 `600`으로 저장하는데 음성 컨테이너는 UID·GID 10001로 실행돼, 그대로 두면 모델을 읽지 못하고 `unhealthy`가 된다(컨테이너 로그는 꺼져 있어 원인이 보이지 않는다). 그룹만 10001로 바꾸고 읽기만 준다.

```bash
sudo chgrp -R 10001 speech/models && sudo chmod -R g+rX,g-w,o-rwx speech/models
```

## 2. 음성 (STT·TTS)

```bash
docker compose -f infra/compose.speech-cpu.yaml build
docker compose -f infra/compose.speech-cpu.yaml up -d --wait --wait-timeout 300
docker run --rm --network reconnect-speech-cpu_speech --read-only --tmpfs /tmp:size=64m \
  --entrypoint /opt/venv/bin/python -v "$PWD/eval:/eval:ro" reconnect-speech-cpu:local \
  -I /eval/measure_speech.py --source /eval/personas > security-reports/speech-measure.log
```

- 음성 서비스는 내부 네트워크에만 있어서 같은 네트워크에 측정용 컨테이너를 붙인다. 음성 이미지를 진입점만 바꿔 쓰고 `eval/`은 읽기 전용으로 연결한다.
- `--source`에 #265의 `eval/speech_cases.json`을 주면 음성 평가 대본으로 잰다. 없으면 페르소나 대화 43문장을 쓴다.
- `--long-text`는 문장 6개를 이은 긴 합성 1건을 먼저 잰다. CPU에서는 55초 제한을 넘어 503이 나고, **런타임이 재시작하지 않아 이후 요청이 모두 실패한다.** 다시 재려면 `docker compose -f infra/compose.speech-cpu.yaml restart`.
- 메모리는 다른 터미널에서 `docker stats reconnect-speech-cpu-speech-1`로 본다.
- 끝나면 `docker compose -f infra/compose.speech-cpu.yaml down`.

## 3. LLM 경험 추출

Ollama는 [고정 가중치 준비](ollama-preparation.md)의 검증한 배포 파일(0.40.3)을 쓴다. 공식 릴리스의 `ollama-linux-amd64.tar.zst`를 받아 SHA-256을 대조하고 실행 파일·라이브러리만 푼다. CPU 측정이면 `cuda*`·`vulkan*` 라이브러리를 빼고, GPU 측정이면 CUDA 라이브러리를 포함한다.

```bash
OLLAMA_MODELS=$PWD/models/ollama OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ~/ollama-rt/bin/ollama serve &
curl -s 127.0.0.1:11434/api/tags      # digest가 359d7dd4…인지 확인
backend/.venv/bin/python -I eval/check_extraction.py --repeat 2 --out security-reports/extraction.json
kill %1
```

- 실제 백엔드 `OllamaLLMAdapter`와 `GroundedGenerationService`를 그대로 쓴다. 측정을 위해 Adapter 제한만 600초로 늘리고, 서비스 기본 제한(60초) 초과 여부는 `over_limit`로 따로 센다.
- 채점 항목은 도구 설명에 있다. 경험이 들어 있는 턴과 자격증 구절은 [eval/extraction_cases.json](../../eval/extraction_cases.json)에 적었다. 근거 검사 실패, 경험이 아닌 턴 추출, `must_not_extract` 누출이 하나라도 있으면 종료 코드 1이다.
- 문구의 의미 일치(기대 프로필과 같은 경험인지)는 자동 채점이 대신하지 않는다. `--show`로 추출 내용을 함께 보고 사람이 판단한다.
- 첫 요청은 모델 적재 시간을 포함한다. 메모리는 `ps -C llama-server -o rss=`로 본다.

## 4. 기록할 것

| 항목 | 예 |
|---|---|
| 장비 | 인스턴스 유형, vCPU·메모리·GPU, 리전, OS |
| 버전 | 음성 모델 revision(model-manifest.json), Ollama 버전, 모델 digest, 프롬프트 버전(`PROMPT_VERSION`) |
| 지연 | TTS 문장별 최대, STT 89초 음성, 추출 최대·60초 초과 수 |
| 품질 | STT CER(합성 음성 기준임을 표시), 추출 채점 요약 |
| 메모리 | 음성 컨테이너 최대, Ollama 실행 프로세스 RSS, GPU 측정이면 VRAM |
| 실패 | 시간 초과·런타임 정지 여부와 복구 방법 |

결과 요약은 #34에, 추출 품질 변화는 `docs/ai/extraction-eval-<날짜>.md`에 남긴다. 측정이 끝나면 Ollama를 끄고 인스턴스를 중지한다.
