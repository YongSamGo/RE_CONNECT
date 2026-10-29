# W12-03 / #92 모델 실행 환경

- 확인일: 2026-10-29 KST. 주담당 C, 협력 B.
- 상태: 검토. 코드 작성·기존 계약 연결 완료, 실제 EC2 배포 검증 미실행.
- 구성: 기존 운영 Compose에 GPU Ollama 1개와 기존 CPU STT/TTS를 연결하는 overlay.
- 검증: Python 3.12.13/Windows, Docker Compose 5.1.0 오프라인 렌더링 포함 모델 회귀 13개,
  Ollama Adapter·health 회귀 55개, 릴리스 도구 회귀 14개 통과. Bandit 1.9.4 변경 코드 지적 0건.
- 실제 런타임: 로컬 Docker daemon이 실행되지 않아 컨테이너 시작·GPU·Linux 커널 검사는 미실행.
- 차단/남은 범위: 실제 계정·리전·GPU 쿼터·EC2 사양/비용·Ollama 이미지 digest/검사와
  드라이버/Toolkit 호환성 확정, EC2에서 사전 적재·음성 health·swap/core/권한/통신/로그/볼륨 검사.
  #34의 한국어·지연·RAM/VRAM·교대 실행/OOM/취소 평가를 완료로 추정하지 않는다.
- 해제 조건/담당: C가 인프라와 운영 이미지·사양을 확정하고 B와 함께 실제 EC2 증거를 기록한다.
- 실행 절차와 인계 목록: [infra/models/README.md](../../infra/models/README.md).
- 실제 사용 인시간과 다음 확인 시각: 미기록/미확정.
- #92는 실제 EC2 완료 증거 전 종료하지 않는다.
