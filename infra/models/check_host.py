"""Linux EC2 호스트의 swap/core dump 설정을 읽기 전용으로 검사한다."""
from pathlib import Path
import sys


def checks(root=Path("/proc")):
    return {
        "swap_disabled": len((root / "swaps").read_text().splitlines()) == 1,
        "core_discarded": (root / "sys/kernel/core_pattern").read_text().strip() == "/dev/null",
        "suid_dump_disabled": (root / "sys/fs/suid_dumpable").read_text().strip() == "0",
    }


def main():
    if sys.platform != "linux":
        print("host check requires Linux EC2")
        return 1
    try:
        result = checks()
    except OSError:
        print("host check unavailable")
        return 1
    for name, passed in result.items():
        print(name + ": " + ("ok" if passed else "fail"))
    return 0 if all(result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
