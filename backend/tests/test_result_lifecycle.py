"""TOCTOU(TIM-01)·부적절한 인가(SEC-02): 삭제/취소/수명과 늦은 완료의 경합."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.business_errors import AppError
from app.modules.consents.models import ConsentCreate
from app.modules.consents.repository import RedisConsentStore
from app.modules.consents.service import ConsentActor
from app.modules.requests.repository import RedisRequestStore
from app.modules.requests.service import CompletionGuard, Permit, RequestScope, RequestService, ResultReference, UnavailableRequestStore
from tests.test_sessions import with_redis


@pytest.mark.parametrize("changes", [
    {"session_digest": "private-session-token"}, {"session_digest": "a" * 63},
    {"resource_generation": "client-generated"}, {"ai_notice_version": "old version"},
    {"ai_notice_version": "ai\n"}, {"ai_notice_version": "x" * 33},
])
def test_guard_rejects_malformed_internal_identity(changes):
    values = {"session_digest": "a" * 64, "resource_generation": uuid4(), "ai_notice_version": "ai-test-v1"}
    with pytest.raises(ValueError):
        CompletionGuard(**{**values, **changes})


def test_guard_does_not_expose_session_digest_in_repr():
    guard = CompletionGuard("a" * 64, uuid4(), "ai-test-v1")
    assert guard.session_digest not in repr(guard)


def test_guarded_completion_requires_resource_revision():
    permit = Permit(RequestScope(uuid4(), "messages"), uuid4(), "a" * 64, "b" * 64)
    guard = CompletionGuard("c" * 64, uuid4(), "ai-test-v1")
    with pytest.raises(AppError, match="VALIDATION_FAILED"):
        asyncio.run(RequestService(UnavailableRequestStore()).complete(permit, None, guard=guard))


async def setup_resource(sessions, session_store, client):
    issued = await sessions.issue()
    consent_store = RedisConsentStore(client, session_key=session_store.key)
    actor = ConsentActor(issued.session.subject_id, session_digest=issued.session.digest)
    await consent_store.grant(actor, ConsentCreate(purpose="ai_processing", notice_version="ai-test-v1"))
    store = RedisRequestStore(client, session_key=session_store.key, prefix=session_store.prefix + "requests:")
    service = RequestService(store)
    guard = CompletionGuard(issued.session.digest, uuid4(), "ai-test-v1")
    resource_id = uuid4()
    assert await service.create_guarded_resource(actor.subject_id, resource_id, guard)
    scope = RequestScope(actor.subject_id, "messages", resource_id)
    permit = await service.begin(scope, str(uuid4()), {"text": "가상 경험"}, base_revision=0)
    return issued, service, store, guard, permit


def test_real_redis_guarded_completion_replay_does_not_extend_ttl_or_repeat_revision():
    async def scenario(sessions, session_store, client):
        _, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        key = store.resource_key(permit.scope.subject_id, permit.scope.resource_id)
        before = await client.pttl(key)
        result = ResultReference("message", uuid4(), 1)
        await service.complete(permit, result, guard=guard)
        await service.complete(permit, result, guard=guard)
        assert await client.get(key) == "g:1"
        assert 0 < await client.pttl(key) <= before
        assert await client.hget(store.keys(permit.scope, permit.key_id)[0], "state") == "done"
    with_redis(scenario)


@pytest.mark.parametrize("mutation,code", [
    ("session_deleted", "NOT_FOUND"), ("session_expired", "NOT_FOUND"),
    ("consent_withdrawn", "CONSENT_REQUIRED"), ("consent_changed", "CONSENT_REQUIRED"),
    ("journey_expired", "NOT_FOUND"), ("journey_idle", "NOT_FOUND"),
    ("generation_changed", "NOT_FOUND"), ("guard_missing", "NOT_FOUND"),
])
def test_real_redis_late_result_never_completes_after_lifecycle_changes(mutation, code):
    async def scenario(sessions, session_store, client):
        issued, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        session_key = session_store.key(issued.session.digest)
        resource = store.resource_key(permit.scope.subject_id, permit.scope.resource_id)
        meta = resource + ":lifecycle"
        if mutation == "session_deleted":
            await sessions.revoke(issued.token)
        elif mutation == "session_expired":
            await client.hset(session_key, mapping={"created_ms": 0, "last_ms": 0})
        elif mutation == "consent_withdrawn":
            await client.hdel(session_key, "ai_notice_version", "ai_granted_ms")
        elif mutation == "consent_changed":
            await client.hset(session_key, "ai_notice_version", "ai-test-v2")
        elif mutation == "journey_expired":
            await client.hset(meta, mapping={"created_ms": 0, "last_ms": 0})
        elif mutation == "journey_idle":
            seconds, micros = await client.time()
            now = seconds * 1000 + micros // 1000
            await client.hset(meta, mapping={"created_ms": now - 1_800_001, "last_ms": now - 1_800_001})
        elif mutation == "generation_changed":
            await client.hset(meta, "generation", str(uuid4()))
        else:
            await client.delete(meta)
        with pytest.raises(AppError, match=code):
            await service.complete(permit, ResultReference("message", uuid4(), 1), guard=guard)
        assert await client.get(resource) == "g:0"
        assert await client.hget(store.keys(permit.scope, permit.key_id)[0], "result") == ""
    with_redis(scenario)


def test_real_redis_unguarded_api_cannot_bypass_missing_lifecycle_metadata():
    async def scenario(sessions, session_store, client):
        _, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        resource = store.resource_key(permit.scope.subject_id, permit.scope.resource_id)
        await client.delete(resource + ":lifecycle")
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            await service.complete(permit, ResultReference("message", uuid4(), 1))
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.begin(permit.scope, str(uuid4()), {}, base_revision=0)
        assert await client.get(resource) == "g:0"
    with_redis(scenario)


def test_real_redis_cancel_blocks_completion_and_is_idempotent():
    async def scenario(sessions, session_store, client):
        _, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        await service.cancel(permit)
        await service.cancel(permit)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.complete(permit, ResultReference("message", uuid4(), 1), guard=guard)
        with pytest.raises(AppError, match="REQUEST_ALREADY_COMPLETED"):
            await service.begin(permit.scope, str(permit.key_id), {"text": "가상 경험"}, base_revision=0)
        assert await client.get(store.resource_key(permit.scope.subject_id, permit.scope.resource_id)) == "g:0"
    with_redis(scenario)


def test_real_redis_delete_and_late_completion_cannot_recreate_request_or_resource():
    async def scenario(sessions, session_store, client):
        _, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        await service.delete_resource(permit.scope.subject_id, permit.scope.resource_id)
        before = set([key async for key in client.scan_iter(match=store.prefix + "*")])
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.complete(permit, ResultReference("message", uuid4(), 1), guard=guard)
        after = set([key async for key in client.scan_iter(match=store.prefix + "*")])
        assert before == after == set()
    with_redis(scenario)


def test_real_redis_cancel_complete_race_has_one_winner():
    async def scenario(sessions, session_store, client):
        _, service, store, guard, permit = await setup_resource(sessions, session_store, client)
        async def attempt(operation):
            try:
                await operation
                return "ok"
            except AppError as error:
                return error.code
        results = await asyncio.gather(
            attempt(service.cancel(permit)),
            attempt(service.complete(permit, ResultReference("message", uuid4(), 1), guard=guard)),
        )
        assert results in (["ok", "NOT_FOUND"], ["INVALID_STATE_TRANSITION", "ok"])
        key = store.resource_key(permit.scope.subject_id, permit.scope.resource_id)
        assert await client.get(key) == ("g:0" if results[0] == "ok" else "g:1")
    with_redis(scenario)
