"""역할 사전·실재 확정 경험·소유권·별칭/규칙의 정상·공격 경계."""

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from uuid import uuid4

from alembic import command
import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import insert, update

from app.contracts.profile import ProfileContent, empty_profile_content
from app.contracts.roles import CatalogRole
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.journeys.service import JourneyService, RoleState
from app.modules.roles.repository import SQLRoleCatalog
from app.modules.roles.service import RoleService, match_roles
from app.persistence import Base
from app.persistence.operations import RoleDefinition
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_journeys import BODY, app_for_test, real_services
from tests.test_migrations import migration_config
from tests.test_profile_confirmation import MemoryConfirmedStore, ready_edit


def role(**changes):
    return CatalogRole.model_validate({"id": "reading_companion", "name": "책 읽어주기 활동가", "description": "가상 역할 설명",
                                      "skill_tags": ["낭독"], "aliases": [], "experience_rules": [], **changes})


def profile_with_tags(*tag_groups, global_skills=None):
    values = empty_profile_content().model_dump(mode="json")
    values["experiences"] = [{"id": str(uuid4()), "description": "가상 확정 경험", "duration_note": None, "skill_tags": tags} for tags in tag_groups]
    values["skills"] = global_skills or []
    return ProfileContent.model_validate(values)


def test_every_role_evidence_is_a_real_experience_and_global_skills_do_not_invent_linkage():
    profile = profile_with_tags(["자료 정리"], ["낭독"], global_skills=["낭독"])
    before = profile.model_dump()
    items = match_roles(profile, [role()], ())
    assert [e.experience_id for e in items[0].evidence] == [profile.experiences[1].id]
    assert items[0].evidence[0].skill_tags == ["낭독"] and not items[0].excluded
    assert profile.model_dump() == before
    assert match_roles(profile_with_tags(["자료 정리"], global_skills=["낭독"]), [role()], ()) == []


def test_only_declared_aliases_match_and_original_user_tag_is_preserved():
    catalog = role(skill_tags=["자료 정리"], aliases=[{"alias": "book sorting", "skill_tag": "자료 정리"}])
    profile = profile_with_tags([" BOOK   SORTING "])
    candidates = match_roles(profile, [catalog], (catalog.id,))
    assert candidates[0].evidence[0].skill_tags == [" BOOK   SORTING "]
    assert candidates[0].excluded is True
    assert match_roles(profile_with_tags(["도서 정돈"]), [catalog], ()) == []
    assert match_roles(profile_with_tags(["aaaaaaaa"]), [role(skill_tags=["(a+)+$"])], ()) == []


def test_all_rule_cannot_merge_tags_from_unrelated_experiences():
    catalog = role(skill_tags=["낭독", "교육"], experience_rules=[{"operator": "all", "skill_tags": ["낭독", "교육"]}])
    assert match_roles(profile_with_tags(["낭독"], ["교육"]), [catalog], ()) == []
    assert len(match_roles(profile_with_tags(["낭독", "교육"]), [catalog], ())) == 1


def test_candidate_limit_and_order_are_deterministic():
    catalog = [role(id=f"role_{index:02d}") for index in reversed(range(25))]
    candidates = match_roles(profile_with_tags(["낭독"]), catalog, ())
    assert len(candidates) == 20
    assert [c.role_id for c in candidates] == [f"role_{index:02d}" for index in range(20)]


@pytest.mark.parametrize("changes", [
    {"aliases": [{"alias": "read", "skill_tag": "없는 태그"}]},
    {"aliases": [{"alias": "낭독", "skill_tag": "낭독"}]},
    {"aliases": [{"alias": "READ", "skill_tag": "낭독"}, {"alias": "read", "skill_tag": "낭독"}]},
    {"experience_rules": [{"operator": "execute", "skill_tags": ["낭독"]}]},
    {"experience_rules": [{"operator": "all", "skill_tags": ["없는 태그"]}]},
])
def test_invalid_alias_targets_or_executable_rules_are_not_accepted(changes):
    with pytest.raises(ValidationError):
        role(**changes)


class MemoryRolesStore(MemoryConfirmedStore):
    role_ids = ()
    async def role_state(self, session, journey_id):
        current = await self.profile(session, journey_id)
        if current.confirmed is None:
            raise AppError("PROFILE_NOT_CONFIRMED")
        return RoleState(current.revision, current.confirmed.version, self.role_ids)


class CatalogStub:
    def __init__(self):
        self.calls = 0
    def list(self):
        self.calls += 1
        return [role()]


def test_service_rejects_unconfirmed_other_owner_and_unknown_snapshot():
    async def scenario():
        app, _ = app_for_test()
        issued = await app.state.session_service.issue()
        journey = uuid4()
        store, catalog = MemoryRolesStore(issued.session, journey), CatalogStub()
        journeys = JourneyService(store, app.state.consent_service, app.state.admission_service)
        service = RoleService(journeys, catalog)
        with pytest.raises(AppError, match="PROFILE_NOT_CONFIRMED"):
            await service.candidates(issued.session, journey)
        body = ready_edit().model_dump(mode="json")
        body["draft"]["experiences"][0]["skill_tags"] = ["낭독"]
        from app.contracts.journey import ProfileUpdate
        await journeys.update_profile(issued.session, journey, ProfileUpdate.model_validate(body))
        await journeys.confirm_profile(issued.session, journey, 2)
        result = await service.candidates(issued.session, journey)
        assert result.profile_version == 1 and result.revision == 3
        assert result.items[0].evidence[0].experience_id == store.snapshots[1].experiences[0].id
        before = catalog.calls
        with pytest.raises(AppError, match="NOT_FOUND"):
            await service.candidates(replace(issued.session, subject_id=uuid4()), journey)
        assert catalog.calls == before
        with pytest.raises(AppError, match="VERSION_CONFLICT"):
            await service.candidates(issued.session, journey, 99)
    asyncio.run(scenario())


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_catalog_validation_and_initial_seed_preserve_existing_operator_rows(backend):
    with open_test_database(backend) as db:
        config = migration_config(db)
        command.upgrade(config, "0002_immutable_versions")
        custom = role(id="library_assistant", name="운영자 확인 이름", skill_tags=["자료 정리"])
        db.execute(insert(RoleDefinition), custom.model_dump())
        command.upgrade(config, "head")
        catalog = SQLRoleCatalog(lambda: nullcontext(db)).list()
        assert {entry.id for entry in catalog} == {"reading_companion", "library_assistant"}
        assert next(r for r in catalog if r.id == "library_assistant").name == "운영자 확인 이름"
        command.downgrade(config, "0002_immutable_versions")
        command.upgrade(config, "head")
        assert len(SQLRoleCatalog(lambda: nullcontext(db)).list()) == 2
        db.execute(update(RoleDefinition).where(RoleDefinition.id == "reading_companion").values(aliases=["검증되지 않은 문자열 별칭"]))
        with pytest.raises(AppError, match="SERVICE_UNAVAILABLE"):
            SQLRoleCatalog(lambda: nullcontext(db)).list()


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_real_http_uses_confirmed_redis_experience_and_sql_catalog(backend):
    async def scenario(admission, admission_store, redis):
        issued, sessions, journeys, _, _, identity = await real_services(admission, admission_store, redis)
        journey = await journeys.create(issued.session, identity, str(uuid4()), BODY)
        with open_test_database(backend) as db:
            Base.metadata.create_all(db)
            db.execute(insert(RoleDefinition), role().model_dump())
            catalog = SQLRoleCatalog(lambda: nullcontext(db))
            app = create_app(Settings(_env_file=None, app_env="test"))
            app.state.session_service, app.state.consent_service = sessions, journeys.consents
            app.state.admission_service = admission
            app.state.role_service = RoleService(journeys, catalog)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("192.0.2.1", 50000)), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                path = f"/api/v1/journeys/{journey.journey_id}/roles"
                assert (await client.get(path)).json()["code"] == "PROFILE_NOT_CONFIRMED"
                from app.contracts.journey import ProfileUpdate
                body = ready_edit().model_dump(mode="json")
                body["draft"]["experiences"][0]["skill_tags"] = ["낭독"]
                await journeys.update_profile(issued.session, journey.journey_id, ProfileUpdate.model_validate(body))
                confirmed = await journeys.confirm_profile(issued.session, journey.journey_id, 2)
                response = await client.get(path)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                assert response.json()["profile_version"] == confirmed.profile.version
                snapshot = await journeys.resolve_profile(issued.session, confirmed.profile)
                assert response.json()["items"][0]["evidence"][0]["experience_id"] == str(snapshot.content.experiences[0].id)
                assert (await client.get(path + "?profile_version=99")).status_code == 409
    with_redis(scenario)
