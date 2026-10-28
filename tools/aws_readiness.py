"""AWS GPU 준비의 읽기 전용 사전 확인. 자원을 생성하거나 할당량을 요청하지 않는다."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import subprocess


QUOTA_CODE = "L-DB2E81BA"  # Running On-Demand G and VT instances (vCPU)


class ProbeError(Exception):
    pass


def aws_json(arguments, *, region, profile=None):
    command = ["aws", *arguments, "--region", region, "--output", "json", "--no-cli-pager"]
    if profile:
        command += ["--profile", profile]
    try:
        result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=30, check=True)
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except FileNotFoundError:
        raise ProbeError("aws_cli_missing") from None
    except subprocess.TimeoutExpired:
        raise ProbeError("aws_timeout") from None
    except (subprocess.CalledProcessError, UnicodeError, ValueError):
        # AWS 응답·stderr에는 계정 ID·ARN·호스트 등이 있을 수 있으므로 출력하지 않는다.
        raise ProbeError("aws_query_failed") from None


def inspect(region, instance_type, profile=None, *, query=aws_json):
    checks = []

    def record(name, state, **details):
        checks.append(dict(check=name, state=state, **details))

    def call(*args):
        return query(list(args), region=region, profile=profile)

    report = dict(
        checked_at=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        region=region, instance_type=instance_type, checks=checks,
        launch_ready=False,
        remaining=["root_mfa_and_team_access", "budget_and_operating_hours", "quota_headroom",
                   "actual_capacity", "private_rds_tls", "domain_https", "gpu_model_benchmark"],
    )
    try:
        identity = call("sts", "get-caller-identity")
        arn = identity.get("Arn")
        if not isinstance(arn, str) or not arn.startswith("arn:"):
            raise ProbeError("invalid_identity_response")
        if arn.endswith(":root"):
            record("identity", "blocked", reason="root_credentials")
            return report
        record("identity", "pass")
    except ProbeError as exc:
        record("identity", "unknown", reason=str(exc))
        return report

    vcpus = None
    try:
        data = call("ec2", "describe-instance-types", "--instance-types", instance_type)
        types = data.get("InstanceTypes", [])
        if len(types) != 1 or types[0].get("InstanceType") != instance_type:
            raise ProbeError("invalid_instance_response")
        spec = types[0]
        vcpus = spec.get("VCpuInfo", {}).get("DefaultVCpus")
        memory = spec.get("MemoryInfo", {}).get("SizeInMiB")
        gpu_memory = spec.get("GpuInfo", {}).get("TotalGpuMemoryInMiB")
        if any(type(value) is not int or value <= 0 for value in (vcpus, memory, gpu_memory)):
            raise ProbeError("invalid_instance_response")
        record("instance_spec", "pass", vcpus=vcpus, memory_mib=memory, gpu_memory_mib=gpu_memory)
    except ProbeError as exc:
        vcpus = None
        record("instance_spec", "unknown", reason=str(exc))

    try:
        data = call("ec2", "describe-instance-type-offerings", "--location-type", "region",
                    "--filters", f"Name=instance-type,Values={instance_type}", f"Name=location,Values={region}")
        offered = any(item.get("InstanceType") == instance_type and item.get("Location") == region
                      for item in data.get("InstanceTypeOfferings", []))
        record("region_offering", "pass" if offered else "blocked")
    except ProbeError as exc:
        record("region_offering", "unknown", reason=str(exc))

    try:
        data = call("service-quotas", "get-service-quota", "--service-code", "ec2", "--quota-code", QUOTA_CODE)
        value = data.get("Quota", {}).get("Value")
        if type(value) not in (int, float) or value < 0 or not value < float("inf"):
            raise ProbeError("invalid_quota_response")
        # 승인 한도와 단일 후보의 크기만 비교한다. 이미 쓰는 다른 GPU의 점유는 별도 확인한다.
        state = "unknown" if vcpus is None else ("pass" if value >= vcpus else "blocked")
        record("on_demand_quota", state, approved_vcpus=value, candidate_vcpus=vcpus)
    except ProbeError as exc:
        record("on_demand_quota", "unknown", reason=str(exc))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--instance-type", default="g5.xlarge")
    parser.add_argument("--profile")
    args = parser.parse_args()
    if re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-[0-9]+", args.region) is None:
        parser.error("region 형식을 확인하세요")
    if re.fullmatch(r"(?:g4dn|g5|g6|g6e)\.(?:xlarge|[0-9]+xlarge)", args.instance_type) is None:
        parser.error("CUDA 후보 g4dn/g5/g6/g6e 인스턴스를 지정하세요")
    if args.profile and (args.profile.startswith("-") or len(args.profile) > 128):
        parser.error("profile 형식을 확인하세요")
    report = inspect(args.region, args.instance_type, args.profile)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    # 0도 배포 허가가 아니다. 읽기 전용 세 가지 사전 조건을 확인했다는 뜻이다.
    return 0 if all(item["state"] == "pass" for item in report["checks"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
