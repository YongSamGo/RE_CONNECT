"""AWS 변경 호출 방지·루트 차단·부분 실패·비밀값 출력 방지 시험."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("aws_readiness", Path(__file__).parents[1] / "aws_readiness.py")
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


def response(arguments, **kwargs):
    service, operation = arguments[:2]
    if service == "sts":
        return {"Arn": "arn:aws:iam::000000000000:user/fixture"}
    if operation == "describe-instance-types":
        return {"InstanceTypes": [{"InstanceType": "g5.xlarge", "VCpuInfo": {"DefaultVCpus": 4},
                                  "MemoryInfo": {"SizeInMiB": 16384}, "GpuInfo": {"TotalGpuMemoryInMiB": 24576}}]}
    if operation == "describe-instance-type-offerings":
        return {"InstanceTypeOfferings": [{"InstanceType": "g5.xlarge", "Location": "ap-northeast-2"}]}
    return {"Quota": {"Value": 4.0}}


class ReadinessTests(unittest.TestCase):
    def inspect(self, query=response):
        return readiness.inspect("ap-northeast-2", "g5.xlarge", query=query)

    def test_success_does_not_claim_deployment_or_capacity(self):
        calls = []

        def query(args, **kwargs):
            calls.append(tuple(args[:2]))
            return response(args, **kwargs)

        report = self.inspect(query)
        self.assertTrue(all(item["state"] == "pass" for item in report["checks"]))
        self.assertFalse(report["launch_ready"])
        self.assertIn("actual_capacity", report["remaining"])
        self.assertIn("quota_headroom", report["remaining"])
        self.assertEqual(calls, [("sts", "get-caller-identity"), ("ec2", "describe-instance-types"),
                                 ("ec2", "describe-instance-type-offerings"), ("service-quotas", "get-service-quota")])
        self.assertNotIn("000000000000", json.dumps(report))
        self.assertNotIn("fixture", json.dumps(report))

    def test_root_credentials_stop_before_ec2(self):
        calls = []

        def query(args, **kwargs):
            calls.append(args)
            return {"Arn": "arn:aws:iam::000000000000:root"}

        report = self.inspect(query)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["checks"][0]["reason"], "root_credentials")

    def test_zero_quota_blocks_even_when_offered(self):
        def query(args, **kwargs):
            return {"Quota": {"Value": 0}} if args[0] == "service-quotas" else response(args, **kwargs)

        self.assertEqual(self.inspect(query)["checks"][-1]["state"], "blocked")

    def test_offering_is_checked_for_requested_region(self):
        def query(args, **kwargs):
            if args[1] == "describe-instance-type-offerings":
                return {"InstanceTypeOfferings": [{"InstanceType": "g5.xlarge", "Location": "other"}]}
            return response(args, **kwargs)

        self.assertEqual(self.inspect(query)["checks"][2]["state"], "blocked")

    def test_denied_spec_does_not_imply_sufficient_quota(self):
        def query(args, **kwargs):
            if args[1] == "describe-instance-types":
                raise readiness.ProbeError("aws_query_failed")
            return response(args, **kwargs)

        report = self.inspect(query)
        self.assertEqual(report["checks"][-1]["state"], "unknown")
        self.assertIsNone(report["checks"][-1]["candidate_vcpus"])

    def test_cli_error_never_exposes_stdout_stderr(self):
        error = subprocess.CalledProcessError(1, ["aws"], output="private-output", stderr="private-error")
        with patch.object(readiness.subprocess, "run", side_effect=error):
            with self.assertRaises(readiness.ProbeError) as caught:
                readiness.aws_json(["sts", "get-caller-identity"], region="ap-northeast-2")
        self.assertEqual(str(caught.exception), "aws_query_failed")

    def test_missing_cli_and_timeout_are_distinct(self):
        for error, reason in [(FileNotFoundError(), "aws_cli_missing"),
                              (subprocess.TimeoutExpired("aws", 30), "aws_timeout")]:
            with self.subTest(reason=reason), patch.object(readiness.subprocess, "run", side_effect=error):
                with self.assertRaises(readiness.ProbeError) as caught:
                    readiness.aws_json(["sts", "get-caller-identity"], region="ap-northeast-2")
                self.assertEqual(str(caught.exception), reason)

    def test_shell_is_not_used_and_profile_remains_one_argument(self):
        completed = subprocess.CompletedProcess([], 0, stdout="{}")
        with patch.object(readiness.subprocess, "run", return_value=completed) as run:
            readiness.aws_json(["sts", "get-caller-identity"], region="ap-northeast-2", profile="team profile")
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ["--profile", "team profile"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
