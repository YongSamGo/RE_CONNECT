"""역할 후보·제외 계약과 운영 역할 사전의 엄격한 내부 구조."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator

from app.contracts.fields import CONTRACT_CONFIG, SkillTag, Unique, text
from app.contracts.opportunity import RoleId


def normalize_tag(value: str) -> str:
    return " ".join(value.split()).casefold()


class SkillAlias(BaseModel):
    model_config = CONTRACT_CONFIG
    alias: SkillTag
    skill_tag: SkillTag


class ExperienceRule(BaseModel):
    model_config = CONTRACT_CONFIG
    operator: Literal["all", "any"]
    skill_tags: Annotated[list[SkillTag], Field(min_length=1, max_length=20), Unique]


class CatalogRole(BaseModel):
    model_config = CONTRACT_CONFIG
    id: RoleId
    name: text(50)
    description: text(300)
    skill_tags: Annotated[list[SkillTag], Field(max_length=20), Unique]
    aliases: Annotated[list[SkillAlias], Field(max_length=100)]
    experience_rules: Annotated[list[ExperienceRule], Field(max_length=20)]

    @model_validator(mode="after")
    def known_canonical_tags(self):
        canonical = {normalize_tag(tag) for tag in self.skill_tags}
        if len(canonical) != len(self.skill_tags):
            raise ValueError("정규화 후 중복된 역량 태그")
        seen = set(canonical)
        for alias in self.aliases:
            name, target = normalize_tag(alias.alias), normalize_tag(alias.skill_tag)
            if name in seen or target not in canonical:
                raise ValueError("별칭의 대상 또는 중복을 확인해야 합니다")
            seen.add(name)
        if any(not {normalize_tag(tag) for tag in rule.skill_tags} <= canonical for rule in self.experience_rules):
            raise ValueError("연결 규칙은 확인된 사전 태그만 사용합니다")
        return self


class RoleEvidence(BaseModel):
    model_config = CONTRACT_CONFIG
    experience_id: UUID
    skill_tags: Annotated[list[SkillTag], Field(min_length=1, max_length=20), Unique]


class RoleCandidate(BaseModel):
    model_config = CONTRACT_CONFIG
    role_id: RoleId
    name: text(50)
    description: text(300)
    evidence: Annotated[list[RoleEvidence], Field(min_length=1, max_length=20)]
    excluded: StrictBool


class RoleCandidates(BaseModel):
    model_config = CONTRACT_CONFIG
    profile_version: Annotated[StrictInt, Field(ge=1)]
    items: Annotated[list[RoleCandidate], Field(max_length=20)]
    revision: Annotated[StrictInt, Field(ge=1)]


class RoleExclusionUpdate(BaseModel):
    model_config = CONTRACT_CONFIG
    role_ids: Annotated[list[RoleId], Field(max_length=50), Unique]
    base_revision: Annotated[StrictInt, Field(ge=1, lt=2**31 - 1)]


class RoleExclusions(BaseModel):
    model_config = CONTRACT_CONFIG
    role_ids: Annotated[list[RoleId], Field(max_length=50), Unique]
    revision: Annotated[StrictInt, Field(ge=1)]
