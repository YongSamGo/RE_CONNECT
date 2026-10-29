"""앱 밖의 관리 진입점: 보관기간이 지난 기록을 한 번에 정리하는 주기 실행 묶음 (W12-07).

각 정리 명령을 별도 프로세스로 차례로 실행한다. 한 단계가 실패해도 다음 단계는 계속 실행하고,
하나라도 실패하면 종료 코드 1로 알린다. 출력은 단계 이름·고정 상태·처리 건수뿐이며
하위 명령의 오류 원문·연결 정보는 옮기지 않는다.
"""

import argparse
import json
from pathlib import Path
import subprocess  # nosec B404 - 고정된 정리 명령만 현재 인터프리터로 실행하며 shell은 쓰지 않는다.
import sys

BACKEND = Path(__file__).resolve().parent
# 한 번 호출에 limit만큼만 지우는 명령은 같은 실행 안에서 반복한다. 남은 양이 많아도 하루 실행 시간을 묶는다.
MAX_ROUNDS = 20
STEP_TIMEOUT_SECONDS = 300
# (이름, 명령 인자, 한 번에 처리하는 상한 — 상한이 없으면 None)
STEPS = (
    ("deletion_records", ("manage_deletions.py", "prune"), None),
    ("report_details", ("manage_reports.py", "purge", "--limit", "100"), 100),
    ("audit_events", ("manage_audit.py", "prune"), None),
)


def run_command(args):
    """하위 명령의 마지막 JSON 줄을 읽는다. stderr는 버리고 해석할 수 없으면 None을 돌려준다."""
    try:
        completed = subprocess.run([sys.executable, *args], cwd=BACKEND, stdout=subprocess.PIPE,  # nosec B603 - argv는 STEPS 고정값이며 shell 없이 실행한다.
                                   stderr=subprocess.DEVNULL, timeout=STEP_TIMEOUT_SECONDS, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = completed.stdout.strip().splitlines()
    try:
        result = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    if completed.returncode != 0 or not isinstance(result, dict) or result.get("completed") is not True:
        return None
    processed = result.get("processed")
    return processed if isinstance(processed, int) and not isinstance(processed, bool) and processed >= 0 else None


def run_step(args, batch, runner=run_command):
    if not (BACKEND / args[0]).is_file():
        return {"status": "missing", "processed": 0}
    total = 0
    for _ in range(MAX_ROUNDS):
        processed = runner(args)
        if processed is None:
            return {"status": "failed", "processed": total}
        total += processed
        if batch is None or processed < batch:
            return {"status": "ok", "processed": total}
    # 상한까지 돌았는데도 남았을 수 있다. 성공으로 숨기지 않고 다음 실행에서 이어 지운다.
    return {"status": "incomplete", "processed": total}


def main(argv=None, runner=run_command):
    parser = argparse.ArgumentParser(description="보관기간이 지난 삭제 이력·신고 설명·감사 기록을 차례로 정리")
    parser.add_argument("command", choices=["run"])
    parser.parse_args(argv)
    results = [{"step": name, **run_step(args, batch, runner)} for name, args, batch in STEPS]
    print(json.dumps({"completed": all(r["status"] == "ok" for r in results), "steps": results}))
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
