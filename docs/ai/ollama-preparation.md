# Ollama Qwen3 가중치 준비 (W04-01 · #28)

Ollama는 실행 엔진이고 `qwen3:4b`는 그 안에서 실행할 텍스트 모델이다. 이 도구는 **가중치 준비와 추론을 분리**한다. Ollama 설치·서버 기동·추론·Cloud 호출은 하지 않는다. Python 3.12 표준 라이브러리만 사용한다.

## 준비와 오프라인 확인

저장소 루트에서 실행한다. 약 2.5GB의 여유 공간과 다운로드가 필요하다.

```bash
python -I backend/tools/prepare_ollama.py prepare
python -I backend/tools/prepare_ollama.py verify
```

기본 저장 위치는 Git에서 제외한 `models/ollama/`다. 별도 위치는 두 명령 모두 `--root <전용 폴더>`로 지정한다. 웹 사용자 입력으로 경로를 받지 않으며 운영자만 실행한다. 다른 사용자·서비스가 동시에 수정하지 않는 개인 전용 폴더를 사용한다.

- `prepare`: 공식 Ollama registry의 **고정된 blob 5개만** HTTPS로 받는다. 기존 파일은 다시 검사하고 덮어쓰지 않는다. 현재 태그를 재조회해 새 모델로 바꾸지 않는다.
- `verify`: 네트워크·추론 없이 매니페스트와 blob 5개의 정확한 크기·SHA-256을 확인한다. 파일이 없거나 변조됐으면 종료 코드 1이다.
- 매니페스트는 저장소의 [고정 파일](../../backend/tools/ollama-manifest.json)과 코드 안 SHA-256을 함께 검증한다. 모든 blob을 검증한 뒤 마지막에 게시한다.
- 다운로드는 파일당 최대 30분, 소켓 대기 30초, 고정 크기까지만 허용한다. 압축 응답·길이 불일치·다른 HTTPS 호스트·HTTP 전환을 거절한다. 공식 registry의 현재 CDN 한 곳만 명시적으로 허용한다.
- 오류에는 예외 종류만 표시한다. 서명 URL이나 응답 본문을 출력하지 않는다. 프록시 환경변수를 상속하지 않는다.
- 링크·Windows junction·blob 하드링크를 거절한다. 준비 잠금이 이미 있으면 실패한다. 기존 데이터와 잠금은 자동 삭제하지 않는다. 중단된 잠금은 해당 준비 프로세스가 끝났는지 확인한 후 운영자가 정리한다.
- 실패한 다운로드의 자체 임시 파일만 정리한다. 이미 검증한 blob은 다음 실행에서 재사용할 수 있다. 손상된 기존 파일은 별도 전용 폴더에 다시 준비하거나 운영자가 확인해 처리한다.

## 고정값과 검증 기록

2026-10-20 공식 registry 응답이 [모델 후보 문서](models.md)에서 정한 config·model·template·params·license digest와 모두 일치했다. 태그의 변경 여부와 무관하게 아래 매니페스트만 게시한다.

| 항목 | 값 |
| --- | --- |
| 모델 | `qwen3:4b` |
| 매니페스트 | 859 B · SHA-256 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` |
| model blob | 2,497,280,480 B · SHA-256 `3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f` |
| 기타 blob | config 487 B, template 1,506 B, license 11,338 B, params 120 B |
| 로컬 실제 확인 | Windows에서 5개 다운로드·해시 검증 후 별도 `verify` 재통과 |
| 공격 경계 시험 | 변조·초과·잘린 파일, 부분 다운로드 재개, 덮어쓰기 방지, 잠금, 링크, 비허용 리다이렉트·압축·헤더, 오류 본문 비노출 |

서버에 제공할 때는 이 폴더를 Ollama의 `OLLAMA_MODELS` 위치에 읽기 전용으로 연결한다. 모델 레이어만 바꾸거나 임의 `ollama pull`로 갱신하지 않는다. [공식 FAQ](https://docs.ollama.com/faq)에 따라 `OLLAMA_NO_CLOUD=1`을 설정하고 외부 통신을 네트워크에서도 막아야 한다.

## 실제 로컬 CPU 적재 확인 (2026-10-20)

준비 CLI와 분리한 임시 시험에서 아래 조합을 확인했다. 운영 서버를 설치·상시 실행하는 구성은 아니다.

| 항목 | 실제 확인값 |
| --- | --- |
| 런타임 | Ollama 0.40.3 · 공식 배포일 2026-10-11 · Linux amd64/WSL Ubuntu 24.04 CPU |
| 공식 배포 파일 | [ollama-linux-amd64.tar.zst](https://github.com/ollama/ollama/releases/tag/v0.40.3) · 1,437,349,190 B |
| 배포 파일 SHA-256 | `ce6f8b671a699bf1ebafb28d60dbbabf4f37b30b499145fa308a8ba72de021d6` · 공식 GitHub Release asset digest와 대조 |
| 실행 범위 | 검증한 배포 파일 중 실행 파일·CPU 라이브러리·라이선스만 별도 임시 폴더에 추출. CUDA/Vulkan 라이브러리 제외 |
| 모델 식별 | `/api/tags`의 digest가 고정 매니페스트와 일치. `/api/show`: GGUF, Qwen3 4.0B, Q4_K_M, completion/thinking 지원 |
| 네트워크 | 별도 Linux network namespace의 loopback만 사용. 경로 없음, 외부 IP 연결 `ENETUNREACH`, `OLLAMA_NO_CLOUD=1` |
| 직접 요청 | `/api/chat`, `stream=false`, `think=false`, JSON Schema, `temperature=0`, `num_ctx=16384`, `num_predict=128`, CPU 스레드 2 |
| 응답 | 가상의 짧은 한국어 확인 입력 → `{"ok":true}` 스키마 통과, done/stop, thinking 비어 있음. 16.119초, prompt 34/output 9 토큰 |
| 실제 백엔드 Adapter | 현재 develop의 `OllamaLLMAdapter`로 readiness·구조화 응답 재검증 통과. 15.882초, 컨텍스트 16,384 |
| CPU 확인·종료 | `/api/ps`의 VRAM 사용 0. 종료 후 소유 서버·자식 프로세스 0개 |

위 시간은 짧은 합성 입력 두 건의 로컬 확인값이다. 콜드/웜 성능 비교나 한국어 대화·추출·지원서 품질 합격을 뜻하지 않는다. 모델 적재 시 `/api/ps`의 계획 크기는 5,109,197,044 B였으며 실제 RSS나 서비스 전체 메모리 사용량으로 해석하지 않는다.

운영 컨테이너 이미지 digest·볼륨·자원 제한, EC2/GPU 조합(#6/#92), 실제 기능 품질·성능 평가(#34)는 별도 검증이 필요하다. STT·TTS 준비는 해당 음성 PR에서 검토한다. #28 전체 완료로 표시하지 않는다.
