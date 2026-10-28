"""근거 선택 → 서버 재검증 → 사용자 확인용 미승인 미리보기.

호출자는 먼저 동의·소유권·확정 버전·호출 한도를 확인해야 한다. 이 모듈은
라우트/DB/Redis를 제공하지 않으며 결과 저장 전 수명·리비전 재검사도 호출자 책임이다.
"""

import json
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.adapters.llm import LLMAdapter, LLMInvalidOutputError, OutputT, UntrustedTurn
from app.contracts.profile import Experience, ExperienceInput, RecommendationField
from app.contracts.roles import normalize_tag
from app.modules.generation import prompts, wording
from app.modules.generation.models import (
    ApplicationPlan,
    ApplicationContext,
    ApplicationPreview,
    ConfirmedProfileSnapshot,
    ExperiencePreview,
    ExtractionPlan,
    QuestionPlan,
    Quote,
)
from app.modules.generation.privacy import safe_text

_QUESTIONS: dict[RecommendationField, str] = {
    "experiences": "지금까지 해 보신 일이나 활동 한 가지를 말씀해 주시겠어요?",
    "preferred_regions": "어느 지역에서 활동하고 싶으세요?",
    "activity_types": "취업과 봉사 중 어떤 활동을 원하세요?",
}


class GenerationInputError(ValueError):
    """안전하게 쓸 입력이 없음. 메시지에 본문을 담지 않는다."""


def _unique(tags: list[str]) -> list[str]:
    """공백·대소문자만 다른 태그는 처음 것 하나만 남긴다."""
    seen, result = set(), []
    for tag in tags:
        if normalize_tag(tag) not in seen:
            seen.add(normalize_tag(tag))
            result.append(tag)
    return result


def _invalid() -> LLMInvalidOutputError:
    return LLMInvalidOutputError("모델 결과의 근거를 확인하지 못했습니다")


class GroundedGenerationService:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def _generate(self, instructions: str, data: dict, model: type[OutputT]) -> OutputT:
        result = await self._adapter.generate_structured(
            instructions=instructions,
            untrusted_turns=[UntrustedTurn(role="user", text=json.dumps(data, ensure_ascii=False))],
            output_model=model,
        )
        # 다른 Adapter 구현·테스트 대역의 반환값도 스키마로 다시 검사한다.
        try:
            if not isinstance(result, BaseModel):
                raise _invalid()
            return model.model_validate(result.model_dump())
        except ValidationError:
            raise _invalid() from None

    async def extract_experiences(
        self, *, user_texts: Sequence[str], existing_experiences: Sequence[Experience] = (),
        standard_tags: Sequence[str] = (),
    ) -> ExperiencePreview:
        """standard_tags: 역할 사전의 표준 기술 태그(서버 자료). 모델은 이 안에서만 고를 수 있다."""
        if isinstance(user_texts, (str, bytes)) or not 1 <= len(user_texts) <= 64 or len(existing_experiences) > 20:
            raise GenerationInputError("입력 개수를 확인해 주세요")
        # 별도 인덱스를 유지해 제외된 턴을 다른 턴의 근거로 바꾸지 않는다.
        turns = {index: cleaned for index, value in enumerate(user_texts) if (cleaned := safe_text(value)) is not None}
        if not turns:
            raise GenerationInputError("개인정보를 제외하고 경험을 직접 입력해 주세요")
        if sum(len(value.encode("utf-8")) for value in turns.values()) > 12000:
            raise GenerationInputError("입력 길이를 줄여 주세요")
        existing = {item.id: item for item in existing_experiences}
        if len(existing) != len(existing_experiences):
            raise GenerationInputError("기존 경험 목록을 확인해 주세요")
        # 기존 본문 전체·다른 개인정보는 전달하지 않는다. 안전한 설명만 비교 자료로 전달한다.
        allowed = {key: item for key, item in existing.items() if safe_text(item.description) is not None}
        catalog = {normalize_tag(tag): tag for tag in standard_tags}
        if len(catalog) > 200:
            raise GenerationInputError("표준 태그 목록을 확인해 주세요")
        plan = await self._generate(prompts.EXTRACTION, {
            "turns": [{"turn_index": index, "text": value} for index, value in turns.items()],
            "existing_experiences": [{"id": str(key), "description": item.description} for key, item in allowed.items()],
            "standard_tags": list(catalog.values()),
        }, ExtractionPlan)

        def grounded(quote: Quote, turn_index: int) -> bool:
            source = turns.get(quote.turn_index)
            return quote.turn_index == turn_index and source is not None and quote.text in source and safe_text(quote.text) is not None

        def quote_value(quote: Quote, turn_index: int) -> str:
            if not grounded(quote, turn_index):
                raise _invalid()
            return quote.text

        proposals, source_turns = [], []
        used_ids = set()
        try:
            for item in plan.experiences:
                index = item.description.turn_index
                quote = quote_value(item.description, index)
                summary = item.summary if wording.summary_grounded(item.summary, turns[index]) else None
                if item.existing_id is not None:
                    if item.existing_id not in allowed or item.existing_id in used_ids:
                        raise _invalid()
                    used_ids.add(item.existing_id)
                    # 기존 경험은 다듬은 문구로 저장돼 있을 수 있다. 문구가 다르면 교체하지 않고 이 선택만 버린다.
                    if allowed[item.existing_id].description not in {quote, summary}:
                        continue
                # 설명은 경험 자체라 근거가 없으면 전체를 거절한다. 기간·기술은 다른 턴에서 가져오는 일이
                # 잦아(docs/ai/extraction-eval-2026-10-22.md) 근거 없는 인용만 버리고 같은 턴의 것만 남긴다.
                # 표준 태그를 먼저 두고, 사전에 없는 원문 기술 구절은 정보를 잃지 않게 뒤에 남긴다.
                tags = [catalog[normalize_tag(tag)] for tag in item.standard_tags if normalize_tag(tag) in catalog]
                tags += [skill.text for skill in item.skills if grounded(skill, index)]
                proposals.append(ExperienceInput(
                    id=item.existing_id,
                    description=allowed[item.existing_id].description if item.existing_id else summary or quote,
                    duration_note=wording.duration_label(item.duration.text) if item.duration and grounded(item.duration, index) else None,
                    skill_tags=_unique(tags)[:20],
                ))
                source_turns.append(index)
        except ValidationError:
            raise _invalid() from None
        return ExperiencePreview(
            experiences=proposals,
            source_turns=source_turns,
            excluded_turn_indices=[index for index in range(len(user_texts)) if index not in turns],
        )

    @staticmethod
    def _question_fields(missing_fields: Sequence[RecommendationField]) -> list[RecommendationField]:
        fields = list(dict.fromkeys(missing_fields))
        if any(field not in _QUESTIONS for field in fields):
            raise GenerationInputError("질문 항목을 확인해 주세요")
        return fields

    @classmethod
    def fallback_question(cls, *, missing_fields: Sequence[RecommendationField]) -> str | None:
        """모델 없이 누락 항목의 고정 순서로 고른다. 모델 경로와 같은 고정 질문 문장만 쓴다."""
        fields = cls._question_fields(missing_fields)
        return _QUESTIONS[fields[0]] if fields else None

    async def next_question(self, *, missing_fields: Sequence[RecommendationField]) -> str | None:
        fields = self._question_fields(missing_fields)
        if not fields:
            return None
        plan = await self._generate(prompts.QUESTION, {"allowed_fields": fields}, QuestionPlan)
        if plan.field not in fields:
            raise _invalid()
        return _QUESTIONS[plan.field]

    async def application_preview(self, *, snapshot: ConfirmedProfileSnapshot, context: ApplicationContext | None = None) -> ApplicationPreview:
        # 고정 템플릿과 확정 프로필만으로 문장을 조립한다. 모델의 자유 문장은 받지 않는다.
        profile = snapshot.content
        ids = [item.id for item in profile.experiences]
        if len(set(ids)) != len(ids):
            raise GenerationInputError("확정 경험 목록을 확인해 주세요")
        facts: dict[str, str] = {}
        for item in profile.experiences:
            if safe_text(item.description) is not None:
                facts[f"experience:{item.id}"] = f"경험: {item.description}"
            if item.duration_note and safe_text(item.description) is not None and safe_text(item.duration_note) is not None:
                facts[f"duration:{item.id}"] = f"경험 기간 ({item.description}): {item.duration_note}"
        for kind, values, label in (
            ("skill", profile.skills, "역량"),
            ("certification", profile.certifications or [], "자격"),
            ("course", profile.completed_courses or [], "이수 교육"),
        ):
            for index, value in enumerate(values):
                if safe_text(value) is not None:
                    facts[f"{kind}:{index}"] = f"{label}: {value}"
        if not facts:
            raise GenerationInputError("확정한 경험을 확인해 주세요")
        data = {"facts": facts}
        if context is not None:
            data['opportunity_context'] = context.model_dump(mode='json')
        plan = await self._generate(prompts.APPLICATION, data, ApplicationPlan)
        if any(key not in facts for key in plan.fact_ids):
            raise _invalid()
        return ApplicationPreview(
            profile_id=snapshot.profile_id,
            profile_version=snapshot.version,
            paragraphs=[facts[key] for key in plan.fact_ids],
        )
