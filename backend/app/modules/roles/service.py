"""사전에 확인된 태그/별칭과 같은 경험 안의 근거만 사용한다. LLM은 호출하지 않는다."""

import asyncio
from typing import Protocol
from uuid import UUID

from app.contracts.journey import ProfileRef
from app.contracts.profile import ProfileContent
from app.contracts.roles import CatalogRole, RoleCandidate, RoleCandidates, RoleEvidence, RoleExclusionUpdate, RoleExclusions, normalize_tag
from app.core.business_errors import AppError
from app.modules.journeys.service import JourneyService
from app.modules.sessions.service import Session


class RoleCatalog(Protocol):
    def list(self) -> list[CatalogRole]: ...


class UnknownRoleIds(Exception):
    def __init__(self, indices):
        self.indices = tuple(indices)
        super().__init__("역할 사전에 없는 선택")


def match_roles(profile: ProfileContent, catalog: list[CatalogRole], excluded: tuple[str, ...]) -> list[RoleCandidate]:
    if len({item.id for item in profile.experiences}) != len(profile.experiences) or len({r.id for r in catalog}) != len(catalog):
        raise ValueError("중복된 근거 또는 역할 식별자")
    candidates = []
    for role in catalog:
        canonical = {normalize_tag(tag): normalize_tag(tag) for tag in role.skill_tags}
        canonical.update({normalize_tag(a.alias): normalize_tag(a.skill_tag) for a in role.aliases})
        evidence = []
        for experience in profile.experiences:
            matched = {canonical[normalize_tag(tag)] for tag in experience.skill_tags if normalize_tag(tag) in canonical}
            if role.experience_rules:
                supported = any(
                    {normalize_tag(tag) for tag in rule.skill_tags} <= matched if rule.operator == "all"
                    else bool({normalize_tag(tag) for tag in rule.skill_tags} & matched)
                    for rule in role.experience_rules
                )
            else:
                supported = bool(matched)
            if supported:
                # 별칭을 프로필에 새 사실로 쓰지 않고, 실제 경험에 있던 원래 태그를 근거로 반환한다.
                tags = [tag for tag in experience.skill_tags if normalize_tag(tag) in canonical]
                evidence.append(RoleEvidence(experience_id=experience.id, skill_tags=tags))
        if evidence:
            candidates.append(RoleCandidate(role_id=role.id, name=role.name, description=role.description,
                                            evidence=evidence, excluded=role.id in excluded))
    return sorted(candidates, key=lambda item: (-len(item.evidence), item.role_id))[:20]


class RoleService:
    def __init__(self, journeys: JourneyService, catalog: RoleCatalog):
        self.journeys, self.catalog = journeys, catalog

    async def catalog_entries(self) -> list[CatalogRole]:
        return await asyncio.to_thread(self.catalog.list)

    async def candidates(self, session: Session, journey_id: UUID, profile_version: int | None = None) -> RoleCandidates:
        state = await self.journeys.role_state(session, journey_id)
        version = state.profile_version if profile_version is None else profile_version
        snapshot = await self.journeys.resolve_profile(session, ProfileRef(kind="journey", id=journey_id, version=version),
                                                       require_current=profile_version is None)
        catalog = await asyncio.to_thread(self.catalog.list)
        try:
            items = match_roles(snapshot.content, catalog, state.role_ids)
        except ValueError:
            raise AppError("SERVICE_UNAVAILABLE") from None
        current = await self.journeys.role_state(session, journey_id)
        if current.revision != state.revision:
            raise AppError("VERSION_CONFLICT")
        return RoleCandidates(profile_version=version, revision=current.revision, items=items)

    async def set_exclusions(self, session: Session, journey_id: UUID, body: RoleExclusionUpdate) -> RoleExclusions:
        state = await self.journeys.role_state(session, journey_id)
        if body.base_revision != state.revision:
            raise AppError("VERSION_CONFLICT")
        known = {role.id for role in await asyncio.to_thread(self.catalog.list)} if body.role_ids else set()
        invalid = [index for index, value in enumerate(body.role_ids) if value not in known]
        if invalid:
            raise UnknownRoleIds(invalid)
        return await self.journeys.set_role_exclusions(session, journey_id, body.role_ids, body.base_revision)

    async def excluded_role_ids(self, session: Session, journey_id: UUID) -> frozenset[str]:
        return frozenset((await self.journeys.role_state(session, journey_id)).role_ids)
