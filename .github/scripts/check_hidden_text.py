"""저장소 텍스트 파일의 숨은 문자와 에이전트 지시 파일의 의심 문구를 검사한다.

AI 개발 도구(Claude Code, Codex 등)는 사람이 화면에서 보지 못하는 문자도 그대로 읽는다.
폭 없는 문자·글자 방향 제어·태그 문자로 숨긴 문장은 리뷰를 통과한 뒤 도구를 조종할 수 있다.

1. 숨은 문자 (실패): git이 추적하는 모든 텍스트 파일과 경로 이름
   - 제어 문자 (탭·줄바꿈 제외), 서식 문자(유니코드 Cf: 폭 없는 문자·글자 방향 제어·태그 문자 등)
   - 한글 채움 문자, 점자 빈칸, 연속된 이체 선택자(variation selector) 등 보이지 않는 글자
   - 허용: 파일 맨 앞 BOM, 이모지 사이의 ZWJ, 글자 뒤 이체 선택자 1개(이모지 표시용)
2. 의심 문구 (경고, --diff-base를 줄 때만): 에이전트 지시 파일에 새로 추가된 줄의
   "이전 지시 무시", "사용자에게 알리지 마" 같은 문구. 보안 문서가 예시로 쓰는 경우가 있어 실패시키지 않는다.

표준 라이브러리만 쓴다. 점검 기준: .claude/skills/kisa-secure-coding-python/references/llm-security.md (AGT-01~03)

사용법 (저장소 최상위에서):
    python .github/scripts/check_hidden_text.py                   # 추적 중인 파일 전체
    python .github/scripts/check_hidden_text.py --diff-base HEAD^1 # + base 대비 추가된 줄의 의심 문구
    python .github/scripts/check_hidden_text.py 파일1 파일2        # 지정한 파일만
"""

from __future__ import annotations

import argparse
import bisect
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf",
    ".zip", ".gz", ".tgz", ".7z", ".whl", ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".wav", ".webm", ".ogg", ".so", ".dll", ".exe", ".pyc",
}

# 화면에 보이지 않거나 다른 글자처럼 보이게 만드는 문자 중 서식(Cf)·제어(Cc)가 아닌 것
EXTRA_INVISIBLE = [
    (0x034F, 0x034F),    # COMBINING GRAPHEME JOINER
    (0x115F, 0x1160),    # HANGUL CHOSEONG/JUNGSEONG FILLER
    (0x17B4, 0x17B5),    # KHMER VOWEL INHERENT AQ/AA
    (0x180B, 0x180F),    # MONGOLIAN FREE VARIATION SELECTOR
    (0x2800, 0x2800),    # BRAILLE PATTERN BLANK
    (0x3164, 0x3164),    # HANGUL FILLER
    (0xFE00, 0xFE0F),    # VARIATION SELECTOR-1~16 (글자 뒤 1개는 아래에서 허용)
    (0xFFA0, 0xFFA0),    # HALFWIDTH HANGUL FILLER
    (0xE0100, 0xE01EF),  # VARIATION SELECTOR-17~256 (데이터 숨기기에 쓰임)
]
ALLOWED_CONTROLS = {"\t", "\n", "\r"}
ZWJ = "‍"
BOM = "﻿"


def _build_pattern() -> re.Pattern[str]:
    flagged = set()
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        ch = chr(cp)
        cat = unicodedata.category(ch)
        if cat == "Cf" or (cat == "Cc" and ch not in ALLOWED_CONTROLS):
            flagged.add(cp)
    for start, end in EXTRA_INVISIBLE:
        flagged.update(range(start, end + 1))

    ranges, cps = [], sorted(flagged)
    start = prev = cps[0]
    for cp in cps[1:]:
        if cp != prev + 1:
            ranges.append((start, prev))
            start = cp
        prev = cp
    ranges.append((start, prev))
    body = "".join(
        re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}"
        for a, b in ranges
    )
    return re.compile(f"[{body}]")


HIDDEN = _build_pattern()


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF or 0x2B00 <= cp <= 0x2BFF


def _is_variation_selector(ch: str) -> bool:
    cp = ord(ch)
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


def _allowed(text: str, i: int) -> bool:
    ch = text[i]
    if ch == BOM:
        return i == 0
    if ch in ("︎", "️"):
        # 이모지·기호 뒤 1개는 표시 방식 선택이다. 연속되면 데이터를 숨긴 것으로 본다.
        return i > 0 and not HIDDEN.match(text[i - 1])
    if ch == ZWJ:
        # 👩‍💻 같은 이모지 결합만 허용
        j = i - 1
        while j >= 0 and _is_variation_selector(text[j]):
            j -= 1
        return j >= 0 and i + 1 < len(text) and _is_emoji(text[j]) and _is_emoji(text[i + 1])
    return False


def _describe(ch: str) -> str:
    fallback = "CONTROL" if unicodedata.category(ch) == "Cc" else "UNNAMED"
    return f"U+{ord(ch):04X} {unicodedata.name(ch, fallback)}"


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, check=True)
    return result.stdout.decode("utf-8")


def _report(level: str, path: str, line: int, col: int, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        safe_path = path.replace("%", "%25").replace(",", "%2C").replace(":", "%3A")
        print(f"::{level} file={safe_path},line={line},col={col}::{message}")
    else:
        print(f"{path}:{line}:{col}: {level}: {message}")


def find_hidden(text: str) -> list[tuple[int, int, str]]:
    """(줄, 열, 설명) 목록. 줄·열은 1부터 센다. 붙어 있는 숨은 문자는 한 건으로 묶는다."""
    found = []
    line_starts = None
    run_end = -1
    for match in HIDDEN.finditer(text):
        i = match.start()
        if _allowed(text, i):
            continue
        if i == run_end:
            run_end += 1
            line, col, desc, count = found[-1]
            found[-1] = (line, col, desc, count + 1)
            continue
        if line_starts is None:
            line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        line = bisect.bisect_right(line_starts, i) - 1
        found.append((line + 1, i - line_starts[line] + 1, _describe(text[i]), 1))
        run_end = i + 1
    return [
        (line, col, desc if count == 1 else f"{desc} 외 {count - 1}자 연속")
        for line, col, desc, count in found
    ]


def check_files(paths: list[str]) -> tuple[int, Counter[str]]:
    errors, kinds = 0, Counter()
    for path in paths:
        for _, _, desc in find_hidden(path):
            _report("error", path, 1, 1, f"파일 경로에 숨은 문자 {desc}")
            errors += 1
            kinds[desc.split(" 외 ")[0]] += 1
        if os.path.splitext(path)[1].lower() in BINARY_EXTENSIONS or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        if b"\0" in data[:8192]:
            continue  # 바이너리
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            _report("warning", path, 1, 1, f"UTF-8로 읽을 수 없어 검사하지 못함 ({exc.reason}, {exc.start}바이트)")
            continue
        for line, col, desc in find_hidden(text):
            _report("error", path, line, col, f"숨은 문자 {desc}")
            errors += 1
            kinds[desc.split(" 외 ")[0]] += 1
    return errors, kinds


# ── 에이전트 지시 파일의 의심 문구 (경고) ──

AGENT_PATHSPECS = [
    ":(glob).claude/**", ":(glob).codex/**", ":(glob).cursor/**",
    ":(glob).github/copilot-instructions.md", ":(glob).github/instructions/**", ":(glob).github/prompts/**",
    ":(glob)**/CLAUDE.md", ":(glob)**/CLAUDE.local.md", ":(glob)**/AGENTS.md", ":(glob)**/GEMINI.md",
    ":(glob).cursorrules", ":(glob).windsurfrules", ":(glob).mcp.json",
]

SUSPICIOUS = [
    ("지시 무시", re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|any|system)\b.{0,20}"
        r"\b(instructions?|prompts?|rules|guidelines|messages?)\b"
        r"|(이전|위의?|앞의?|기존|모든|지금까지)[^\n]{0,15}(지시|지침|명령|규칙|프롬프트)[^\n]{0,10}(무시|잊|따르지)",
        re.IGNORECASE)),
    ("사용자에게 숨김", re.compile(
        r"\b(do not|don't|never)\b.{0,20}\b(tell|inform|mention|reveal|show)\b.{0,20}\b(the )?(user|human|reviewer)s?\b"
        r"|(사용자|리뷰어|검토자)(에게|한테)[^\n]{0,15}(알리지|말하지|보여주지|숨기)",
        re.IGNORECASE)),
    ("권한 사칭", re.compile(
        r"\b(new|updated|real)\s+(system\s+)?instructions?\s*:|<\s*/?\s*(system|instructions?)\s*>|\[(system|admin)\]"
        r"|(시스템|관리자)\s*(지시|명령)\s*:",
        re.IGNORECASE)),
    ("비밀값 외부 전송", re.compile(
        r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|fetch)\b[^\n]{0,100}"
        r"(token|secret|password|\.env\b|api[_-]?key|GITHUB_TOKEN|ssh)",
        re.IGNORECASE)),
    ("권한 확인 우회", re.compile(
        r"--dangerously-skip-permissions|bypassPermissions|dangerouslyDisableSandbox|--yolo\b"
        r"|(확인|승인|허락)\s*(을|를)?\s*(받지|묻지)\s*(말고|않고)\s*(바로|즉시|곧바로)",
        re.IGNORECASE)),
]

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def check_agent_diff(base: str) -> int:
    diff = _git("-c", "core.quotepath=false", "diff", "--unified=0", "--no-color", "--no-ext-diff", "--diff-filter=AMR",
                base, "HEAD", "--", *AGENT_PATHSPECS)
    warnings, path, line_no = 0, None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else None
            continue
        hunk = HUNK.match(raw)
        if hunk:
            line_no = int(hunk.group(1))
            continue
        if path is None or not raw.startswith("+"):
            continue
        added = raw[1:]
        for label, pattern in SUSPICIOUS:
            if pattern.search(added):
                _report("warning", path, line_no, 1,
                        f"에이전트 지시 파일에 '{label}'류 문구가 추가됨. 의도한 내용인지 리뷰에서 확인하세요 (AGT-03)")
                warnings += 1
                break
        line_no += 1
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="숨은 문자(실패)와 에이전트 지시 파일 의심 문구(경고) 검사")
    parser.add_argument("paths", nargs="*", help="검사할 파일. 생략하면 git이 추적하는 파일 전체")
    parser.add_argument("--diff-base", metavar="REF",
                        help="이 커밋 대비 에이전트 지시 파일에 추가된 줄의 의심 문구를 경고한다")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글 출력

    paths = args.paths or [p for p in _git("ls-files", "-z").split("\0") if p]
    errors, kinds = check_files(paths)

    warnings = check_agent_diff(args.diff_base) if args.diff_base else 0

    print(f"\n검사한 파일 {len(paths)}개: 숨은 문자 {errors}건, 의심 문구 경고 {warnings}건")
    for desc, count in kinds.most_common():
        print(f"  {count:>5}  {desc}")
    if errors:
        print("숨은 문자를 지우세요. 대응 방법: docs/security/ci-pipeline.md '실패했을 때'")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
