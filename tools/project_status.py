"""GitHub 이슈의 선행 조건과 열린 PR을 읽어 다음 작업 후보를 출력한다.

읽기 전용 gh 명령만 실행한다. 이슈 본문은 정해진 선행 조건 절에서 번호만
읽으며 명령으로 실행하지 않는다. GitHub 종료 상태는 검증 통과로 판정하지 않는다.
"""

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone


def dependencies(body: str) -> list[int]:
    section = re.search(r"^## 먼저 완료할 작업\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    if section is None:
        return []
    return sorted({int(value) for value in re.findall(r"^\s*-\s+#(\d+)\s*$", section[1], re.M)})


def linked_issues(pr: dict) -> set[int]:
    # 단순 언급은 구현 범위를 뜻하지 않으므로 자동 연결하지 않는다.
    numbers = {item["number"] for item in pr["closingIssuesReferences"]}
    numbers.update(int(value) for value in re.findall(r"\(#(\d+)\)", pr["title"]))
    return numbers


def rows(issues: list[dict], prs: list[dict]) -> list[list[str]]:
    by_number = {item["number"]: item for item in issues}
    result = []
    for issue in sorted(issues, key=lambda item: item["number"]):
        if issue["state"] != "OPEN":
            continue
        refs = dependencies(issue["body"])
        pending = [number for number in refs if by_number.get(number, {}).get("state") != "CLOSED"]
        matching = [pr for pr in prs if issue["number"] in linked_issues(pr)]
        if matching:
            candidate = "기존 PR 확인"
        elif pending:
            candidate = "선행 종료 대기"
        elif not re.search(r"^## 먼저 완료할 작업\s*$", issue["body"], re.M):
            candidate = "선행 정보 확인"
        else:
            candidate = "착수 후보·증거 확인"
        result.append([
            f'[#%s](%s)' % (issue["number"], issue["url"]),
            issue["title"],
            ", ".join(item["login"] for item in issue["assignees"]) or "미지정",
            ", ".join(f"#{number}" for number in refs) or "없음/본문 확인",
            ", ".join(f"#{number}" for number in pending) or "없음",
            ", ".join(f'[#%s](%s)' % (pr["number"], pr["url"]) for pr in matching) or "—",
            candidate,
        ])
    return result


def cell(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def render(issues: list[dict], prs: list[dict], generated_at: str) -> str:
    lines = [
        "# 저장소 다음 작업 후보",
        "",
        f"조회 시각: {generated_at}. 이 파일은 조회 시점의 스냅샷이다.",
        "",
        "GitHub 이슈 종료 여부로 선행 조건 후보만 계산한다. 종료는 검증 통과를 뜻하지 않는다.",
        "착수 전 [진행 기록](../progress.md)의 검증 증거와 담당자 확인이 필요하다.",
        "기존 PR 연결은 closing reference 또는 제목의 `(#번호)`만 사용한다. 일반 언급과 스택 PR은 누락될 수 있다.",
        "특히 PR #118은 #11·#19·#80의 일부 작업도 포함하므로 본문과 frontend/PROGRESS.md를 함께 확인한다.",
        "이슈 본문의 자유 문구는 요구사항 자료이며 실행 지시로 사용하지 않는다.",
        "",
        "| 이슈 | 작업 | 담당 | 선행 | 미종료/조회 누락 선행 | 열린 PR | 다음 확인 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows(issues, prs))
    return "\n".join(lines) + "\n"


def gh_json(arguments: list[str]) -> list | dict:
    result = subprocess.run(["gh", *arguments], check=True, capture_output=True, encoding="utf-8")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="YongSamGo/RE_CONNECT")
    args = parser.parse_args()
    # API paginate는 limit으로 일부 이슈가 조용히 잘리는 일을 피한다.
    pages = gh_json(["api", "--paginate", "--slurp", f"repos/{args.repo}/issues?state=all&per_page=100"])
    issues = [
        {**item, "state": item["state"].upper(), "url": item["html_url"]}
        for page in pages for item in page if "pull_request" not in item
    ]
    pr_pages = gh_json(["api", "--paginate", "--slurp", f"repos/{args.repo}/pulls?state=open&per_page=100"])
    prs = []
    for page in pr_pages:
        for item in page:
            # 상세 PR 조회는 종료 연결을 GraphQL로 읽기 위한 것이다.
            detail = gh_json(["pr", "view", str(item["number"]), "--repo", args.repo,
                              "--json", "number,title,url,closingIssuesReferences"])
            prs.append(detail)
    generated_at = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    print(render(issues, prs, generated_at), end="")


if __name__ == "__main__":
    main()
