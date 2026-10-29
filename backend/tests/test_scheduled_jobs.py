"""주기 수집·보관 정리 묶음 (W12-07 · #96).

정상: 활성 출처만 코드 순서로 `--due` 실행, 정리 단계 반복·건수 합계, 타이머가 실제 명령을 호출.
공격·장애: 한 출처/단계 실패가 나머지를 막지 않음, 실패를 성공으로 숨기지 않음, 하위 명령의 오류 원문 비노출.
"""

import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, update

from app import collect
from app.modules.ingestion.runs import BASE_URLS
from app.modules.ingestion.runner import RunResult
from app.persistence.operations import Source
import manage_retention

INFRA = Path(__file__).resolve().parents[2] / "infra"


class FakeCollector:
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    async def run(self, source_id, **kwargs):
        self.calls.append((source_id, kwargs))
        outcome = self.outcomes[source_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_enabled_sources_reads_only_active_api_sources_in_code_order():
    engine = create_engine("sqlite://")
    Source.__table__.create(engine)
    volunteer, senuri = uuid4(), uuid4()
    with engine.begin() as db:
        db.execute(insert(Source), [
            {"id": volunteer, "code": "volunteer", "name": "봉사", "base_url": BASE_URLS["volunteer"], "enabled": True},
            {"id": senuri, "code": "senuri", "name": "노인 일자리", "base_url": BASE_URLS["senuri"], "enabled": True},
            # 수동 입력 출처는 활성이어도 API 수집 대상이 아니다(docs/data/manual-intake.md).
            {"id": uuid4(), "code": "manual_50plus", "name": "수동 입력", "base_url": "https://50plus.or.kr", "enabled": True},
        ])
    assert collect.enabled_sources(engine) == [senuri, volunteer]
    with engine.begin() as db:
        db.execute(update(Source).where(Source.id == senuri).values(enabled=False))
    assert collect.enabled_sources(engine) == [volunteer]
    engine.dispose()


def test_run_due_forces_due_and_continues_after_failure():
    first, second, third = uuid4(), uuid4(), uuid4()
    run_id = uuid4()
    collector = FakeCollector({
        first: RuntimeError("postgresql://user:secret@db/x 연결 실패"),
        second: RunResult("succeeded", run_id),
        third: RunResult("failed", uuid4(), "budget_exhausted"),
    })
    results = asyncio.run(collect.run_due(collector, [first, second, third], max_requests=5, max_pages=2, rows=3))
    assert [call[0] for call in collector.calls] == [first, second, third]
    assert all(call[1] == {"due": True, "max_requests": 5, "max_pages": 2, "rows": 3} for call in collector.calls)
    assert results[0] == {"source_id": str(first), "status": "unavailable", "run_id": None, "failure_code": None}
    assert results[1] == {"source_id": str(second), "status": "succeeded", "run_id": str(run_id), "failure_code": None}
    assert results[2]["failure_code"] == "budget_exhausted"
    assert "secret" not in json.dumps(results)


def test_skipped_sources_are_not_failures():
    source = uuid4()
    results = asyncio.run(collect.run_due(FakeCollector({source: RunResult("skipped")}), [source]))
    assert results == [{"source_id": str(source), "status": "skipped", "run_id": None, "failure_code": None}]


@pytest.mark.parametrize("argv", [[], ["--all-due", "--source", str(uuid4())]])
def test_collect_requires_exactly_one_target(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["collect", *argv])
    with pytest.raises(SystemExit) as raised:
        collect.main()
    assert raised.value.code == 2


@pytest.fixture
def backend_dir(tmp_path, monkeypatch):
    for _, args, _ in manage_retention.STEPS:
        (tmp_path / args[0]).write_text("", encoding="utf-8")
    monkeypatch.setattr(manage_retention, "BACKEND", tmp_path)
    return tmp_path


def test_retention_runs_every_step_and_repeats_batched_purge(backend_dir, capsys):
    answers = {"manage_deletions.py": [3], "manage_reports.py": [100, 100, 7], "manage_audit.py": [0]}
    calls = []

    def runner(args):
        calls.append(args[0])
        return answers[args[0]].pop(0)

    assert manage_retention.main(["run"], runner=runner) == 0
    assert calls == ["manage_deletions.py", "manage_reports.py", "manage_reports.py", "manage_reports.py", "manage_audit.py"]
    output = json.loads(capsys.readouterr().out)
    assert output["completed"] is True
    assert [step["processed"] for step in output["steps"]] == [3, 207, 0]


def test_retention_failure_does_not_stop_later_steps(backend_dir, capsys):
    calls = []

    def runner(args):
        calls.append(args[0])
        return None if args[0] == "manage_deletions.py" else 0

    assert manage_retention.main(["run"], runner=runner) == 1
    assert calls == ["manage_deletions.py", "manage_reports.py", "manage_audit.py"]
    output = json.loads(capsys.readouterr().out)
    assert output["completed"] is False
    assert [step["status"] for step in output["steps"]] == ["failed", "ok", "ok"]


def test_retention_reports_missing_command_and_unfinished_batches(backend_dir, capsys):
    (backend_dir / "manage_audit.py").unlink()
    assert manage_retention.main(["run"], runner=lambda args: 100) == 1
    steps = {step["step"]: step for step in json.loads(capsys.readouterr().out)["steps"]}
    assert steps["audit_events"] == {"step": "audit_events", "status": "missing", "processed": 0}
    assert steps["report_details"] == {"step": "report_details", "status": "incomplete",
                                       "processed": 100 * manage_retention.MAX_ROUNDS}


@pytest.mark.parametrize(("script", "expected"), [
    ("print('로그'); print('{\"completed\": true, \"processed\": 4}')", 4),
    ("import sys; sys.stderr.write('postgresql://secret'); print('{\"completed\": false, \"code\": \"SERVICE_UNAVAILABLE\"}'); raise SystemExit(1)", None),
    ("print('{\"completed\": true, \"processed\": 4}'); raise SystemExit(1)", None),
    ("print('{\"completed\": true, \"processed\": -1}')", None),
    ("print('{\"completed\": true, \"processed\": true}')", None),
    ("print('not json')", None),
    ("pass", None),
])
def test_run_command_trusts_only_successful_json_count(tmp_path, monkeypatch, capsys, script, expected):
    (tmp_path / "job.py").write_text(script, encoding="utf-8")
    monkeypatch.setattr(manage_retention, "BACKEND", tmp_path)
    assert manage_retention.run_command(("job.py",)) == expected
    assert "secret" not in capsys.readouterr().err


def unit(name):
    return (INFRA / "scheduler" / name).read_text(encoding="utf-8")


def test_timers_survive_restart_and_call_existing_commands():
    for name in ("reconnect-collect.timer", "reconnect-retention.timer"):
        assert "Persistent=true" in unit(name)
    assert "OnCalendar=*:0/15" in unit("reconnect-collect.timer")
    # 운영 이미지의 ENTRYPOINT는 API 서버라서 일회성 작업은 진입점을 python으로 바꿔야 한다.
    entry = '--entrypoint /opt/venv/bin/python "$BACKEND_SERVICE"'
    assert f"{entry} -B -m app.collect --all-due" in unit("reconnect-collect.service")
    assert f"{entry} -B manage_retention.py run" in unit("reconnect-retention.service")
    for service in ("reconnect-collect.service", "reconnect-retention.service"):
        text = unit(service)
        assert "Type=oneshot" in text and "WorkingDirectory=$" not in text
        # 배포 때 tmpfs에 만드는 이미지·앱 env 파일을 읽고, 재부팅으로 사라졌으면 Compose를 부르기 전에 실패한다.
        assert '--env-file "$IMAGES_ENV_FILE"' in text
        assert 'test -r "$IMAGES_ENV_FILE" && test -r "$APP_ENV_FILE"' in text
    env = unit("scheduler.env.example")
    assert "IMAGES_ENV_FILE=/run/reconnect/images.env" in env and "APP_ENV_FILE=/run/reconnect/app.env" in env


def test_docker_logs_go_to_the_14_day_group_without_creating_unbounded_groups():
    daemon = json.loads((INFRA / "logging" / "docker-daemon.json").read_text(encoding="utf-8"))
    groups = json.loads((INFRA / "logging" / "log-groups.json").read_text(encoding="utf-8"))["Resources"]
    assert groups["OperationalLogs"]["Properties"]["RetentionInDays"] == 14
    assert daemon["log-driver"] == "awslogs"
    assert daemon["log-opts"]["awslogs-group"] == "/re-connect/production/operations"
    assert daemon["log-opts"]["awslogs-create-group"] == "false"
    assert daemon["log-opts"]["mode"] == "non-blocking"
