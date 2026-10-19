"""역할 제외는 체험 필터일 뿐 프로필 사실이 아니다. 소유권·CAS·복원·형식 경계."""

import asyncio
from contextlib import nullcontext
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import insert

from app.contracts.roles import RoleExclusionUpdate, RoleExclusions
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.journeys.service import JourneyService
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService, UnknownRoleIds
from app.persistence import Base
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journeys import BODY, app_for_test, real_services
from tests.test_profile_confirmation import ready_edit
from tests.test_roles import CatalogStub, MemoryRolesStore, role


class MemoryExclusionStore(MemoryRolesStore):
    async def set_role_exclusions(self, session, journey_id, role_ids, base_revision):
        current = await self.profile(session, journey_id)
        if current.revision != base_revision:
            raise AppError("VERSION_CONFLICT")
        self.role_ids = tuple(role_ids)
        self.view = current.model_copy(update={"revision": current.revision + 1})
        return RoleExclusions(role_ids=role_ids, revision=self.view.revision)


def test_selection_does_not_change_profile_and_restore_all_does_not_require_catalog():
    async def scenario():
        app, _ = app_for_test()
        session = (await app.state.session_service.issue()).session
        journey = uuid4()
        store = MemoryExclusionStore(session, journey)
        journeys = JourneyService(store, app.state.consent_service, app.state.admission_service)
        await journeys.update_profile(session, journey, ready_edit())
        confirmation = await journeys.confirm_profile(session, journey, 2)
        before = (await journeys.resolve_profile(session, confirmation.profile)).content
        service = RoleService(journeys, CatalogStub())
        result = await service.set_exclusions(session, journey, RoleExclusionUpdate(role_ids=["reading_companion"], base_revision=3))
        assert result.revision == 4 and await service.excluded_role_ids(session, journey) == frozenset({"reading_companion"})
        assert (await journeys.resolve_profile(session, confirmation.profile)).content == before
        assert not (await journeys.profile(session, journey)).has_unconfirmed_changes
        with pytest.raises(UnknownRoleIds) as unknown:
            await service.set_exclusions(session, journey, RoleExclusionUpdate(role_ids=["missing_role"], base_revision=4))
        assert unknown.value.indices == (0,) and (await journeys.role_state(session, journey)).revision == 4
        class BrokenCatalog:
            def list(self):
                raise AppError("SERVICE_UNAVAILABLE")
        restored = await RoleService(journeys, BrokenCatalog()).set_exclusions(session, journey, RoleExclusionUpdate(role_ids=[], base_revision=4))
        assert restored.role_ids == [] and restored.revision == 5
    asyncio.run(scenario())


@pytest.mark.parametrize("ids,revision", [(["reading_companion", "reading_companion"], 1), (["bad-role"], 1),
                                         (["reading_companion"], True), (["role_id"] * 51, 1)])
def test_selection_contract_rejects_duplicates_unknown_format_boolean_revision_and_size(ids, revision):
    with pytest.raises(ValidationError):
        RoleExclusionUpdate(role_ids=ids, base_revision=revision)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_http_exclude_restore_unknown_stale_and_other_owner(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        with open_test_database(backend) as db:
            Base.metadata.create_all(db)
            # ready_edit의 실제 경험 태그가 자료 정리이므로 같은 태그의 사전 역할을 사용한다.
            db.execute(insert(RoleDefinition), role(skill_tags=["자료 정리"]).model_dump())
            service = RoleService(journeys, SQLRoleCatalog(lambda: nullcontext(db)))
            app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service, app.state.role_service = admission, service
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("192.0.2.1", 50000)), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")
                path = f"/api/v1/journeys/{journey.journey_id}/role-exclusions"
                candidates = f"/api/v1/journeys/{journey.journey_id}/roles"
                body = {"role_ids": ["reading_companion"], "base_revision": 1}
                assert (await client.put(path, json=body, headers=csrf(client))).json()["code"] == "PROFILE_NOT_CONFIRMED"
                await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
                confirmed = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
                before = (await journeys.resolve_profile(issued.session, confirmed.profile)).content
                body["base_revision"] = 3
                assert (await client.put(path, json=body)).status_code == 403
                selected = await client.put(path, json=body, headers=csrf(client))
                assert selected.status_code == 200 and selected.json()["revision"] == 4
                assert (await client.get(candidates)).json()["items"][0]["excluded"] is True
                assert (await client.put(path, json=body, headers=csrf(client))).status_code == 409
                invalid = await client.put(path, json={"role_ids": ["missing_role"], "base_revision": 4}, headers=csrf(client))
                assert invalid.status_code == 422 and invalid.json()["fields"] == [{"path": "role_ids[0]", "reason": "invalid_value"}]
                restored = await client.put(path, json={"role_ids": [], "base_revision": 4}, headers=csrf(client))
                assert restored.json() == {"role_ids": [], "revision": 5}
                assert (await client.get(candidates)).json()["items"][0]["excluded"] is False
                assert (await journeys.resolve_profile(issued.session, confirmed.profile)).content == before
                assert not (await journeys.profile(issued.session, journey.journey_id)).has_unconfirmed_changes
                stranger = await sessions.issue()
                client.cookies.clear()
                client.cookies.set("__Host-rc_session", stranger.token)
                await client.get("/api/v1/me")
                assert (await client.put(path, json={"role_ids": [], "base_revision": 5}, headers=csrf(client))).status_code == 404
    with_redis(scenario)


def test_real_redis_two_selection_changes_from_same_revision_have_one_winner():
    async def scenario(admission, admission_store, redis):
        issued, _, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        await journeys.update_profile(issued.session, journey.journey_id, ready_edit())
        await journeys.confirm_profile(issued.session, journey.journey_id, 2)
        service = RoleService(journeys, CatalogStub())
        async def attempt(ids):
            try:
                await service.set_exclusions(issued.session, journey.journey_id, RoleExclusionUpdate(role_ids=ids, base_revision=3))
                return "ok"
            except AppError as error:
                return error.code
        outcomes = await asyncio.gather(attempt(["reading_companion"]), attempt([]))
        assert sorted(outcomes) == ["VERSION_CONFLICT", "ok"]
        assert (await journeys.role_state(issued.session, journey.journey_id)).revision == 4
    with_redis(scenario)
