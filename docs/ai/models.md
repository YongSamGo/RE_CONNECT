# 로컬 모델 후보·라이선스·고정값 (W04-01)

> 기준일: 2026-10-15 · 담당: B(AI·데이터), 협력 C · 관련 이슈: #28 → 후속 #29(Ollama 통신), #31(STT), #32(TTS), #92
>
> 후보는 [Plan/03 §3](../../Plan/03_Architecture_and_Dependencies.md)의 첫 후보다. 이 문서는 **공식 배포원 메타데이터로 확인한 사실**만 적는다. 가중치를 받거나 실행한 결과가 아니며, 품질·지연·메모리는 W04-07(#34)의 실측으로 정한다.

## 1. 후보와 라이선스

| 용도 | 모델 | 공식 배포원 | 라이선스 | 접근 제한 | 실행 코드 |
|---|---|---|---|---|---|
| 텍스트 (대화·추출·지원서) | Qwen3 4B | Ollama 라이브러리 `qwen3:4b` (모델 계열: [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B)) | Apache-2.0 (Ollama 매니페스트의 license 레이어, Hugging Face 카드 모두) | 없음 | Ollama |
| 음성 인식 | Whisper small (CTranslate2 변환) | [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small) | MIT | 없음 | [faster-whisper](https://pypi.org/project/faster-whisper/) 1.2.1 (MIT) + ctranslate2 4.x (MIT, 배포 후 7일 경과·호환성 검증 뒤 정확한 버전 확정) |
| 읽어주기 | Qwen3-TTS 12Hz 0.6B CustomVoice | [Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) | Apache-2.0 | 없음 | [qwen-tts](https://pypi.org/project/qwen-tts/) 0.1.1 (Apache-2.0) |

- 세 모델 모두 상업적 이용·서비스 제공을 막는 조건이 없는 라이선스다. 배포물에 모델 가중치를 넣지 않으므로 재배포 고지 의무는 생기지 않지만, 서비스 안내(오픈소스 고지)에 모델·라이선스 이름을 적는다.
- faster-whisper는 크기 이름(`small`)을 Systran 저장소로 연결하므로, 이름 대신 저장소와 revision을 직접 지정한다.
- 한국어: Qwen3-TTS 카드는 한국어를 지원 언어로 적고 한국어 기본 화자로 `Sohee`(Warm Korean female voice)를 둔다. Whisper small은 다국어 모델이다. 실제 한국어 품질은 W01-07 평가 표본으로 잰다.

## 2. 고정값 (2026-10-15 조회)

준비 단계에서 아래 값으로만 받고, 받은 뒤 같은 값인지 확인한다. 값이 바뀌면 이 표와 함께 PR로 갱신한다.

| 대상 | 고정값 |
|---|---|
| Ollama `qwen3:4b` 매니페스트 | config `sha256:e18a783aae5525fd2852fc94c985541a77e791e034abc2d3056474d59de336fc` |
| ↳ model 레이어 | `sha256:3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f` (2,497,280,480 B) |
| ↳ template / params / license | `sha256:2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9` / `sha256:cff3f395ef3756ab63e58b0ad1b32bb6f802905cae1472e6a12034e4246fbbdb` / `sha256:d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12` |
| Systran/faster-whisper-small | revision `536b0662742c02347bc0e980a01041f333bce120` (2023-11-23) |
| Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice | revision `85e237c12c027371202489a0ec509ded67b5e4b5` (2026-01-29) |
| Qwen/Qwen3-4B (참고) | revision `1cfa9a7208912126459214e8b04321603b3df60c` (2025-07-26). Ollama `qwen3:4b`가 이 revision에서 변환됐는지는 **확인하지 못했다** |

- Ollama 태그(`qwen3:4b`)는 바뀔 수 있으므로 태그가 아니라 model 레이어 digest로 확인한다. `ollama pull` 후 `ollama show --modelfile`·`/api/show`로 digest와 양자화 형식을 기록한다(양자화는 아직 미확인).
- `params` 레이어의 기본값은 `temperature 0.6`, `top_k 20`, `top_p 0.95`다. 구조화 추출은 Plan/03대로 요청에서 `temperature=0`, `think=false`(모델이 허용할 때)로 덮어쓴다.
- Hugging Face 모델은 `revision=<위 commit>`으로 받고, 운영 컨테이너에는 받은 폴더 경로만 넘긴다(`HF_HUB_OFFLINE=1`). 저장소 이름을 넘기면 실행 중에 내려받으려 하므로 쓰지 않는다.

## 3. 런타임 조건

| 대상 | 조건 | 근거 |
|---|---|---|
| ctranslate2 최신(4.x) | **CUDA 12 + cuDNN 9** | faster-whisper 문서: 최신 ctranslate2는 CUDA 12·cuDNN 9만 지원. CUDA 12 + cuDNN 8이면 ctranslate2 4.4.0으로 내려야 한다 |
| faster-whisper 컨테이너 | 공식 예시 이미지 `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` | 같은 문서. digest 고정과 실제 조합은 3단계에서 확정 |
| qwen-tts | `transformers==4.57.3`, `accelerate==1.12.0`을 정확히 고정해 요구 | PyPI 메타데이터. 백엔드와 분리되지만 같은 음성 이미지의 faster-whisper·CUDA 의존성 공존은 검증 전이다 |
| qwen-tts 예시 설정 | `dtype=bfloat16`, `attn_implementation="flash_attention_2"` | 모델 카드. flash-attn은 별도 빌드 의존성이라 3단계에서 사용 여부를 정한다 |
| Ollama | `OLLAMA_NO_CLOUD=1`, 내부 네트워크만 | Plan/03 |

GPU 종류·VRAM·동시 처리량은 이 문서에서 추정하지 않는다(Plan/03 §3). W01-03(#6) EC2 사양이 정해지면 3단계(런타임·드라이버·컨테이너 조합)를 이 문서에 더한다.

## 4. 실행 코드 점검 (qwen-tts 0.1.1)

공식 휠(`qwen_tts-0.1.1`, PyPI sha256 검증)을 실행하지 않고 압축만 풀어 읽었다.

| 확인 항목 | 결과 | 대응 |
|---|---|---|
| 원격 코드 실행 (`trust_remote_code`) | **없음.** 패키지가 자체 모델 클래스를 `AutoConfig.register`·`AutoModel.register`로 등록해서 쓴다 | 규칙(speech/README) 충족. `trust_remote_code=True`를 넘기지 않는다 |
| 외부 요청 | 참조 음성(`ref_audio`)이 `http(s)` URL이면 `urllib.request.urlopen`으로 받는다(음성 복제 기능) | 기본 화자 합성(`generate_custom_voice`)만 쓰고 음성 복제 경로는 호출하지 않는다. 음성 서비스 API는 텍스트만 받는다 |
| 웹 UI 의존성 | 필수 의존성에 `gradio`가 있지만 코드에서는 데모 CLI(`cli/demo.py`)만 쓴다 | 운영 컨테이너에서 데모를 실행하지 않는다. 설치 범위를 줄일 수 있는지(의존성 직접 고정 + `--no-deps`)는 3단계에서 시험 |
| 유지 상태 | 마지막 릴리스 2026-02-06 (0.1.1) | 공급망 점검(`pip-audit`) 대상에 넣고, 갱신이 없으면 고정 버전으로 유지 |

## 5. 다음 단계

- 가중치 준비는 safetensors와 필요한 JSON·토크나이저 파일만 허용하고 pickle 기반 `.pt`·`.pth`·`.pkl`·`pytorch_model.bin`은 받지 않는다. 지원 로더는 `use_safetensors=True`를 사용한다. CTranslate2 `model.bin`은 pickle이 아닌 전용 모델 형식이므로 고정 revision·해시 확인 대상으로 별도 허용한다.
- Ollama 런타임 이미지도 배포 후 7일이 지난 버전의 digest로 고정하고 `think`·JSON Schema·컨텍스트 처리 동작을 실제 모델에서 검증한다. 현재 표는 모델 레이어만 고정하며 런타임 조합은 확정 전이다.
- STT·TTS를 한 이미지에서 실행하기 전에 의존성 해석, torch·CTranslate2의 CUDA/cuDNN 공존과 onnxruntime 설치 조합을 시험한다. 함께 실행할 수 없으면 서비스를 분리한다.

- [x] 1단계: 후보·라이선스 확인 (이 문서 §1·§4)
- [ ] 2단계: 공식 가중치·revision/digest 준비 — STT/TTS 15개 파일은 고정 명세로 실제 준비 후 오프라인 재검증 완료([도구](../../speech/MODEL_PREPARATION.md)). Ollama 준비와 Compose 볼륨 연결은 남아 있다
- [ ] 3단계: 런타임·드라이버·컨테이너 조합 기록 — EC2 사양(#6) 확정 후
- [ ] Ollama `qwen3:4b`의 양자화 형식과 thinking 지원 여부 (`/api/show`)

2026-10-18 로컬 CPU에서 faster-whisper1.2.1/CTranslate2 4.8.2/PyAV16.1.0 조합의 실제 오프라인 적재와 합성 한국어3문장 전사를 확인했다([측정 범위](../../speech/STT_RUNTIME.md)). 이는 GPU/EC2 조합 확정이나 실제 사용자 음성 품질 평가를 대신하지 않는다.
