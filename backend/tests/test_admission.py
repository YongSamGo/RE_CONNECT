"""실제 Redis 한도와 작업 중단·응답 유실의 단일 슬롯 경계."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import os
import hashlib
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.adapters.redis import build_redis
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.admission.llm import ControlledLLMAdapter
from app.modules.admission.repository import RedisAdmissionStore
from app.modules.admission.service import AdmissionService, InferenceIdentity, Lease, UnavailableAdmissionService, normalize_ip
from app.modules.sessions.repository import RedisSessionStore
from app.modules.sessions.service import SessionService
from tests.test_ollama_adapter import Extracted, make_adapter, chat_response
from app.adapters.llm import LLMInvalidOutputError, LLMTimeoutError, UntrustedTurn


def test_trusted_peer_identity_normalizes_addresses_and_rejects_non_addresses():
    assert normalize_ip("::ffff:192.0.2.1") == normalize_ip("192.0.2.1")
    assert normalize_ip("2001:0db8::1") == "2001:db8::1"
    for value in ("attacker.test", "192.0.2.1, 192.0.2.2", "fe80::1%eth0", ""):
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            normalize_ip(value)


def test_absent_or_invalid_secret_does_not_enable_inference():
    async def run():
        for settings in (Settings(_env_file=None), Settings(_env_file=None, redis_url="redis://127.0.0.1:1", request_limit_key="invalid", inference_control_epoch=uuid4())):
            app = create_app(settings)
            assert not await app.state.llm_adapter.is_ready()
            with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
                await app.state.llm_adapter.generate_structured(instructions="x", untrusted_turns=[UntrustedTurn(role="user", text="x")], output_model=Extracted)
            if app.state.redis:
                await app.state.redis.aclose()
    asyncio.run(run())


async def expect_error(code, operation):
    with pytest.raises(AppError) as caught:
        await operation
    assert caught.value.code == code
    if code in {"RATE_LIMITED", "DAILY_QUOTA_EXCEEDED", "INFERENCE_BUSY"}:
        assert 1 <= caught.value.retry_after <= 86400


def with_redis(scenario):
    url = os.environ.get("PERSISTENCE_TEST_REDIS_URL")
    if not url:
        pytest.skip("호출 한도와 슬롯은 CI의 실제 Redis에서 검증")

    async def run():
        client = build_redis(Settings(_env_file=None, redis_url=url))
        store = RedisAdmissionStore(client, epoch=uuid4(), prefix=f"test:admission:{uuid4().hex}:")
        service = AdmissionService(store, identity_key=bytes(range(32)))
        try:
            # 시험에서만 이미 정지한 가상 런타임에 대해 초기화한다. 앱 시작 경로에는 없다.
            seconds, _ = await client.time()
            await client.hset(store.control_key, mapping={"epoch": str(store.epoch), "key_id": hashlib.sha256(bytes(range(32))).hexdigest(), "day": (seconds + 32400) // 86400, "global": 0})
            await scenario(service, store, client)
        finally:
            keys = [key async for key in client.scan_iter(match=store.prefix + "*")]
            if keys:
                await client.delete(*keys)
            await client.aclose()
    asyncio.run(run())


def identity(ip="192.0.2.1", *, account=None):
    return InferenceIdentity(uuid4(), ip, account)


async def ended(completion):
    completion.confirm_ended()
    return "ok"


def test_redis_http_sliding_minute_is_atomic_for_ip_and_subject():
    async def scenario(service, store, client):
        subject = uuid4()
        async def attempt():
            try:
                await service.check_http("192.0.2.1", subject)
                return "ok"
            except AppError as exc:
                return exc.code
        results = await asyncio.gather(*(attempt() for _ in range(80)))
        assert results.count("ok") == 60 and results.count("RATE_LIMITED") == 20
        await expect_error("RATE_LIMITED", service.check_http("192.0.2.2", subject))
        assert await client.zcard(store.prefix + "http:" + service.digest("ip", "192.0.2.2")) == 0
        # 기준 창을 넘어간 점수는 다음 요청에서 제거하며, 한 주체/다른 IP 제한은 별개다.
        seconds, micros = await client.time()
        past = seconds * 1000 + micros // 1000 - 60001
        for category, value in (("ip", "192.0.2.1"), ("subject", str(subject))):
            key = store.prefix + "http:" + service.digest(category, value)
            members = await client.zrange(key, 0, -1)
            await client.zadd(key, {member: past for member in members})
        await service.check_http("::ffff:192.0.2.1", subject)
        assert await client.zcard(store.prefix + "http:" + service.digest("ip", "192.0.2.1")) == 1
    with_redis(scenario)


def test_redis_anonymous_generation_and_transcription_share_ip_daily_quota():
    async def scenario(service, store, client):
        for index in range(60):
            assert await service.run(identity(), "llm" if index % 2 else "stt", ended) == "ok"
        await expect_error("DAILY_QUOTA_EXCEEDED", service.run(identity(), "llm", ended))
        assert await client.hget(store.control_key, "global") == "60"
        await service.run(identity("192.0.2.2"), "llm", ended)
        assert await client.pttl(store.control_key) == -1
        assert "192.0.2.1" not in str(await client.hgetall(store.control_key))
    with_redis(scenario)


def test_redis_member_budget_follows_account_across_ips_and_tts_uses_both_identities():
    async def scenario(service, store, client):
        account = uuid4()
        for index in range(60):
            await service.run(identity(f"192.0.2.{index + 1}", account=account), "llm", ended)
        await expect_error("DAILY_QUOTA_EXCEEDED", service.run(identity("192.0.2.200", account=account), "stt", ended))
        user = identity("198.51.100.1")
        for _ in range(60):
            await service.run(user, "tts", ended)
        await expect_error("DAILY_QUOTA_EXCEEDED", service.run(replace(user, ip="198.51.100.2"), "tts", ended))
        await expect_error("DAILY_QUOTA_EXCEEDED", service.run(identity("198.51.100.1"), "tts", ended))
        assert await client.hget(store.control_key, "global") == "120"
    with_redis(scenario)


def test_redis_all_runtime_kinds_share_one_slot_and_busy_calls_are_not_executed():
    async def scenario(service, store, client):
        started, finish = asyncio.Event(), asyncio.Event()
        async def blocking(completion):
            started.set()
            await finish.wait()
            completion.confirm_ended()
        first = asyncio.create_task(service.run(identity(), "llm", blocking))
        await started.wait()
        for kind in ("llm", "stt", "tts"):
            await expect_error("INFERENCE_BUSY", service.run(identity("192.0.2.2"), kind, ended))
        assert await client.hget(store.control_key, "global") == "1"
        assert await client.pttl(store.control_key) == -1
        finish.set()
        await first
        await service.run(identity(), "stt", ended)
        assert await client.hget(store.control_key, "global") == "2"
    with_redis(scenario)


def test_redis_timeout_and_cancellation_do_not_release_and_old_token_cannot_release():
    async def scenario(service, store, client):
        async def unknown(completion):
            await asyncio.Event().wait()
        await expect_error("AI_TIMEOUT", service.run(identity(), "llm", unknown, timeout_seconds=0.01))
        await expect_error("INFERENCE_BUSY", service.run(identity(), "tts", ended))
        token = await client.hget(store.control_key, "active")
        await expect_error("SERVICE_UNAVAILABLE", store.release(Lease("0" * 64)))
        assert await client.hget(store.control_key, "active") == token
        # 종료 미확인 슬롯을 시간만 보고 넘기는 자동·공개 경로는 없다. 운영자 복구는 별도 시험에서 확인한다.
        await store.release(Lease(token))  # 시험만 다음 취소 시나리오로 이동
        entered = asyncio.Event()
        async def cancel_target(completion):
            entered.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(service.run(identity(), "stt", cancel_target))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await expect_error("INFERENCE_BUSY", service.run(identity(), "llm", ended))
    with_redis(scenario)


def test_redis_500_daily_cap_and_kst_rollover_preserve_active_slot():
    async def scenario(service, store, client):
        for _ in range(500):
            await service.run(identity(account=uuid4()), "llm", ended)
        await expect_error("DAILY_QUOTA_EXCEEDED", service.run(identity(account=uuid4()), "tts", ended))
        seconds, _ = await client.time()
        kst = datetime.fromtimestamp(seconds, timezone.utc).astimezone(ZoneInfo("Asia/Seoul"))
        expected_day = (kst.date() - datetime(1970, 1, 1).date()).days
        assert await client.hget(store.control_key, "day") == str(expected_day)
        await client.hset(store.control_key, mapping={"day": expected_day - 1, "active": "a" * 64, "kind": "stt"})
        await expect_error("INFERENCE_BUSY", service.run(identity(), "llm", ended))
        assert await client.hget(store.control_key, "global") == "0"
        assert await client.hget(store.control_key, "active") == "a" * 64
        assert not [key for key in await client.hkeys(store.control_key) if key.startswith("limit:")]
        await store.release(Lease("a" * 64))
        await service.run(identity(), "tts", ended)
    with_redis(scenario)


def test_redis_lost_or_wrong_epoch_control_and_corrupt_counts_fail_closed():
    async def scenario(service, store, client):
        assert await service.is_ready()
        for changes in ({"epoch": str(uuid4())}, {"key_id": "wrong-key"}, {"global": "-1"}, {"global": "1.5"}, {"day": "invalid"}):
            old = await client.hgetall(store.control_key)
            await client.hset(store.control_key, mapping=changes)
            await expect_error("SERVICE_UNAVAILABLE", service.run(identity(), "llm", ended))
            await client.delete(store.control_key)
            await client.hset(store.control_key, mapping=old)
        await client.pexpire(store.control_key, 60000)
        assert not await service.is_ready()
        await expect_error("SERVICE_UNAVAILABLE", service.run(identity(), "llm", ended))
        await client.delete(store.control_key)
        await expect_error("SERVICE_UNAVAILABLE", service.run(identity(), "llm", ended))
        assert not await client.exists(store.control_key)
        broken = build_redis(Settings(_env_file=None, redis_url="redis://127.0.0.1:1"))
        try:
            failed = AdmissionService(RedisAdmissionStore(broken, epoch=store.epoch), identity_key=bytes(range(32)))
            await expect_error("SERVICE_UNAVAILABLE", failed.run(identity(), "llm", ended))
        finally:
            await broken.aclose()
    with_redis(scenario)


def test_real_redis_me_bootstrap_is_limited_before_session_creation_and_public_stays_open():
    async def scenario(service, store, client):
        app = create_app(Settings(_env_file=None, app_env="test"))
        sessions = RedisSessionStore(client, prefix=store.prefix + "sessions:")
        app.state.session_service = SessionService(sessions)
        app.state.admission_service = service
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver") as http:
            for _ in range(60):
                assert (await http.get("/api/v1/me")).status_code == 200
            denied = await http.get("/api/v1/me", headers={"X-Forwarded-For": "203.0.113.5"})
            assert denied.status_code == 429 and denied.json()["code"] == "RATE_LIMITED"
            assert "retry-after" in denied.headers and "set-cookie" not in denied.headers
            http.cookies.clear()
            assert (await http.get("/api/v1/me")).status_code == 429
            assert len([key async for key in client.scan_iter(match=sessions.prefix + "*")]) == 1
            app.state.admission_service = UnavailableAdmissionService()
            assert (await http.get("/api/v1/me")).status_code == 503
            assert (await http.get("/api/v1/regions")).status_code == 200
    with_redis(scenario)


def test_actual_ollama_adapter_terminal_signal_releases_even_invalid_output_but_not_timeout():
    async def scenario(service, store, client):
        for response in (chat_response('{"skills": [], "years": null}'), chat_response("bad-json"), chat_response("", done_reason="length")):
            async def handler(request):
                return response
            adapter = ControlledLLMAdapter(make_adapter(handler), service)
            try:
                await adapter.generate_structured(identity=identity(), instructions="x", untrusted_turns=[UntrustedTurn(role="user", text="x")], output_model=Extracted)
            except LLMInvalidOutputError:
                pass
            assert await client.hget(store.control_key, "active") is None
        calls = []
        async def slow(request):
            calls.append(1)
            await asyncio.sleep(0.1)
            return chat_response('{"skills": [], "years": null}')
        adapter = ControlledLLMAdapter(make_adapter(slow, timeout_seconds=0.01), service)
        with pytest.raises(LLMTimeoutError):
            await adapter.generate_structured(identity=identity(), instructions="x", untrusted_turns=[UntrustedTurn(role="user", text="x")], output_model=Extracted)
        await expect_error("INFERENCE_BUSY", adapter.generate_structured(identity=identity(), instructions="x", untrusted_turns=[UntrustedTurn(role="user", text="x")], output_model=Extracted))
        assert len(calls) == 1
    with_redis(scenario)


def test_operator_release_requires_runtime_stop_confirmation_and_lease_fingerprint():
    import manage_inference
    for argv in (["release", "--lease", "0123456789abcdef"], ["release", "--lease", "ABC", "--confirm-runtime-stopped"],
                 ["release", "--confirm-runtime-stopped"], []):
        with pytest.raises(SystemExit) as caught:
            manage_inference.parse_args(argv)
        assert caught.value.code == 2
    args = manage_inference.parse_args(["release", "--lease", "0123456789abcdef", "--confirm-runtime-stopped"])
    assert (args.command, args.lease, args.confirm_runtime_stopped) == ("release", "0123456789abcdef", True)


def test_operator_cli_without_settings_reports_fixed_unavailable(monkeypatch, capsys):
    import manage_inference
    monkeypatch.setattr(manage_inference, "get_settings", lambda: Settings(_env_file=None))
    assert manage_inference.main(["status"]) == 1
    assert capsys.readouterr().out.strip() == '{"completed": false, "code": "SERVICE_UNAVAILABLE"}'


def test_redis_operator_recovery_releases_only_the_inspected_stuck_lease_and_keeps_daily_counts():
    from app.modules.admission.repository import lease_fingerprint
    async def scenario(service, store, client):
        assert await store.recover(service.identity_key_id, "0" * 16) == "not_active"
        async def unknown(completion):
            await asyncio.Event().wait()
        await expect_error("AI_TIMEOUT", service.run(identity(), "llm", unknown, timeout_seconds=0.01))
        token = await client.hget(store.control_key, "active")
        status = await store.slot_status(service.identity_key_id)
        assert status.ready and status.kind == "llm" and status.lease == lease_fingerprint(token) and status.global_count == 1
        assert token not in repr(status)
        # 다른 지문·다른 세대·다른 식별키로는 비우지 않는다.
        wrong = "0" * 16 if status.lease != "0" * 16 else "1" * 16
        assert await store.recover(service.identity_key_id, wrong) == "lease_changed"
        other_epoch = RedisAdmissionStore(client, epoch=uuid4(), prefix=store.prefix)
        await expect_error("SERVICE_UNAVAILABLE", other_epoch.recover(service.identity_key_id, status.lease))
        await expect_error("SERVICE_UNAVAILABLE", store.recover("0" * 64, status.lease))
        await expect_error("INFERENCE_BUSY", service.run(identity(), "tts", ended))
        assert await store.recover(service.identity_key_id, status.lease) == "released"
        assert await client.hget(store.control_key, "active") is None and await client.hget(store.control_key, "kind") is None
        assert await client.hget(store.control_key, "global") == "1"
        assert await service.run(identity(), "tts", ended) == "ok"
        assert await client.hget(store.control_key, "global") == "2"
        # 검사 뒤 새 실행이 슬롯을 잡았다면 예전 지문으로 그 실행을 비우지 않는다.
        await expect_error("AI_TIMEOUT", service.run(identity(), "stt", unknown, timeout_seconds=0.01))
        newer = await client.hget(store.control_key, "active")
        assert await store.recover(service.identity_key_id, status.lease) == "lease_changed"
        assert await client.hget(store.control_key, "active") == newer
    with_redis(scenario)


def test_operator_init_requires_runtime_stop_confirmation():
    import manage_inference
    for argv in (["init"], ["init", "--confirm-no-runs-today"]):
        with pytest.raises(SystemExit) as caught:
            manage_inference.parse_args(argv)
        assert caught.value.code == 2
    args = manage_inference.parse_args(["init", "--confirm-runtime-stopped"])
    assert (args.command, args.confirm_no_runs_today) == ("init", False)
    args = manage_inference.parse_args(["init", "--confirm-runtime-stopped", "--confirm-no-runs-today"])
    assert args.confirm_no_runs_today is True


@pytest.mark.parametrize("result, code", [("initialized", 0), ("exists", 1)])
def test_operator_init_cli_reports_fixed_result_and_fails_when_hash_exists(monkeypatch, capsys, result, code):
    import manage_inference
    seen = {}
    async def fake(command, lease=None, no_runs_today=False):
        seen.update(command=command, no_runs_today=no_runs_today)
        return {"result": result}
    monkeypatch.setattr(manage_inference, "execute", fake)
    assert manage_inference.main(["init", "--confirm-runtime-stopped"]) == code
    assert seen == {"command": "init", "no_runs_today": False}
    assert capsys.readouterr().out.strip() == f'{{"completed": true, "result": "{result}"}}'


def test_redis_restart_then_default_init_blocks_today_and_next_kst_day_reopens():
    async def scenario(service, store, client):
        await service.run(identity(), "llm", ended)
        # Redis 재시작: 비영속이라 제어 해시와 이 시험 범위의 모든 키가 사라진다.
        await client.delete(*[key async for key in client.scan_iter(match=store.prefix + "*")])
        assert not await service.is_ready()
        await expect_error("SERVICE_UNAVAILABLE", service.run(identity(), "llm", ended))
        # 기본 초기화는 오늘 집계를 한도로 채운다. 0으로 되돌려 한도를 우회하지 않는다.
        assert await store.initialize(service.identity_key_id, no_runs_today=False) == "initialized"
        assert await service.is_ready()
        assert await client.hget(store.control_key, "global") == "500"
        assert await client.pttl(store.control_key) == -1
        for kind in ("llm", "stt", "tts"):
            await expect_error("DAILY_QUOTA_EXCEEDED", service.run(identity(), kind, ended))
        assert await client.hget(store.control_key, "active") is None
        # 다음 KST 날짜가 되면 기존 자정 정리로 다시 열린다.
        day = int(await client.hget(store.control_key, "day"))
        await client.hset(store.control_key, "day", day - 1)
        assert await service.run(identity(), "llm", ended) == "ok"
        assert await client.hget(store.control_key, "global") == "1"
    with_redis(scenario)


def test_redis_init_with_confirmed_no_runs_starts_at_zero_but_never_overwrites():
    async def scenario(service, store, client):
        await client.delete(store.control_key)
        assert await store.initialize(service.identity_key_id, no_runs_today=True) == "initialized"
        assert await client.hget(store.control_key, "global") == "0"
        assert await service.run(identity(), "llm", ended) == "ok"
        # 이미 있는 해시는 어떤 옵션으로도 덮어쓰지 않는다: 오늘 집계·점유 슬롯을 지워 우회할 수 없다.
        await client.hset(store.control_key, mapping={"active": "a" * 64, "kind": "stt"})
        before = await client.hgetall(store.control_key)
        for no_runs_today in (True, False):
            assert await store.initialize(service.identity_key_id, no_runs_today=no_runs_today) == "exists"
        assert await client.hgetall(store.control_key) == before
        # 만료가 걸린 이상한 해시도 존재하면 덮어쓰지 않고 503 상태를 유지한다.
        await client.pexpire(store.control_key, 60000)
        assert await store.initialize(service.identity_key_id, no_runs_today=True) == "exists"
        assert not await service.is_ready()
    with_redis(scenario)


def test_redis_init_rejects_wrong_inputs_and_wrong_key_stays_closed():
    async def scenario(service, store, client):
        await client.delete(store.control_key)
        for key_id in ("0" * 63, "G" * 64, None, service.identity_key_id.upper()):
            with pytest.raises(ValueError):
                await store.initialize(key_id, no_runs_today=True)
        for flag in ("yes", 1, None):
            with pytest.raises(ValueError):
                await store.initialize(service.identity_key_id, no_runs_today=flag)
        assert not await client.exists(store.control_key)
        # 다른 식별키로 만든 해시는 앱의 키와 맞지 않아 추론을 열지 않는다.
        assert await store.initialize("0" * 64, no_runs_today=True) == "initialized"
        await expect_error("SERVICE_UNAVAILABLE", service.run(identity(), "llm", ended))
        assert await client.hget(store.control_key, "global") == "0"
        broken = build_redis(Settings(_env_file=None, redis_url="redis://127.0.0.1:1"))
        try:
            await expect_error("SERVICE_UNAVAILABLE", RedisAdmissionStore(broken, epoch=store.epoch).initialize(service.identity_key_id, no_runs_today=True))
        finally:
            await broken.aclose()
    with_redis(scenario)
