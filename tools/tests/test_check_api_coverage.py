import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.check_api_coverage import canonical_operations, compare_operations, failure_status, print_operations


class ApiCoverageTests(unittest.TestCase):
    def test_reads_only_path_operations_and_applies_server_base(self):
        fixture = """openapi: 3.1.0
paths:
  /profiles/me:
    get:
      summary: nested text must not become a method
      responses: {}
    delete:
      responses: {}
  /admin/reports:
    post:
      responses: {}
  /health/live:
    get:
      responses: {}
components:
  /not-a-path:
    get:
      responses: {}
"""
        self.assertEqual(canonical_operations(fixture), {
            ("/api/v1/profiles/me", "GET"),
            ("/api/v1/profiles/me", "DELETE"),
            ("/api/v1/admin/reports", "POST"),
            ("/health/live", "GET"),
        })

    def test_missing_canonical_route_is_reported_and_strict_fails(self):
        canonical = {("/api/v1/reports", "POST"), ("/api/v1/admin/audit", "GET")}
        actual = {("/api/v1/reports", "POST")}
        missing, extra = compare_operations(canonical, actual)
        self.assertEqual(missing, [("/api/v1/admin/audit", "GET")])
        self.assertEqual(extra, [])
        self.assertEqual(failure_status(strict=True, missing=missing), 1)

    def test_report_only_does_not_fail_for_missing_canonical_route(self):
        self.assertEqual(failure_status(strict=False, missing=[("/api/v1/x", "GET")]), 0)

    def test_output_keeps_methods_and_admin_paths_in_their_columns(self):
        output = StringIO()
        with redirect_stdout(output):
            print_operations(
                [("/api/v1/admin/reports", "GET"), ("/api/v1/reports", "POST")],
                [("/api/v1/extra", "PATCH")], {("/health/live", "GET")},
            )
        self.assertEqual(output.getvalue().splitlines(), [
            "미구현 admin: GET /api/v1/admin/reports",
            "미구현 계약: POST /api/v1/reports",
            "계약 외 실제 라우트: PATCH /api/v1/extra",
            "스키마 제외 분류: GET /health/live",
        ])


if __name__ == "__main__":
    unittest.main()
