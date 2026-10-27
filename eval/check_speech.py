"""녹음한 평가 대본으로 STT를 돌리고 채점한다 (W01-07 · #10, #31·#34에서 사용).

1) 전사: 녹음 폴더의 `<사례 ID>.<wav|webm|ogg|m4a>`를 내부 음성 서비스(`POST /internal/transcriptions`)에 보내
   전사·길이·지연을 JSON으로 저장한다. 음성 서비스와 같은 내부 네트워크(EC2)에서 돌린다.
2) 채점: 전사 JSON을 `speech_cases.json`과 대조한다.
   - 문자 오류율(CER): 띄어쓰기·문장부호를 빼고, 한글 숫자를 아라비아 숫자로 바꾼 뒤 계산한다.
   - 핵심어: `keywords`가 전사에 남았는지. 놓친 핵심어를 사례별로 보여 준다.
   - 필터: 원문이 개인정보 필터에서 막히는 문장(`filter: exclude`)이 전사 후 통과하면 실패다.

필터 실패가 있으면 종료 코드 1이다. CER·핵심어는 기준값 없이 기록만 한다(EC2 실측 전 합격선을 정하지 않는다).
녹음·전사 파일은 커밋하지 않는 `security-reports/speech/`에 둔다(docs/ai/speech-eval.md).

사용법 (저장소 최상위에서):
    python -I eval/check_speech.py script                                  # 녹음 대본
    python -I eval/check_speech.py transcribe security-reports/speech/<녹음자>/ --out security-reports/speech/<녹음자>.json
    backend/.venv/bin/python -I eval/check_speech.py score security-reports/speech/<녹음자>.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {case["id"]: case for case in
         json.loads((ROOT / "eval/speech_cases.json").read_text(encoding="utf-8"))["cases"]}
# 녹음 한도(Plan/05 §4): 1회 90초·6MiB. 음성 서비스가 받는 형식만 보낸다.
MAX_BYTES = 6 * 1024 * 1024
MEDIA_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
DIGITS = dict(zip("공영일이삼사오육칠팔구", "00123456789"))
UNITS = {"십": 10, "백": 100, "천": 1000}


def korean_number(word: str) -> str:
    """'삼십오' → '35', '천구백오십팔' → '1958', '공일공' → '010'. 숫자 단위가 없으면 자리별로 읽는다."""
    if not any(char in UNITS for char in word):
        return "".join(DIGITS[char] for char in word)
    total, digit = 0, None
    for char in word:
        if char in UNITS:
            total += (digit or 1) * UNITS[char]
            digit = None
        else:
            digit = int(DIGITS[char])
    return str(total + (digit or 0))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # 낱말 첫머리에서 단위어 앞에 오는 한글 숫자만 바꾼다. "이용"·"동안구 살고"의 "구"는 숫자가 아니다.
    text = re.sub(r"(?<![가-힣])[공영일이삼사오육칠팔구십백천]+(?=\s*(?:년|살|시간|시|분|세|급|회|명|월|일|번|층))",
                  lambda m: korean_number(m.group()), text)
    return re.sub(r"[\s\W_]+", "", text)


def edit_distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (x != y))
    return row[-1]


def transcribe(folder: Path, service: str, out: Path) -> int:
    results = {}
    for path in sorted(folder.iterdir()):
        media_type = MEDIA_TYPES.get(path.suffix.lower())
        if path.stem not in CASES or media_type is None:
            print("건너뜀(사례 ID·형식 아님):", path.name)
            continue
        body = path.read_bytes()
        if len(body) > MAX_BYTES:
            print("건너뜀(6MiB 초과):", path.name)
            continue
        request = urllib.request.Request(service.rstrip("/") + "/internal/transcriptions", data=body, method="POST",
                                         headers={"Content-Type": media_type, "X-Speech-Request-ID": str(uuid.uuid4())})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - 운영자가 지정한 내부 음성 서비스
                payload = json.loads(response.read(64 * 1024))
            results[path.stem] = {"text": payload["text"], "duration_seconds": payload["duration_seconds"],
                                  "latency_seconds": round(time.monotonic() - started, 3)}
        except Exception as error:  # 원문·응답 본문은 출력하지 않는다.
            results[path.stem] = {"error": type(error).__name__}
        print(path.stem, "완료" if "text" in results[path.stem] else results[path.stem]["error"])
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(results)}건 저장: {out}")
    return 0


def score(path: Path) -> int:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.modules.generation.privacy import safe_text

    results = json.loads(path.read_text(encoding="utf-8"))
    rates, latencies, leaks = [], [], []
    print("| 사례 | 원문 | CER | 놓친 핵심어 | 필터 |\n|---|---|---|---|---|")
    for case_id, case in CASES.items():
        result = results.get(case_id)
        if result is None or "text" not in result:
            print(f"| {case_id} | {case['source']} | — | 전사 없음({(result or {}).get('error', '녹음 없음')}) | — |")
            continue
        expected, actual = normalize(case["text"]), normalize(result["text"])
        rate = edit_distance(expected, actual) / max(len(expected), 1)
        rates.append(rate)
        if "latency_seconds" in result:
            latencies.append(result["latency_seconds"])
        missed = [word for word in case["keywords"] if normalize(word) not in actual]
        passed = safe_text(result["text"]) is not None
        leak = case["filter"] == "exclude" and passed
        if leak:
            leaks.append(case_id)
        print(f"| {case_id} | {case['source']} | {rate:.1%} | {', '.join(missed) or '—'} | "
              f"{'**통과(유출)**' if leak else ('제외' if not passed else '통과')} |")
    if rates:
        print(f"\n전사 {len(rates)}/{len(CASES)}건, CER 평균 {statistics.mean(rates):.1%}, 중앙값 {statistics.median(rates):.1%}")
    if latencies:
        print(f"지연 중앙값 {statistics.median(latencies):.2f}초, 최대 {max(latencies):.2f}초")
    for case_id in leaks:
        print(f"필터 실패: {case_id}({CASES[case_id]['source']})는 원문이 제외 대상인데 전사가 필터를 통과함")
    return 1 if leaks else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("script", help="녹음 대본 출력(사례 ID와 읽을 문장)")
    run = commands.add_parser("transcribe", help="녹음 폴더를 내부 음성 서비스로 전사")
    run.add_argument("folder", type=Path)
    run.add_argument("--service", default="http://speech:8001", help="내부 음성 서비스 주소")
    run.add_argument("--out", type=Path, required=True)
    check = commands.add_parser("score", help="전사 JSON 채점")
    check.add_argument("transcripts", type=Path)
    args = parser.parse_args()
    if args.command == "script":
        for case_id, case in CASES.items():
            print(case_id, case["text"], sep="\t")
        return 0
    if args.command == "transcribe":
        return transcribe(args.folder, args.service, args.out)
    return score(args.transcripts)


if __name__ == "__main__":
    sys.exit(main())
