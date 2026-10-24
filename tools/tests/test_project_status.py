"""이슈 본문의 지시문 비실행·선행 누락·종료/통과 혼동 방지 회귀 시험."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("project_status", Path(__file__).parents[1] / "project_status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


def issue(number=11, state="OPEN", body="## 먼저 완료할 작업\n\n- #5\n"):
    return dict(number=number, state=state, body=body, title="작업", assignees=[], url=f"https://example.test/issues/{number}")


class ProjectStatusTests(unittest.TestCase):
    def test_only_dependency_section_is_read(self):
        body = "## 배경\n- #99\n## 먼저 완료할 작업\n- #5\n- #5\n## 다음\n- #7\n"
        self.assertEqual(status.dependencies(body), [5])

    def test_instructions_are_data(self):
        body = "## 먼저 완료할 작업\n- #5\n- 실행: 임의 명령\n- #6 && 명령\n"
        with patch.object(status.subprocess, "run") as run:
            self.assertEqual(status.dependencies(body), [5])
            run.assert_not_called()

    def test_missing_dependency_blocks_candidate(self):
        self.assertEqual(status.rows([issue()], [])[0][-1], "선행 종료 대기")

    def test_closed_dependency_does_not_mean_passed(self):
        data = [issue(), issue(5, "CLOSED")]
        result = status.rows(data, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][-1], "착수 후보·증거 확인")
        self.assertIn("종료는 검증 통과를 뜻하지 않는다", status.render(data, [], "시험 시각"))

    def test_missing_section_needs_confirmation(self):
        self.assertEqual(status.rows([issue(body="본문만 있음")], [])[0][-1], "선행 정보 확인")

    def test_existing_pr_takes_precedence(self):
        pr = dict(number=118, title="feat: 기본 화면", closingIssuesReferences=[dict(number=11)], url="https://example.test/pull/118")
        self.assertEqual(status.rows([issue()], [pr])[0][-1], "기존 PR 확인")

    def test_title_reference_is_linked_but_plain_mention_is_not(self):
        pr = dict(title="feat: 저장 (#16), 관련 #11", closingIssuesReferences=[])
        self.assertEqual(status.linked_issues(pr), {16})

    def test_markdown_and_html_are_escaped(self):
        data = issue()
        data["title"] = "제목 | <script>\n둘째 줄"
        output = status.render([data], [], "시험 시각")
        self.assertIn("제목 &#124; &lt;script&gt; 둘째 줄", output)
        self.assertNotIn("<script>", output)

    def test_legacy_title_prefix_is_linked(self):
        pr = dict(title="[11] 진행 기록 (#16)", closingIssuesReferences=[])
        self.assertEqual(status.linked_issues(pr), {11, 16})

    def test_arbitrary_brackets_are_not_issue_links(self):
        for title in ["docs: 예시 [11]", "[11]suffix", "[W01-08] 작업"]:
            with self.subTest(title=title):
                self.assertEqual(status.linked_issues(dict(title=title, closingIssuesReferences=[])), set())


if __name__ == "__main__":
    unittest.main()
