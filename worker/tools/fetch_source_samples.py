"""W01-05 · 공고 출처의 실제 응답 샘플을 받아 저장하고 필드 구조를 요약한다.

사용 예 (오퍼레이션명·파라미터는 docs/data/sources.md 참고):
    python worker/tools/fetch_source_samples.py senuri --operation getJobList
    python worker/tools/fetch_source_samples.py volunteer --operation getVltrAreaList --param schSido=6110000
    python worker/tools/fetch_source_samples.py seoul50plus --operation job --param year=2026

보안 기준:
- 통신 대상은 아래 SOURCES에 고정한 HTTPS 주소뿐이다. 사용자 입력으로 호스트를 바꿀 수 없고 리다이렉트도 따라가지 않는다.
- 인증키는 환경변수나 저장소 루트의 .env에서만 읽고, 출력·오류 메시지·저장 파일 이름에 남기지 않는다.
  통신 중 어떤 예외가 나도 예외 이름만 출력한다(예외 메시지에 인증키가 든 URL이 들어갈 수 있다).
- 응답은 크기 상한을 두고 읽으며, DOCTYPE 선언이 있는 XML은 파싱하지 않는다(외부 개체 참조 방지).
  DOCTYPE 검사는 expat으로 하므로 UTF-16 등 응답 인코딩과 관계없이 적용된다.
- 원본 샘플에는 담당자 연락처 같은 개인정보가 있을 수 있어 worker/samples/(커밋 제외)에만 저장한다.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405 - has_dtd()로 DOCTYPE 선언이 있는 문서는 파싱하지 않는다
import xml.parsers.expat
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
        "env_var": "DATA_GO_KR_SERVICE_KEY",
        "key_param": "serviceKey",
        "default_params": {"pageNo": "1", "numOfRows": "10"},
    },
    # 행정안전부 봉사참여정보서비스_GW(1365) — https://www.data.go.kr/data/15157582/openapi.do
    # 확인된 오퍼레이션명·지역 파라미터는 docs/data/sources.md 3절 참고.
    "volunteer": {
        "base_url": "https://apis.data.go.kr/1741000/volunteerPartcptnService",
        "env_var": "DATA_GO_KR_SERVICE_KEY",
        "key_param": "serviceKey",
        "default_params": {"pageNo": "1", "numOfRows": "10"},
    },
    # 서울시50플러스 API 센터 — https://www.50plus.or.kr/apiIndex.do (가치동행 일자리·인턴십·교육, JSON 응답)
    # 오퍼레이션이 경로라서 아래 이름으로만 고르게 한다. year는 필수 파라미터다.
    # 경로는 API 매뉴얼(PDF, 2025-10) 기준이다. 웹페이지 설명의 job/list·internship/list는 "No service was found"로 404다.
    "seoul50plus": {
        "base_url": "https://openapi.50plus.or.kr/openapi/service",
        "env_var": "SEOUL50PLUS_API_KEY",
        "key_param": "accessKey",
        "default_params": {"_type": "json", "pageNo": "1", "numOfRows": "10"},
        "operations": {"job": "job1/list", "internship": "job2/list", "education": "education/list"},
        "format": "json",
        "ok_code": "0000",
    },
}

# fullmatch로 검사한다. re.match + `$`는 끝의 줄바꿈 하나를 허용해 제어문자가 URL까지 들어간다.
OPERATION_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,63}")
PARAM_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
# data.go.kr 게이트웨이 오류(키 미등록·한도 초과)는 HTTP 200에 이 태그로 담겨 온다.
STATUS_TAGS = ("resultCode", "resultMsg", "returnAuthMsg", "returnReasonCode", "errMsg", "totalCount")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "리다이렉트 거부", headers, fp)


def load_dotenv(path: Path) -> None:
    """KEY=VALUE 형식만 읽는다. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return
    # utf-8-sig: Windows 편집기가 붙이는 BOM 때문에 첫 줄 변수 이름이 깨지지 않도록 한다.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def parse_params(pairs: list[str]) -> dict[str, str]:
    params = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not PARAM_NAME_RE.fullmatch(name):
            raise SystemExit(f"잘못된 --param 형식: {name!r} (예: keyword=멘토링)")
        if len(value) > 200:
            raise SystemExit(f"--param 값이 너무 깁니다: {name}")
        params[name] = value
    return params


def fetch(source: dict, operation: str, params: dict[str, str]) -> bytes:
    key = os.environ.get(source["env_var"], "").strip()
    if not key:
        raise SystemExit(f"{source['env_var']}가 없습니다. 저장소 루트 .env에 넣어 주세요 (.env.example 참고).")

    path = source["operations"][operation] if "operations" in source else operation
    query = {**source["default_params"], **params, source["key_param"]: key}
    url = f"{source['base_url']}/{path}?{urllib.parse.urlencode(query)}"
    opener = urllib.request.build_opener(NoRedirect)
    accept = "application/json" if source.get("format") == "json" else "application/xml"
    request = urllib.request.Request(url, headers={"Accept": accept})
    # 아래 어떤 예외든 메시지(str(exc))에는 인증키가 든 URL이 포함될 수 있어 코드·이름만 출력한다.
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - https 고정 주소만 사용
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP 오류 {exc.code}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"연결 실패: {type(exc.reason).__name__}") from None
    except (OSError, http.client.HTTPException) as exc:
        # 응답 수신 단계의 TimeoutError, RemoteDisconnected, IncompleteRead, InvalidURL 등
        raise SystemExit(f"통신 실패: {type(exc).__name__}") from None
    if len(body) > MAX_BYTES:
        raise SystemExit(f"응답이 {MAX_BYTES} 바이트를 넘어 중단합니다.")
    return body


def has_dtd(body: bytes) -> bool:
    """인코딩과 관계없이 DOCTYPE 선언이 있는지 expat으로 확인한다. ENTITY 선언은 DOCTYPE 안에만 올 수 있다."""
    found = False

    def on_doctype(*_):
        nonlocal found
        found = True
        raise ValueError  # 선언을 만나면 바로 중단

    parser = xml.parsers.expat.ParserCreate()
    parser.StartDoctypeDeclHandler = on_doctype
    try:
        parser.Parse(body, True)
    except (ValueError, xml.parsers.expat.ExpatError):
        pass
    return found


def _find_items(node: object) -> list | None:
    """JSON 응답에서 item 목록을 찾는다. 공공 API는 response.body.items.item 형태가 많지만 깊이가 출처마다 다르다."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == "item":
                return value if isinstance(value, list) else [value]
            found = _find_items(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_items(value)
            if found is not None:
                return found
    return None


def _find_value(node: object, name: str) -> object:
    if isinstance(node, dict):
        if name in node and not isinstance(node[name], (dict, list)):
            return node[name]
        for value in node.values():
            found = _find_value(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_value(value, name)
            if found is not None:
                return found
    return None


def summarize_json(body: bytes, ok_code: str) -> None:
    try:
        root = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        print("JSON이 아닙니다. 앞부분:", body[:300].decode("utf-8", "replace"))
        return
    for tag in ("resultCode", "resultMsg", "totalCount"):
        value = _find_value(root, tag)
        if value is not None:
            print(f"{tag}: {value}")
    if str(_find_value(root, "resultCode")) != ok_code:
        print(f"경고: 정상 응답(resultCode {ok_code})이 아닙니다. 인증키·파라미터를 확인하고 이 샘플은 근거로 쓰지 마세요.")
    items = [item for item in (_find_items(root) or []) if isinstance(item, dict)]
    print(f"item 수: {len(items)}")
    fields = Counter(name for item in items for name, value in item.items() if value not in (None, ""))
    for name in sorted({name for item in items for name in item}):
        print(f"  {name}  ({fields[name]}/{len(items)}건에 값 있음)")


def summarize(body: bytes) -> None:
    if has_dtd(body):
        print("DOCTYPE 선언이 있는 응답이라 구조 요약을 건너뜁니다. 원본 파일만 확인하세요.")
        return
    try:
        root = ET.fromstring(body)  # nosec B314 - has_dtd()로 DOCTYPE 선언이 없음을 확인했다
    except ET.ParseError:
        print("XML이 아닙니다. 앞부분:", body[:300].decode("utf-8", "replace"))
        return

    status = {}
    for tag in STATUS_TAGS:
        node = root.find(f".//{tag}")
        if node is not None and node.text:
            status[tag] = node.text.strip()
            print(f"{tag}: {status[tag]}")
    if status.get("resultCode") != "00":
        print("경고: 정상 응답(resultCode 00)이 아닙니다. 인증키·일일 한도·파라미터를 확인하고 이 샘플은 근거로 쓰지 마세요.")

    items = root.findall(".//item")
    print(f"item 수: {len(items)}")
    # item마다 태그를 한 번만 세고, 빈 요소(<tag/>)는 값 없음으로 본다.
    fields = Counter(tag for item in items for tag in {c.tag for c in item if c.text and c.text.strip()})
    all_tags = sorted({c.tag for item in items for c in item})
    for tag in all_tags:
        print(f"  {tag}  ({fields[tag]}/{len(items)}건에 값 있음)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--operation", required=True, help="API 오퍼레이션명 (예: getJobList)")
    parser.add_argument("--param", action="append", default=[], help="추가 요청 변수 name=value")
    args = parser.parse_args()

    source = SOURCES[args.source]
    if not OPERATION_RE.fullmatch(args.operation):
        raise SystemExit("오퍼레이션명은 영문·숫자만 허용합니다.")
    if "operations" in source and args.operation not in source["operations"]:
        raise SystemExit(f"{args.source}의 오퍼레이션은 {', '.join(source['operations'])} 중 하나입니다.")

    load_dotenv(REPO_ROOT / ".env")
    body = fetch(source, args.operation, parse_params(args.param))

    out_dir = SAMPLE_DIR / args.source
    out_dir.mkdir(parents=True, exist_ok=True)
    # 같은 초에 --param만 바꿔 반복 호출해도 덮어쓰지 않도록 마이크로초까지 쓴다.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    is_json = source.get("format") == "json"
    out_path = out_dir / f"{stamp}-{args.operation}.{'json' if is_json else 'xml'}"
    out_path.write_bytes(body)
    print(f"저장: {out_path.relative_to(REPO_ROOT)}")
    if is_json:
        summarize_json(body, source["ok_code"])
    else:
        summarize(body)


if __name__ == "__main__":
    sys.exit(main())
