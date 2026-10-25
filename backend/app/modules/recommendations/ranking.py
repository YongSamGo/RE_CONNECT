"""확정 사실의 집합 계산. 내부 점수는 응답에 노출하지 않는다."""

from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction

from app.contracts.profile import ProfileContent
from app.contracts.recommendation import RecommendationMatch
from app.contracts.roles import CatalogRole, normalize_tag
from app.contracts.time import kst_date
from app.modules.recommendations.filters import Candidate
from app.modules.roles.service import match_roles


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: Fraction
    matched: RecommendationMatch


def tokens(*values: str | None) -> set[str]:
    return {token for value in values if value for token in normalize_tag(value).split() if len(token) >= 2}


def alias_map(catalog: list[CatalogRole]) -> dict[str, str]:
    mapping = {}
    canonical = {normalize_tag(tag) for role in catalog for tag in role.skill_tags}
    for role in catalog:
        for alias in role.aliases:
            name, target = normalize_tag(alias.alias), normalize_tag(alias.skill_tag)
            if name in canonical or name in mapping and mapping[name] != target:
                raise ValueError("역할 간 충돌하는 사전 별칭")
            mapping[name] = target
    return mapping


def deadline_key(scored: ScoredCandidate):
    opportunity = scored.candidate.opportunity
    precise = opportunity.deadline_at
    day = kst_date(precise) if precise else opportunity.deadline_date
    # 날짜만 있는 마감에 정확한 시각을 부여하지 않는다. 같은 날의 알려진 시각 뒤에 둔다.
    return (day is None, day.toordinal() if day else 0, precise is None,
            precise or datetime.max.replace(tzinfo=UTC), opportunity.id.int)


def rank_candidates(profile: ProfileContent, candidates: list[Candidate], catalog: list[CatalogRole]) -> list[ScoredCandidate]:
    aliases = alias_map(catalog)
    def canonical(tag):
        value = normalize_tag(tag)
        return aliases.get(value, value)

    profile_tags = {canonical(tag) for tag in profile.skills}
    profile_tags.update(canonical(tag) for experience in profile.experiences for tag in experience.skill_tags)
    experience_tokens = {experience.id: tokens(experience.description, experience.duration_note, *experience.skill_tags)
                         for experience in profile.experiences}
    profile_tokens = tokens(*profile.skills)
    for values in experience_tokens.values():
        profile_tokens.update(values)
    roles = {role.id: role for role in catalog}
    ranked = []
    for candidate in candidates:
        opportunity = candidate.opportunity
        opportunity_tags = {canonical(tag) for tag in opportunity.skill_tags}
        opportunity_tokens = tokens(opportunity.title, opportunity.description_text, *opportunity.skill_tags,
                                    *opportunity.role_tags, *(roles[id].name for id in opportunity.role_tags if id in roles))
        shared_tags = profile_tags & opportunity_tags
        union = profile_tags | opportunity_tags
        shared_tokens = profile_tokens & opportunity_tokens
        skill_score = Fraction(len(shared_tags), len(union)) if union else Fraction(0)
        keyword_score = Fraction(len(shared_tokens), len(profile_tokens)) if profile_tokens else Fraction(0)
        score = Fraction(7, 10) * skill_score + Fraction(3, 10) * keyword_score
        if score == 0:
            continue
        evidence = [experience.id for experience in profile.experiences
                    if {canonical(tag) for tag in experience.skill_tags} & opportunity_tags]
        if not evidence:
            continue
        matched_roles = [id for id in opportunity.role_tags if id in roles and match_roles(profile, [roles[id]], ())]
        original_tags = sorted({tag for tag in [*profile.skills, *(tag for e in profile.experiences for tag in e.skill_tags)]
                                if canonical(tag) in shared_tags})
        ranked.append(ScoredCandidate(candidate, score, RecommendationMatch(
            experience_ids=evidence, skill_tags=original_tags,
            # 자유 문장 조각은 순위 계산에만 쓰고 공개 근거로 표시하지 않는다.
            keywords=[], role_ids=matched_roles,
        )))
    return sorted(ranked, key=lambda value: (-value.score, deadline_key(value)))[:5]
