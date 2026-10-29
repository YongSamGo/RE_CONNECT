"""저장소 텍스트 파일의 숨은 문자와 에이전트 지시 파일의 의심 문구를 검사한다.

AI 개발 도구(Claude Code, Codex 등)는 사람이 화면에서 보지 못하는 문자도 그대로 읽는다.
폭 없는 문자·글자 방향 제어·태그 문자로 숨긴 문장은 리뷰를 통과한 뒤 도구를 조종할 수 있다.

1. 숨은 문자 (실패): git이 추적하는 모든 텍스트 파일과 경로 이름
   - 제어 문자 (탭·줄바꿈 제외), 서식 문자(유니코드 Cf: 폭 없는 문자·글자 방향 제어·태그 문자 등)
   - 한글 채움 문자, 점자 빈칸, 연속된 이체 선택자(variation selector) 등 보이지 않는 글자
   - 허용: 파일 맨 앞 BOM, 이모지 사이의 ZWJ, 글자 뒤 이체 선택자 1개(이모지 표시용), 줄 끝 CRLF
   - NUL이 있거나 UTF-8로 읽히지 않는 텍스트 파일도 실패 (UTF-16 등으로 검사를 피하지 못하게).
     바이너리는 BINARY_EXTENSIONS 확장자나 .gitattributes의 binary로 지정한다
2. 에이전트 지시 파일 설정 (실패, 파일을 지정하지 않고 저장소 전체를 볼 때): 지시 파일이 심볼릭 링크이거나
   .gitattributes의 -diff·binary·linguist-generated로 PR 화면과 의심 문구 검사에서 내용이 숨겨지는 경우
3. 의심 문구 (경고, --diff-base를 줄 때만): 에이전트 지시 파일에 새로 추가된 줄의
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
    (0x2028, 0x2029),    # LINE/PARAGRAPH SEPARATOR (편집기·터미널마다 줄바꿈으로 보이거나 안 보임)
    (0x2800, 0x2800),    # BRAILLE PATTERN BLANK
    (0x3164, 0x3164),    # HANGUL FILLER
    (0xFE00, 0xFE0F),    # VARIATION SELECTOR-1~16 (글자 뒤 1개는 아래에서 허용)
    (0xFFA0, 0xFFA0),    # HALFWIDTH HANGUL FILLER
    (0xE0100, 0xE01EF),  # VARIATION SELECTOR-17~256 (데이터 숨기기에 쓰임)
]
ALLOWED_CONTROLS = {"\t", "\n"}  # CR은 CRLF일 때만 _allowed에서 허용
PATH_CONTROLS = re.compile("[\t\n\r]")
ZWJ = "\u200d"
BOM = "\ufeff"


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
    if ch == "\r":
        # 단독 CR은 터미널에서 커서를 줄 앞으로 돌려 앞 문장을 가린다
        return i + 1 < len(text) and text[i + 1] == "\n"
    if ch in ("\ufe0e", "\ufe0f"):
        # 이모지·기호 뒤 1개는 표시 방식 선택이다. 연속되면 데이터를 숨긴 것으로 본다.
        return i > 0 and not HIDDEN.match(text[i - 1])
    if ch == ZWJ:
        # 이모지 결합(예: 여성 + ZWJ + 컴퓨터 = 개발자 이모지)만 허용
        j = i - 1
        while j >= 0 and _is_variation_selector(text[j]):
            j -= 1
        return j >= 0 and i + 1 < len(text) and _is_emoji(text[j]) and _is_emoji(text[i + 1])
    return False


def _describe(ch: str) -> str:
    fallback = "CONTROL" if unicodedata.category(ch) == "Cc" else "UNNAMED"
    return f"U+{ord(ch):04X} {unicodedata.name(ch, fallback)}"


def _git(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(["git", *args], capture_output=True, check=True,
                            input=stdin.encode("utf-8") if stdin is not None else None)
    return result.stdout.decode("utf-8", "replace")


def _escape_command_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _report(level: str, path: str, line: int, col: int, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # 워크플로 명령은 값의 %·CR·LF(속성값은 :·,도)를 바꿔야 다음 줄에 다른 명령이 끼어들지 않는다
        safe_path = _escape_command_data(path).replace(",", "%2C").replace(":", "%3A")
        print(f"::{level} file={safe_path},line={line},col={col}::{_escape_command_data(message)}")
    else:
        shown = repr(path) if PATH_CONTROLS.search(path) else path
        print(f"{shown}:{line}:{col}: {level}: {message}")


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


def _marked_binary(path: str) -> bool:
    """.gitattributes에서 binary로 지정한 파일인가 (저장소 밖 경로면 False)."""
    try:
        out = _git("check-attr", "binary", "--", path)
    except (subprocess.CalledProcessError, OSError):
        return False
    return out.rstrip().endswith(": set")


def check_files(paths: list[str]) -> tuple[int, Counter[str]]:
    errors, kinds = 0, Counter()
    for path in paths:
        path_issues = [desc for _, _, desc in find_hidden(path)]
        if PATH_CONTROLS.search(path):
            path_issues.append("탭·줄바꿈·CR")
        for desc in path_issues:
            _report("error", path, 1, 1, f"파일 경로에 숨은 문자 {desc}")
            errors += 1
            kinds[desc.split(" 외 ")[0]] += 1
        if os.path.splitext(path)[1].lower() in BINARY_EXTENSIONS or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        # 텍스트 파일은 UTF-8만 허용한다. UTF-16·잘못된 바이트로 검사를 피하지 못하게 실패로 본다.
        # 진짜 바이너리는 BINARY_EXTENSIONS나 .gitattributes의 binary로 지정한다.
        problem = None
        if b"\0" in data:
            problem = "NUL 바이트 (UTF-16 등 UTF-8이 아닌 인코딩)"
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                problem = f"UTF-8로 읽을 수 없음 ({exc.reason}, {exc.start}바이트)"
        if problem:
            if _marked_binary(path):
                continue
            _report("error", path, 1, 1, f"{problem}. UTF-8로 저장하거나, 바이너리면 .gitattributes에 binary로 지정하세요")
            errors += 1
            kinds["UTF-8이 아닌 텍스트 파일"] += 1
            continue
        for line, col, desc in find_hidden(text):
            _report("error", path, line, col, f"숨은 문자 {desc}")
            errors += 1
            kinds[desc.split(" 외 ")[0]] += 1
    return errors, kinds


# ── 에이전트 지시 파일의 의심 문구 (경고) ──

# 하위 폴더에서 도구를 열면 그 폴더의 지시 파일도 쓰이므로 어느 깊이든 본다. .github/CODEOWNERS와 같은 범위.
AGENT_PATHSPECS = [
    ":(glob)**/.claude/**", ":(glob)**/.codex/**", ":(glob)**/.cursor/**", ":(glob)**/.gemini/**",
    ":(glob)**/CLAUDE.md", ":(glob)**/CLAUDE.local.md", ":(glob)**/AGENTS.md", ":(glob)**/AGENTS.override.md",
    ":(glob)**/GEMINI.md", ":(glob)**/.mcp.json", ":(glob)**/.vscode/mcp.json", ":(glob)**/.cursorrules", ":(glob)**/.windsurfrules",
    ":(glob).github/copilot-instructions.md", ":(glob).github/instructions/**", ":(glob).github/prompts/**",
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


def _added_lines(base: str, path: str):
    """base 대비 path에 추가된 (줄 번호, 내용). diff 헤더는 첫 hunk 앞에만 있으므로 그 뒤의 '+' 줄은 모두 내용이다."""
    # --text: .gitattributes의 -diff·binary가 걸려 있어도 "Binary files differ"로 넘기지 않고 내용을 본다
    diff = _git("diff", "--text", "--unified=0", "--no-color", "--no-ext-diff", base, "HEAD",
                "--", f":(literal){path}")
    in_hunk, line_no = False, 0
    for raw in diff.splitlines():
        hunk = HUNK.match(raw)
        if hunk:
            in_hunk, line_no = True, int(hunk.group(1))
            continue
        if in_hunk and raw.startswith("+"):
            yield line_no, raw[1:]
            line_no += 1


def _hides_content(attr: str, value: str) -> bool:
    if attr == "diff":
        return value not in ("unspecified", "set")  # -diff, 사용자 지정 diff 드라이버
    if attr == "binary":
        return value == "set"
    return value not in ("unspecified", "unset", "false")  # linguist-generated: PR 화면에서 diff를 접는다


def check_agent_files() -> int:
    """지시 파일이 심볼릭 링크이거나 .gitattributes로 내용이 숨겨지면 실패로 보고한다 (AGT-02·03)."""
    errors, paths = 0, []
    for entry in _git("ls-files", "-s", "-z", "--", *AGENT_PATHSPECS).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        paths.append(path)
        if meta.startswith("120000"):
            _report("error", path, 1, 1,
                    "에이전트 지시 파일이 심볼릭 링크임. 링크 대상은 의심 문구 검사·CODEOWNERS 밖이므로 실제 파일로 두세요 (AGT-02)")
            errors += 1
    if not paths:
        return errors
    out = _git("check-attr", "--stdin", "-z", "diff", "binary", "linguist-generated", stdin="\0".join(paths) + "\0")
    fields = out.split("\0")
    for path, attr, value in zip(fields[0::3], fields[1::3], fields[2::3]):
        if _hides_content(attr, value):
            _report("error", path, 1, 1,
                    f".gitattributes의 {attr}={value} 지정으로 PR 화면과 의심 문구 검사에서 지시 파일 내용이 숨겨짐. "
                    "지시 파일에는 이 속성을 쓰지 마세요 (AGT-02·03)")
            errors += 1
    return errors


def check_agent_diff(base: str) -> int:
    # 두 점 diff는 base가 앞서 나간 만큼(base에서 지운 줄)도 추가로 보이므로 갈라진 지점과 비교한다
    merge_base = _git("merge-base", base, "HEAD").strip()
    # 파일 목록을 -z로 받아 따옴표로 감싼 경로(", \, 제어 문자)도 빠뜨리지 않는다
    # T: 기존 지시 파일을 심볼릭 링크로 바꾸는 타입 변경도 포함한다
    files = _git("diff", "--name-only", "-z", "--diff-filter=AMRT", merge_base, "HEAD", "--", *AGENT_PATHSPECS)
    warnings = 0
    for path in (p for p in files.split("\0") if p):
        for line_no, added in _added_lines(merge_base, path):
            for label, pattern in SUSPICIOUS:
                if pattern.search(added):
                    _report("warning", path, line_no, 1,
                            f"에이전트 지시 파일에 '{label}'류 문구가 추가됨. 의도한 내용인지 리뷰에서 확인하세요 (AGT-03)")
                    warnings += 1
                    break
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
    if not args.paths:
        agent_errors = check_agent_files()
        if agent_errors:
            errors += agent_errors
            kinds["에이전트 지시 파일 숨김 설정"] += agent_errors

    warnings = check_agent_diff(args.diff_base) if args.diff_base else 0

    print(f"\n검사한 파일 {len(paths)}개: 실패 {errors}건, 의심 문구 경고 {warnings}건")
    for desc, count in kinds.most_common():
        print(f"  {count:>5}  {desc}")
    if errors:
        print("숨은 문자를 지우거나 UTF-8로 저장하고, 지시 파일의 숨김 설정을 없애세요. 대응 방법: docs/security/ci-pipeline.md '실패했을 때'")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
