from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, model_validator

from app.contracts.fields import CONTRACT_CONFIG
from app.contracts.time import UtcDatetime

Action = Literal['profile_delete', 'application_delete', 'storage_withdraw', 'ai_withdraw', 'account_delete']


class DeletionEvent(BaseModel):
    model_config = {**CONTRACT_CONFIG, 'frozen': True}
    schema_version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    id: UUID
    owner_id: UUID
    scope: Literal['account', 'profile', 'application']
    target_id: UUID
    action: Action
    generation: Annotated[StrictInt, Field(ge=1, lt=2147483647)]
    deleted_at: UtcDatetime
    expires_at: UtcDatetime

    @model_validator(mode='after')
    def consistent(self):
        expected = {'profile_delete': 'profile', 'storage_withdraw': 'profile', 'application_delete': 'application',
            'ai_withdraw': 'account', 'account_delete': 'account'}[self.action]
        if self.scope != expected or self.expires_at != self.deleted_at + timedelta(days=30):
            raise ValueError('삭제 이력 형식을 확인해 주세요')
        if self.scope == 'account' and self.target_id != self.owner_id:
            raise ValueError('삭제 범위를 확인해 주세요')
        return self


class WithdrawRequest(BaseModel):
    model_config = CONTRACT_CONFIG
    purpose: Literal['ai_processing', 'storage']


class DeletedCounts(BaseModel):
    model_config = CONTRACT_CONFIG
    journeys: int
    profile_versions: int
    documents: int


class WithdrawResult(BaseModel):
    model_config = CONTRACT_CONFIG
    purpose: Literal['ai_processing', 'storage']
    withdrawn_at: UtcDatetime
    deleted: DeletedCounts
