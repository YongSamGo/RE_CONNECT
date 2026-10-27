# 내부 STT 런타임 (#31 로컬 진행)

별도 Python 3.12 환경에서 해시 잠금 파일로 설치하고, `speech/`에서 실행한다.

```sh
python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

이 명령은 로컬 검증용이다. 운영 컨테이너/Compose 내부 네트워크·tmpfs·프로세스/메모리 제한은 아직 연결하지 않았다. 호스트 공개 포트나 외부 AI 연결을 추가하지 않는다. 의존성은 uv 0.10.0으로 Linux/Python 3.12 대상, 2026-10-11 이전 릴리스만 사용해 해시와 함께 고정했다. Windows 전용 colorama도 명시해 같은 잠금을 설치할 수 있다.

현재 HTTP 서비스는 STT·TTS를 함께 별도 프로세스에 적재한다. 전체 설치·준비·실행 명령은 [프로세스 서비스](PROCESS_RUNTIME.md)를 따른다.

## 실제 처리

- 시작 시 [준비 도구](MODEL_PREPARATION.md)의 STT 파일 크기/SHA-256을 다시 검사한다. 모델 이름 대신 고정 로컬 폴더를 사용하고 `local_files_only=True`, HF 오프라인 모드를 강제한다.
- faster-whisper 1.2.1 + CTranslate2 4.8.2 + PyAV 16.1.0, CPU/int8/스레드2/작업자1로 적재한다. 이전에 시험한 CTranslate2 4.6.0은 최신 setuptools에서 제거된 pkg_resources를 요구해 적재하지 못했다. 4.8.2 조합으로 실제 적재와 추론을 확인했다. GPU 설정을 자동 선택하지 않는다.
- HTTP body는 단일 binary이며 메모리에서 최대6MiB만 받는다. WAV(16kHz/16bit/mono PCM), WebM/Ogg(Opus·Vorbis), MP4(AAC)만 실제 디코딩한다. 영상·첨부·복수 오디오·허용하지 않은 codec을 거절한다. 압축 파일도 실제 decode/resample 후90초를 검사한다.
- 입력 stream 채널1~2, sample rate8~192kHz를 허용해16kHz mono float32로 바꾼다. 파일명·외부 URL·playlist를 받지 않고 고정 demuxer만 사용한다. decode loop의 시간/프레임 수와 출력 sample 수를 제한한다. native 호출 한 번의 강제 중단이나 컨테이너 자원 격리를 이 검사로 대신했다고 주장하지 않는다.
- BytesIO의 custom I/O 외 프로토콜 허용 목록은 비우고, MOV 외부 track·절대 경로 참조도 명시적으로 끈다([FFmpeg 프로토콜 옵션](https://ffmpeg.org/ffmpeg-protocols.html#Protocol-Options), [MOV demuxer 옵션](https://ffmpeg.org/ffmpeg-formats.html#mov_002fmp4_002f3gp)).
- 디지털 무음/극미세 잡음은 RMS 검사로 먼저 거절한다. 실제 발화는 Whisper의 VAD를 추가 적용하고 한국어·고정 decoding 설정으로 전사한다. 전사 generator를 끝까지 소비한 뒤 최대2000자·NFC·숨은 문자를 검사한다. 빈 전사는 입력 오류다.
- 파일로 스풀하지 않고 요청 오디오는 요청/작업 수명 안에서만 보관한다. 완료·오류 때 float32 오디오 배열을 지우고 모델에는 배열/전사 이력을 저장하지 않는다. 전사·오디오·외부 예외 본문을 로깅하지 않는다.

## 종료와 취소

한 native 작업만 수행한다. 현재 HTTP는 [별도 프로세스와 종료 ACK](PROCESS_RUNTIME.md)를 사용한다. 시간 초과/요청 취소 시 실제 프로세스 사망과 IPC 배출을 확인한 뒤 잠금을 해제한다. 실제 종료 확인에 실패하면 완료 헤더를 보내지 않고 잠금을 유지한다. 이전 thread 방식의 취소 후 계속 실행 한계를 대체했다.

`/health/ready`는 살아 있는 프로세스 안에서 두 모델이 모두 적재된 경우에만200이다. 한쪽 실패나 프로세스 정지 뒤에는503이다. 전체 운영 배치/발화 품질 판정과 구분한다.

## 확인한 증거와 남은 범위

- 실제 PyAV encode/decode를 사용하는 형식·길이·무음·영상/codec 거절과 generator 소비/중간 및 최종 배열 정리, HTTP 오류 및 실제 blocking thread의 취소/시간 초과를 포함한27개 시험이 통과했다. HTTP 수명 시험은 모델 대역이며 codec 시험은 실제 PyAV다.
- 고정 Whisper를 실제 오프라인 적재한 뒤, 로컬 Windows SAPI Heami가 만든 한국어3문장을 실제 ASGI API로 전사했다. “도서관에서 책을 정리”, “화요일 오전 안내”, “식당 손님 안내와 설거지” 세 원문 모두 문장 전체가 일치했다. 음성 길이3.395~4.105초, 각 API 처리4.563~5.141초이며 별도 적재 시험은7.94초였다. 한 랩탑의 합성 음성3건 측정으로 성능 기준을 정하지 않는다.
- Ubuntu24.04/WSL의 Python3.12.3 격리 환경에도 같은 해시 잠금을 설치해27개 시험을 통과했다. 같은 고정 모델의 실제 오프라인 CPU 적재5.137초, 첫 합성 음성4.07초의 실제 ASGI 전사1.597초·문장 전체 일치를 확인했다. Windows와 같은 호스트의 단일 표본이며 EC2 비교나 성능 보장으로 해석하지 않는다.
- 의존성 pip-audit 알려진 취약점0, Bandit 지적0을 확인했다. 처음 감사는 Windows tqdm의 colorama 잠금 누락으로 실패했고 명시해 다시 통과했다.

후속 CPU 시험에서 실제 TTS 공존과 별도 프로세스의 ASGI 전사/합성도 확인했다([범위](PROCESS_RUNTIME.md)). 실제 사용자/대상 기기 마이크·환경 소음·방언·인식 실패·EC2/GPU 지연/메모리·컨테이너 격리는 계속 검증해야 한다. 운영 동의 정보 미정으로 실제 시작 화면도 비활성이다. #31 전체 통과나 배포 완료로 처리하지 않는다.
