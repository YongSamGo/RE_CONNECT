#!/usr/bin/env bash
# 릴리스 이미지 하나를 빌드하고 Trivy로 검사·SBOM을 만든 뒤 판정한다 (#93 W12-04).
# 저장소 루트에서: infra/release/build_and_scan.sh <backend|frontend|speech|speech-gpu> <출력 폴더>
# TRIVY 환경변수에 체크섬을 확인한 trivy 실행 파일 경로를 넣는다.
# 검사 결과 JSON에는 미조치 취약점 목록이 들어 있으므로 공개 산출물로 올리지 않는다.
set -euo pipefail

image="${1:?이미지 이름}"
out="${2:?출력 폴더}"
trivy="${TRIVY:?trivy 실행 파일 경로}"
candidate="reconnect-${image}:candidate"

case "$image" in
  backend) docker build --pull=false -t "$candidate" backend ;;
  frontend) docker build --pull=false --build-context api=docs/api -t "$candidate" frontend ;;
  speech-gpu) docker build --pull=false --file speech/Dockerfile.gpu --target runtime -t "$candidate" speech ;;
  speech) docker build --pull=false --target runtime -t "$candidate" speech ;;
  *) echo "알 수 없는 이미지: $image" >&2; exit 2 ;;
esac

mkdir -p "$out"
# 취약점 DB를 한 번 받고 두 번째 실행은 같은 DB를 쓴다.
"$trivy" image --quiet --scanners vuln --format json --output "$out/${image}-scan.json" "$candidate"
"$trivy" image --quiet --skip-db-update --format cyclonedx --output "$out/${image}-sbom.cdx.json" "$candidate"
python3 -I infra/release/check_image_scan.py --image "$image" \
  --scan "$out/${image}-scan.json" --accept infra/release/image-scan-accept.json
