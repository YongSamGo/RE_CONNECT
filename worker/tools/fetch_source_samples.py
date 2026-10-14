"""W01-05 · 공고 출처의 실제 응답 샘플을 받아 저장하고 필드 구조를 요약한다.

사용 예:
    python worker/tools/fetch_source_samples.py senuri --operation getJobList
    python worker/tools/fetch_source_samples.py volunteer --operation <오퍼레이션명> --param keyword=멘토링

보안 기준:
- 통신 대상은 아래 SOURCES에 고정한 HTTPS 주소뿐이다. 사용자 입력으로 호스트를 바꿀 수 없고 리다이렉트도 따라가지 않는다.
- 인증키는 환경변수나 저장소 루트의 .env에서만 읽고, 출력·오류 메시지·저장 파일 이름에 남기지 않는다.
- 응답은 크기 상한을 두고 읽으며, DOCTYPE·ENTITY가 있는 XML은 파싱하지 않는다(외부 개체 참조 방지).
- 원본 샘플에는 담당자 연락처 같은 개인정보가 있을 수 있어 worker/samples/(커밋 제외)에만 저장한다.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405 - DOCTYPE/ENTITY를 파싱 전에 거부한다
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "worker" / "samples"
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 15

SOURCES = {
    # 한국노인인력개발원 노인 구인정보 — https://www.data.go.kr/data/15015153/openapi.do
    "senuri": {
        "base_url": "https://apis.data.go.kr/B552474/SenuriService",
        "key_env": "DATA_GO_KR_SERVICE_KEY",
        "key_param": "serviceKey",
        "default_params": {"pageNo": "1", "numOfRows": "10"},
    },
    # 행정안전부 봉사참여정보서비스_GW(1365) — https://www.data.go.kr/data/15157582/openapi.do
    # 오퍼레이션명·지역/기간 파라미터는 활용신청 후 명세에서 확인한다.
    "volunteer": {
        "base_url": "https://apis.data.go.kr/1741000/volunteerPartcptnService",
        "key_env": "DATA_GO_KR_SERVICE_KEY",
        "key_param": "serviceKey",
        "default_params": {"pageNo": "1", "numOfRows": "10"},
    },
}

OPERATION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
PARAM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
UNSAFE_XML_RE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "리다이렉트 거부", headers, fp)


def load_dotenv(path: Path) -> None:
    """KEY=VALUE 형식만 읽는다. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def parse_params(pairs: list[str]) -> dict[str, str]:
    params = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not PARAM_NAME_RE.match(name):
            raise SystemExit(f"잘못된 --param 형식: {name!r} (예: keyword=멘토링)")
        if len(value) > 200:
            raise SystemExit(f"--param 값이 너무 깁니다: {name}")
        params[name] = value
    return params


def fetch(source: dict, operation: str, params: dict[str, str]) -> bytes:
    key = os.environ.get(source["key_env"], "").strip()
    if not key:
        raise SystemExit(f"{source['key_env']}가 없습니다. 저장소 루트 .env에 넣어 주세요 (.env.example 참고).")

    query = {**source["default_params"], **params, source["key_param"]: key}
    url = f"{source['base_url']}/{operation}?{urllib.parse.urlencode(query)}"
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"Accept": "application/xml"})
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - https 고정 주소만 사용
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # exc 문자열에는 인증키가 든 URL이 포함될 수 있어 상태 코드만 출력한다.
        raise SystemExit(f"HTTP 오류 {exc.code}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"연결 실패: {type(exc.reason).__name__}") from None
    if len(body) > MAX_BYTES:
        raise SystemExit(f"응답이 {MAX_BYTES} 바이트를 넘어 중단합니다.")
    return body


def summarize(body: bytes) -> None:
    if UNSAFE_XML_RE.search(body):
        print("DOCTYPE/ENTITY가 포함된 응답이라 구조 요약을 건너뜁니다. 원본 파일만 확인하세요.")
        return
    try:
        root = ET.fromstring(body)  # nosec B314 - 위에서 DOCTYPE/ENTITY를 거부했다
    except ET.ParseError:
        print("XML이 아닙니다. 앞부분:", body[:300].decode("utf-8", "replace"))
        return

    for tag in ("resultCode", "resultMsg", "totalCount"):
        node = root.find(f".//{tag}")
        if node is not None:
            print(f"{tag}: {node.text}")

    items = root.findall(".//item")
    print(f"item 수: {len(items)}")
    fields = Counter(child.tag for item in items for child in item)
    for tag, count in sorted(fields.items()):
        print(f"  {tag}  ({count}/{len(items)}건에 값 있음)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--operation", required=True, help="API 오퍼레이션명 (예: getJobList)")
    parser.add_argument("--param", action="append", default=[], help="추가 요청 변수 name=value")
    args = parser.parse_args()

    if not OPERATION_RE.match(args.operation):
        raise SystemExit("오퍼레이션명은 영문·숫자만 허용합니다.")

    load_dotenv(REPO_ROOT / ".env")
    body = fetch(SOURCES[args.source], args.operation, parse_params(args.param))

    out_dir = SAMPLE_DIR / args.source
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}-{args.operation}.xml"
    out_path.write_bytes(body)
    print(f"저장: {out_path.relative_to(REPO_ROOT)}")
    summarize(body)


if __name__ == "__main__":
    sys.exit(main())
