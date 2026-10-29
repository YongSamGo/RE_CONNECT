"""운영자 공고 업무 규칙. 운영자 인가(역할·MFA)는 라우터가 먼저 확인한다."""

import asyncio
from typing import Protocol
from uuid import UUID

from app.core.business_errors import AppError
from app.modules.admin_opportunities.models import (
    AdminOpportunity, AdminOpportunityList, AdminOpportunitySearch, OpportunityCreate, OpportunityPatch,
)
from app.modules.requests.service import input_fingerprint


class AdminOpportunityRepository(Protocol):
    def list(self, search: AdminOpportunitySearch) -> AdminOpportunityList: ...
    def get(self, opportunity_id: UUID) -> AdminOpportunity | None: ...
    def create(self, operator_id: UUID, key_id: UUID, fingerprint: str, body: OpportunityCreate, request_id: str) -> AdminOpportunity: ...
    def update(self, operator_id: UUID, opportunity_id: UUID, patch: OpportunityPatch, request_id: str) -> AdminOpportunity: ...


class AdminOpportunityService:
    def __init__(self, repository: AdminOpportunityRepository):
        self.repository = repository

    async def list(self, search: AdminOpportunitySearch) -> AdminOpportunityList:
        return await asyncio.to_thread(self.repository.list, search)

    async def get(self, opportunity_id: UUID) -> AdminOpportunity:
        view = await asyncio.to_thread(self.repository.get, opportunity_id)
        if view is None:
            raise AppError("NOT_FOUND")
        return view

    async def create(self, operator_id: UUID, key: str, body: OpportunityCreate, request_id: str) -> AdminOpportunity:
        try:
            # OpenAPI §IdempotencyKey: UUID. 대소문자만 다른 표기도 같은 키로 보지 않고 거절한다.
            key_id = UUID(key)
            if str(key_id) != key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AppError("VALIDATION_FAILED") from None
        fingerprint = input_fingerprint(body.model_dump(mode="json"))
        return await asyncio.to_thread(self.repository.create, operator_id, key_id, fingerprint, body, request_id)

    async def update(self, operator_id: UUID, opportunity_id: UUID, patch: OpportunityPatch, request_id: str) -> AdminOpportunity:
        return await asyncio.to_thread(self.repository.update, operator_id, opportunity_id, patch, request_id)
