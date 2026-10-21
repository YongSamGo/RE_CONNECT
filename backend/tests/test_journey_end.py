"""체험 종료·멱등 삭제·늦은 완료 경합·소유권 (SEC-02/TIM-01)."""

import asyncio
from uuid import uuid4

import httpx
import pytest

from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.requests.service import RequestScope, RequestService, ResultReference
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, real_services
from tests.test_profile_confirmation import ready_edit


def test_real_http_end_is_csrf_protected_owner_scoped_idempotent_and_blocks_late_results():
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, store, requests, identity = await real_services(admission, admission_store, redis)
        creation_key = str(uuid4())
        journey = await journeys.create(issued.session, identity, creation_key, BODY)
        await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        confirmed = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
        guard = (await journeys.load(issued.session, journey.journey_id)).guard
        service = RequestService(requests)
        permit = await service.begin(RequestScope(issued.session.subject_id, "messages", journey.journey_id), str(uuid4()), {}, base_revision=3)
        resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
        request_key = requests.keys(permit.scope, permit.key_id)[0]
        app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
        app.state.session_service, app.state.consent_service = sessions, journeys.consents
        app.state.admission_service, app.state.journey_service = admission, journeys
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as client:
            path = f"/api/v1/journeys/{journey.journey_id}"
            client.cookies.set("__Host-rc_session", issued.token)
            await client.get("/api/v1/me")
            assert (await client.delete(path)).status_code == 403
            assert await redis.exists(resource)
            # 다른 세션의 같은 ID는 없는 자원과 같은 204이며 원래 체험을 지우지 않는다.
            stranger = await sessions.issue()
            client.cookies.clear()
            client.cookies.set("__Host-rc_session", stranger.token)
            await client.get("/api/v1/me")
            assert (await client.delete(path, headers=csrf(client))).status_code == 204
            assert await redis.exists(resource)
            client.cookies.clear()
            client.cookies.set("__Host-rc_session", issued.token)
            await client.get("/api/v1/me")
            for _ in range(2):
                response = await client.delete(path, headers=csrf(client))
                assert response.status_code == 204 and response.content == b""
            assert await redis.exists(resource, resource + ":lifecycle", resource + ":requests", request_key) == 0
            assert (await client.get(path + "/profile")).status_code == 404
            assert (await client.delete(f"/api/v1/journeys/{uuid4()}", headers=csrf(client))).status_code == 204
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.complete(permit, ResultReference("message", uuid4(), 4), guard=guard)
        with pytest.raises(AppError, match="NOT_FOUND"):
            await journeys.resolve_profile(issued.session, confirmed.profile)
        # 과거 생성 멱등 키는 자료를 다시 만들거나 새 체험으로 바꾸지 않는다.
        with pytest.raises(AppError, match="NOT_FOUND"):
            await journeys.create(issued.session, identity, creation_key, BODY)
        new = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        assert new.journey_id != journey.journey_id and new.confirmed is None
        assert await redis.exists(resource, resource + ":lifecycle", request_key) == 0
    with_redis(scenario)


def test_real_redis_end_wins_over_concurrent_completion_without_recreation():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, requests, identity = await real_services(admission, admission_store, redis)
        for _ in range(4):
            journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            guard = (await journeys.load(issued.session, journey.journey_id)).guard
            service = RequestService(requests)
            permit = await service.begin(RequestScope(issued.session.subject_id, "messages", journey.journey_id), str(uuid4()), {}, base_revision=1)
            async def complete():
                try:
                    await service.complete(permit, ResultReference("message", uuid4(), 2), guard=guard)
                except AppError as error:
                    assert error.code == "NOT_FOUND"
            await asyncio.gather(complete(), journeys.end(issued.session, journey.journey_id))
            resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
            assert await redis.exists(resource, resource + ":lifecycle", resource + ":requests", requests.keys(permit.scope, permit.key_id)[0]) == 0
    with_redis(scenario)


def test_real_redis_expired_metadata_can_be_cleaned_without_consent_or_extending_ttl():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, requests, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        resource = requests.resource_key(issued.session.subject_id, journey.journey_id)
        await redis.hset(resource + ":lifecycle", mapping={"created_ms": 0, "last_ms": 0})
        await redis.hdel(journeys.store.session_key(issued.session.digest), "ai_notice_version", "ai_granted_ms")
        await journeys.end(issued.session, journey.journey_id)
        assert await redis.exists(resource, resource + ":lifecycle") == 0
    with_redis(scenario)
