# EC2 모델 실행 환경 — W12-03 / #92

상태: 코드 작성·계약 연결, EC2 배포 검증은 미실행(2026-10-29 KST).
기존 운영 Compose에 `compose.models.yaml`을 덧붙인다. Ollama는 GPU 1개를 요청하고,
음성 이미지는 현재 검증된 CPU STT/TTS를 그대로 사용한다. 음성 GPU 지원이나 세 모델의
메모리 공존·한국어 품질을 검증했다고 해석하지 않는다.

## 선행 준비

- #90의 EC2/VPC/RDS와 #18의 DB/Redis, #28의 고정 모델 준비를 먼저 확인한다.
- Linux amd64 EC2에 NVIDIA 드라이버와 NVIDIA Container Toolkit을 설치하고 `nvidia-smi`를 확인한다.
  인스턴스 종류·GPU 쿼터·리전·비용·가동시간은 운영자가 확정한다. 이 변경은 AWS 자원을 생성하지 않는다.
- [Ollama 준비 도구](../../docs/ai/ollama-preparation.md)의 verify와
  [음성 모델 준비](../../speech/MODEL_PREPARATION.md)의 오프라인 검증을 실행한다.
  실행 UID 10001이 상위 경로를 탐색하고 파일을 읽을 수 있게 전용 모델 디렉터리 권한을 설정한다.
  다른 사용자/서비스의 쓰기를 허용하지 않는다. 가중치 디렉터리에 음성·본문·캐시를 넣지 않는다.
- [기존 배포 절차](../deploy/README.md)의 backend/frontend/speech 릴리스 이미지를 사용한다.
  Ollama 이미지는 별도 `ollama/ollama@sha256:<검증값>`으로 지정한다. 아직 운영 이미지 digest를
  확정하지 않았다. 공식 registry·배포 후 7일·취약점 검사·CUDA/드라이버 호환성 확인 후 기록한다.
  태그나 임의 digest를 배포 승인으로 취급하지 않는다. 현재 릴리스 자동화는 Ollama를 빌드/검사하지 않는다.

## 호스트 개인정보 잔류 방지

컨테이너만의 swap 제한은 호스트 swap·core 수집기를 대신하지 않는다. 운영자는 유지보수 시간에
swap을 비활성화하고 부팅 후에도 비활성 상태를 유지한다. `/proc/sys/kernel/core_pattern`은
`/dev/null`, `/proc/sys/fs/suid_dumpable`은 `0`으로 설정하고 systemd-coredump/apport 등 수집기를
비활성화한다. 기존 dump·저널·스냅샷 잔류는 별도 점검한다. 검사 도구는 설정을 변경하지 않는다.

```sh
python3 -I infra/models/check_host.py
```

실패하면 시작하지 않는다. 컨테이너는 core ulimit 0, 메모리와 memory+swap 상한 동일,
읽기 전용 root·모델, 제한된 tmpfs, 파일 로그 없음, UID 10001과 capability 제거를 사용한다.
호스트 디스크 전체 암호화·백업 제외 범위는 #90/#94에서 함께 확인한다.

## 설정과 시작

`/run/reconnect/images.env`는 기존 릴리스 도구가 만드는 이미지 치환 파일이다.
추가 운영 설정을 `/run/reconnect/models.env`에 둔다(호스트 tmpfs, 운영자 전용 권한).
다음 키의 실제 값이 필요하다. 예시 사양을 운영 기본값으로 제공하지 않는다.

```text
OLLAMA_IMAGE=ollama/ollama@sha256:<공식 이미지 검증값>
OLLAMA_MODELS_DIR=<검증한 Ollama 가중치 절대경로>
SPEECH_MODELS_DIR=<검증한 STT/TTS 가중치 절대경로>
OLLAMA_MEMORY_LIMIT=<실측용 메모리 상한, 예: 정수와 g 단위>
OLLAMA_CPUS=<할당 CPU 수>
SPEECH_MEMORY_LIMIT=<실측용 음성 메모리 상한>
SPEECH_CPUS=<할당 음성 CPU 수>
```

저장소 루트에서 다음 함수를 사용한다. 이후 ps/exec/stop/down에도 두 파일·두 env를 동일하게 지정한다.
`config` 원문에는 기존 env 파일의 비밀이 포함될 수 있어 터미널·CI 로그에 출력하지 않는다.

```sh
models_compose() {
  docker compose --env-file /run/reconnect/images.env --env-file /run/reconnect/models.env \
    -f infra/compose.prod.yaml -f infra/compose.models.yaml "$@"
}
(umask 077; models_compose --profile model-tools config --format json > /run/reconnect/models-config.json)
python3 -I infra/models/check_config.py /run/reconnect/models-config.json
```

두 검사 도구의 성공 후에만 진행한다. 실패하면 뒤 명령을 실행하지 않는다. 초기 설치 또는
유지보수 시간에 공개 진입점을 닫은 상태에서 모델을 준비한다. 기존 운영 서비스가 있으면
nginx/backend 중지에 따른 중단 시간을 사전에 확보한다.

```sh
models_compose stop nginx backend
models_compose up -d ollama speech
models_compose run --rm model-warmup
# warmup 실패면 중지. speech의 Docker health가 healthy인지 확인한다.
models_compose ps speech
# 두 모델 서비스 준비 확인 후 기존 웹/DB/Redis 정상 여부까지 검사하며 시작한다.
models_compose up -d --wait --wait-timeout 240
```

Ollama는 고정 매니페스트 digest를 `/api/tags`로 확인한 뒤 사용자 입력 없는
`/api/generate`로 `num_ctx=16384`·무기한 keep_alive를 설정하고 `/api/ps`의 동일 모델·digest와
VRAM 사용 양수를 확인한다. 시작 대기는 최대 60초, 적재 요청의 소켓 대기는 180초다.
실패 시 다운로드·다른 모델·Cloud로 전환하지 않는다. 음성 서비스는 자체 시작 단계에서
검증된 두 모델을 적재하고 기존 `check_ready.py`가 성공해야 healthy다.
모델 서비스가 재시작되면 warmup과 음성 health 확인을 다시 수행한다. 자동 재시작은 사용하지 않는다.

## readiness와 장애 경계

백엔드의 `/health/live`·`/health/ready` 계약은 유지한다. Ollama probe는 `/api/ps`에 설정 모델이
적재되어 있어야 성공한다. health 요청 자체는 모델을 적재하거나 다운로드하지 않는다.
DB/Redis 실패는 503, 모델만 실패하면 기존 `degraded` 200이므로 공개 공고 조회를 계속한다.
backend/nginx의 시작을 모델 healthy에 종속시키지 않는다. 모델 초기 준비는 위 유지보수 절차로 분리한다.
공개 readiness에는 기존 최소 상태만, 운영 상세에는 기존 운영자 API만 사용한다.

공유 실행 슬롯은 기존 Redis 기반 전역 1개를 사용한다. Ollama 병렬/적재 모델 수도 1개다.
CPU 음성 서비스와 GPU LLM이 공존할 EC2 RAM/CPU/VRAM 여유는 #34에서 측정한다.
호스트 포트·Nginx 경로·모델 관리 API는 게시하지 않는다. 모델 컨테이너는 internal 네트워크에만 연결하고
backend만 기존 app/data/egress와 model 네트워크를 연결한다.

## 검증·인계

```sh
python3 -m unittest discover -s infra/models/tests -v
# backend 가상환경에서
cd backend
python -m pytest tests/test_ollama_adapter.py tests/test_health.py -q
```

보안 대응: 중요한 자원에 대한 잘못된 권한 설정, 오류 메시지 정보노출, 암호화되지 않은 중요정보.
태그 이미지·공개 포트·Cloud 활성·swap·core dump·쓰기 가능한 모델·파일 로그를 거절하는 구성 회귀와
모델 불일치·미적재·GPU 미사용·오류 본문 비노출을 시험한다.

EC2 인계 시 릴리스 commit·이미지 digest·모델 manifest/revision·GPU/드라이버/Toolkit·OS/Compose,
검사 결과, 재부팅 후 host 검사, 실제 컨테이너 UID/cgroup/swap/core/tmpfs·외부 통신 차단,
단일/교대 실행 RAM/VRAM·OOM/취소·재시작, 로그/볼륨/스냅샷 잔류 부재 증거를 기록한다.
합성 입력만 사용하며 음성/본문·키·상세 미조치 취약점 원문을 공개 증거에 넣지 않는다.
실제 EC2 증거와 운영 Ollama 이미지·사양 확정 전 #92를 통과 또는 종료로 옮기지 않는다.

공식 근거: [Docker GPU 예약](https://docs.docker.com/compose/how-tos/gpu-support/),
[Ollama FAQ: Cloud·적재·병렬](https://docs.ollama.com/faq),
[generate API](https://docs.ollama.com/api/generate), [loaded models API](https://docs.ollama.com/api/ps),
[NVIDIA Container Toolkit 설치](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
