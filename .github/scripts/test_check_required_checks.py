"""Regression cases for the branch-protection aggregate check."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("check_required_checks.py")
SPEC = importlib.util.spec_from_file_location("check_required_checks", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def jobs(**overrides):
    base = {name: {"result": "success"} for name in module.BASE_REQUIRED_JOBS}
    base["dependency-review"] = {"result": "success"}
    base.update(overrides)
    return base


class RequiredChecksTests(unittest.TestCase):
    def test_all_required_jobs_pass(self):
        self.assertEqual(module.evaluate(jobs(), "pull_request"), [])

    def test_missing_required_manifest_fails_even_when_jobs_are_skipped(self):
        errors = module.evaluate(jobs(python={"result": "skipped"}), "push", "speech/requirements.txt")
        self.assertTrue(any("필수 매니페스트 누락" in error for error in errors))
        self.assertTrue(any("python" in error and "skipped" in error for error in errors))

    def test_required_job_skip_fails(self):
        errors = module.evaluate(jobs(frontend={"result": "skipped"}), "pull_request")
        self.assertTrue(any("frontend" in error for error in errors))

    def test_failed_and_cancelled_required_jobs_fail(self):
        errors = module.evaluate(jobs(persistence={"result": "failure"}, secrets={"result": "cancelled"}), "push")
        self.assertEqual(len(errors), 2)

    def test_dependency_review_skip_is_valid_on_push_but_not_pr(self):
        state = jobs(**{"dependency-review": {"result": "skipped"}})
        self.assertEqual(module.evaluate(state, "push"), [])
        self.assertTrue(any("dependency-review" in error for error in module.evaluate(state, "pull_request")))

    def test_missing_status_is_not_success(self):
        state = jobs()
        del state["python"]
        self.assertTrue(any("python" in error and "missing" in error for error in module.evaluate(state, "push")))


if __name__ == "__main__":
    unittest.main()
