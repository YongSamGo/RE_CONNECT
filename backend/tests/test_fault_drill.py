"""장애 도구는 고정 출력과 제한된 Docker 명령만 사용한다."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from tools import fault_drill


def test_probe_exception_and_timeout_do_not_print_original_error(monkeypatch, capsys):
    async def broken():
        raise RuntimeError('private connection detail')
    assert asyncio.run(fault_drill.record('baseline', 'me', broken))['result'] == 'probe_failed'

    async def timeout(awaitable, seconds):
        assert seconds == 15
        awaitable.close()
        raise TimeoutError('private timeout detail')
    monkeypatch.setattr(fault_drill.asyncio, 'wait_for', timeout)
    assert asyncio.run(fault_drill.record('baseline', 'me', broken))['result'] == 'timeout'
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows == [{'stage': 'baseline', 'probe': 'me', 'result': result}
                    for result in ('probe_failed', 'timeout')]


def test_compose_only_allows_fixed_local_service_actions(monkeypatch):
    calls = []
    monkeypatch.setattr(fault_drill.shutil, 'which', lambda _: '/fixed/docker')
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(fault_drill.subprocess, 'run', run)
    fault_drill.compose('pause', 'postgres')
    argv, options = calls[0]
    assert argv[0] == '/fixed/docker' and argv[-2:] == ['pause', 'postgres']
    assert options['shell'] is False and options['timeout'] == 45 and options['capture_output'] is True
    with pytest.raises(RuntimeError, match='COMPOSE_FAILED'):
        fault_drill.compose('stop', 'postgres')
    assert len(calls) == 1


def test_drill_refuses_nonlocal_service_before_any_docker_action(monkeypatch):
    monkeypatch.setenv('PERSISTENCE_TEST_DATABASE_URL', 'postgresql+psycopg://remote.example:5432/db')
    with pytest.raises(ValueError, match='LOCAL_CONFIG_REQUIRED'):
        asyncio.run(fault_drill.drill())
