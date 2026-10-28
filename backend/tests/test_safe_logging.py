"""메시지·콜백 쿼리·인증정보·본문·예외 추적이 실제 포맷된 로그에 없는지 검사한다."""

import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import httpx
import pytest

from app.core.safe_logging import LOGGING_CONFIG, SafeJsonFormatter
from tests.test_errors import app_with_sample_routes


def test_formatter_does_not_stringify_sensitive_objects_or_exceptions():
    class Sensitive:
        def __str__(self):
            raise AssertionError("로그 원문을 읽으면 안 됨")

    record = logging.LogRecord("token-in-logger-name", logging.ERROR, "/secret/file", 1, Sensitive(), (Sensitive(),), None)
    record.exc_info = (RuntimeError, RuntimeError("private-token"), None)
    record.exc_text = "private-traceback"
    record.stack_info = "private-stack"
    record.event = "arbitrary-private-event"
    record.authorization = "Bearer private-token"
    entry = json.loads(SafeJsonFormatter().format(record))
    assert set(entry) == {"timestamp", "level", "event"}
    assert entry["event"] == "runtime_event"
    assert "private" not in json.dumps(entry)


def test_requests_log_only_safe_metadata_including_errors(test_settings, make_client):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter())
    app_logger = logging.getLogger("app")
    previous_level = app_logger.level
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(handler)
    try:
        client = make_client(app_with_sample_routes(test_settings))
        headers = {"Authorization": "Bearer private-token", "Cookie": "session=private-cookie", "X-Request-ID": "private-client-id"}
        good = client.post("/sample?code=private-code&state=private-state", json={"name": "a", "age": 1, "tags": []}, headers=headers)
        invalid = client.post("/sample?code=private-code", json={"name": "private-body", "age": -1, "tags": []}, headers=headers)
        boom = client.get("/boom?otp=private-otp", headers=headers)
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(previous_level)
    entries = [json.loads(line) for line in stream.getvalue().splitlines()]
    requests = [entry for entry in entries if entry["event"] == "request_complete"]
    assert [entry["status"] for entry in requests] == [200, 422, 500]
    assert [entry["request_id"] for entry in requests] == [response.headers["x-request-id"] for response in (good, invalid, boom)]
    assert all(entry["duration_ms"] >= 0 for entry in requests)
    for secret in ("private-", "SuperSecret", "secret-token", "postgresql", "/srv/app", "/sample", "/boom", "traceback"):
        assert secret not in stream.getvalue()


def test_safe_server_entry_disables_uvicorn_access_log():
    from app.__main__ import main

    with patch("app.__main__.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["access_log"] is False
    assert run.call_args.kwargs["log_config"] == LOGGING_CONFIG
    assert run.call_args.kwargs["host"] == "127.0.0.1"


def test_container_entry_accepts_only_ip_bind_host():
    from app.__main__ import main

    with patch("app.__main__.uvicorn.run") as run:
        main(["--host", "0.0.0.0"])
    assert run.call_args.kwargs["host"] == "0.0.0.0"
    assert run.call_args.kwargs["port"] == 8000
    for host in ("backend", "evil.example", "0.0.0.0 --reload", ""):
        with patch("app.__main__.uvicorn.run") as run, pytest.raises(SystemExit):
            main(["--host", host])
        run.assert_not_called()


def test_supplied_log_metadata_must_be_from_allowlist():
    record = logging.LogRecord("app", logging.INFO, "", 1, "secret", (), None)
    record.status = "200 private-token"
    record.duration_ms = True
    record.method = "GET private-token"
    entry = json.loads(SafeJsonFormatter().format(record))
    assert not {"status", "duration_ms", "method"} & entry.keys()


def test_real_uvicorn_callback_and_exception_logs_do_not_expose_secrets():
    script = '''
import socket
import uvicorn
from app.core.config import Settings
from app.core.safe_logging import LOGGING_CONFIG
from app.main import create_app
app = create_app(Settings(_env_file=None, app_env="test"))
@app.get("/callback")
async def callback():
    raise RuntimeError("private-exception-token")
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
sock.listen(128)
print(sock.getsockname()[1], flush=True)
config = uvicorn.Config(app, access_log=False, log_config=LOGGING_CONFIG)
uvicorn.Server(config).run(sockets=[sock])
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        port = int(process.stdout.readline())
        deadline = time.monotonic() + 10
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                try:
                    response = client.get(f"http://127.0.0.1:{port}/callback?code=private-code&state=private-state", headers={"Authorization": "Bearer private-header"})
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
        assert response.status_code == 500
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
    entries = [json.loads(line) for line in stdout.splitlines()]
    assert any(entry.get("request_id") == response.headers["x-request-id"] and entry.get("status") == 500 for entry in entries)
    assert stderr == ""
    assert "private-" not in stdout
    assert "/callback" not in stdout
    assert "RuntimeError" not in stdout
