# CPU 음성 컨테이너 (#33 진행)

`Dockerfile`은 Python3.12.15 slim-trixie의 공식 registry digest를 고정한다. [기본 이미지 기록](container-base.json)은2026-10-19 확인한 provenance다. 빌드 단계에서만 해시 잠금된 pip26.2·CPU 의존성과 [검증한12Hz source](tts_compat/README.md)를 준비한다. 런타임 이미지에는 pip를 남기지 않고 모델이나 코드를 다운로드하지 않는다. `.dockerignore`는 허용한 source/명세/잠금만 컨텍스트에 포함하고 모델·가상환경·환경 파일·키·시험 녹음은 제외한다.

## 로컬 실행

먼저 [고정 모델 준비](MODEL_PREPARATION.md)를 완료한다. 저장소 루트에서 실행한다.

```sh
docker compose -f infra/compose.speech-cpu.yaml config --quiet
docker compose -f infra/compose.speech-cpu.yaml build
docker compose -f infra/compose.speech-cpu.yaml up -d --wait --wait-timeout 180
docker compose -f infra/compose.speech-cpu.yaml ps
python infra/check_speech_service.py
docker compose -f infra/compose.speech-cpu.yaml down
```

Linux/amd64 CPU 검증 구성이다. 외부 요청은 공개 백엔드의 동의/소유권/Redis 슬롯 경계를 거쳐야 한다. 이 파일에는 호스트 게시 포트나 Nginx 경로가 없고, `speech:8001`은 동일 내부 네트워크의 서비스만 사용한다. 기존 개발 DB Compose와 자동으로 합쳐지지 않는다. EC2/RDS/GPU 사양이나 운영 통합 Compose를 임의로 확정하지 않는다.

## 제한과 수명

- UID/GID10001, 읽기 전용 root와 모델 bind mount, 모든 capability 제거, no-new-privileges, init을 사용한다. 모델 경로가 없으면 새 빈 호스트 폴더를 만들지 않는다.
- CPU2개·메모리8GiB·동일 swap 상한·PID128개·공유 메모리64MiB를 설정한다. 이는 로컬 시험값이며 EC2 용량 계획이나 처리량 보장이 아니다.
- `/tmp`는64MiB tmpfs이며 noexec/nosuid/nodev다. 컨테이너 파일 로그와 영구 음성 볼륨은 없다. 모델 가중치만 읽기 전용으로 재사용한다.
- 두 모델이 준비된 경우에만 별도 `check_ready.py`가 실제 loopback HTTP로 성공한다. 검사 본문은4KiB/2초 제한이며 추가 필드·느슨한 boolean·잘못된 media/압축·redirect를 거절한다. 검사 자체는 모델을 import하지 않는다.
- 자동 재시작하지 않는다. worker 정지/연결 해제 뒤 readiness가 실패하면 [프로세스 수명](PROCESS_RUNTIME.md)과 백엔드의 보수적 Redis lease 정책에 따라 복구해야 한다. 컨테이너를 재시작했다고 기존 lease를 자동 해제하면 안 된다.

모델 파일의 쓰기 방지와 내부 네트워크는 운영 배치에서도 적용해야 한다. 이 구성만으로 발화 품질·동의 정보·EC2/GPU·사용자 기기 검증이 완료되지는 않는다.

## 검증 상태

2026-10-19 전용 WSL Docker29.1.3에서 새 이미지 빌드·실제 두 CPU 모델 적재·healthy를 확인했다. `infra/check_speech_service.py`는 inspect와 컨테이너 내부 커널 파일을 함께 검사한다. 실제 UID10001, capability0, no-new-privileges, seccomp, 읽기 전용 root/모델, CPU2, 메모리8GiB, swap0, PID128, tmpfs64MiB와 noexec/nosuid/nodev, 공유 메모리64MiB, 게시 포트 없음, 단일 내부 네트워크, 기본 경로 없음, 외부 연결의 ENETUNREACH/EHOSTUNREACH를 확인했다. 실패 조건 회귀10개를 포함해 Linux59개 통과, Windows58개 통과·POSIX 전용1개 제외다. Bandit 검사는 지적0이며 운영자 전용 검사 도구의 subprocess import/고정 argv 실행에는 사유를 적은 좁은 예외2곳이 있어 PR에서 검토해야 한다.

동일 내부 네트워크의 별도 백엔드 시험 이미지에 백엔드의 해시 잠금 의존성을 설치했다. `InternalSpeechAdapter`의 고정 origin `http://speech:8001`을 변경하지 않고 실제 DNS와 TCP로 readiness·합성·전사를 확인했다. TTS 인사말은126764바이트 WAV였고 공개 합성 녹음은 “저는 도서관에서 책을 정리하는 일을 했습니다.”로 전사됐다. 두 요청 모두 현재 ID의 완료 callback을 확인했다. 백엔드의 `httpx`와 서비스의 `httpx2` 환경은 분리한다. 시험 엔진은 기본 Docker와 별도 socket을 사용했고, 시험용 내부 bridge 전달 규칙은 시험 후 원복했다.

## 이미지 취약점과 남은 배포 조건

공식 SHA-256을 확인한 Trivy0.75.0으로 최종 이미지를 검사했다. OS는 Debian13.7이며 Critical0, High44, Medium58, Low61, Unknown3건의 패키지 지적이 있다. Python 패키지 지적은0건이다. 이는 취약점이 없는 이미지라는 뜻이 아니다. High44건은 ncurses·systemd/udev·acl·util-linux 계열·perl의8개 CVE가 여러 패키지에 반복된 것이며 검사 시점의 FixedVersion은 모두 비어 있다. 미수정 OS 지적의 조치·수용 검토 전에는 운영 릴리스를 통과로 처리하지 않는다. 원시 검사 결과에는 사용자 자료가 없으며 로컬 비공개 시험 보고서에 보관했다.

bookworm의 SQLite Critical과 pip 지적을 그대로 두지 않고 trixie 고정 기반과 빌드 전용 pip로 변경해 다시 검사했다. 런타임 제한은 방어 계층이며 취약점 해결을 대신하지 않는다. EC2/GPU·브라우저 재생·문장 청취 품질·운영 동의 정보는 여전히 미검증 또는 미정이다. 이 PR의 범위는 로컬 CPU 내부 연결과 격리 구성까지이며 #33 전체 운영 완료나 배포 승인으로 처리하지 않는다.


## GPU 변형 (#92)

CPU 빌드/기본 장치 선택은 유지한다. `Dockerfile.gpu`는 별도 해시 잠금으로 Torch 2.14.1+cu130과
CTranslate2 cu12 라이브러리를 설치하며 `SPEECH_DEVICE=cuda`를 고정한다. T4 실측에 따라
STT float16, TTS float32/eager를 사용한다. `cuda`가 준비되지 않으면 readiness 실패이며 CPU로 전환하지 않는다.
[GPU 운영 구성/검증](../infra/models/README.md)을 따른다. CPU 이미지 digest를 GPU로 지정하지 않는다.

GPU 런타임은 `TORCH_DISABLE_NATIVE_JIT=1`로 Torch native 연산의 Triton JIT 전환을 막는다.
`TORCHDYNAMO_DISABLE`만으로는 이 경로가 꺼지지 않으며 런타임 C 컴파일러를 추가하지 않는다.
`HOME=/tmp`는 홈 디렉터리 없는 UID 10001의 기본 캐시 경로를 쓰기 가능한 tmpfs로 돌리는 방어 설정이다.
`LD_LIBRARY_PATH`는 `/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib` 다음에
`/opt/ct2/nvidia/cublas/lib`를 둔다. CT2용 cuDNN 경로를 제외해 Torch cu130의 cuDNN과 충돌하지 않게 하고,
CT2용 cuBLAS 12는 유지한다. 빌드 중 `libcudnn.so.9` 존재를 검사해 venv의 `lib` 경로를 확인한다.
읽기 전용 root·모델, 제한된 `/tmp`, 비특권 UID와 파일 로그 없음은 그대로 유지한다.

준비 도구가 모델 파일을 0600으로 저장하므로 Linux에서는 컨테이너 UID 10001에 읽기·상위 경로 탐색 권한이
필요하다. 운영 모델 전용 디렉터리의 소유자/그룹이나 ACL로 최소 권한을 부여하고 다른 사용자의 쓰기는 막는다.
기존 작업자의 모델 권한을 임의로 넓히지 않는다. 이번 시험은 별도 복사본만 UID 10001 소유로 설정했다.
