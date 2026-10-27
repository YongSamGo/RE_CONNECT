"""서버가 명시적으로 게시한 안내문만 공개한다. 초안·예제는 기본값에 없다."""

from typing import Literal

from pydantic import BaseModel, ValidationError

from app.contracts.fields import CONTRACT_CONFIG, text
from app.modules.consents.models import NoticeVersion


class PublishedNotice(BaseModel):
    model_config = CONTRACT_CONFIG
    version: NoticeVersion
    title: text(200)
    controller: text(200)
    contact: text(300)
    aws_region: text(100)
    body: text(8000, multiline=True)
    retention: text(2000, multiline=True)
    deletion: text(2000, multiline=True)


class NoticePublication(BaseModel):
    model_config = CONTRACT_CONFIG
    state: Literal['approved']
    ai_processing: PublishedNotice | None
    storage: PublishedNotice | None


class NoticeCatalog(BaseModel):
    model_config = CONTRACT_CONFIG
    ai_processing: PublishedNotice | None = None
    storage: PublishedNotice | None = None
    login_available: bool = False


def published_catalog(settings) -> NoticeCatalog:
    if settings.consent_notices_json is None:
        return NoticeCatalog()
    try:
        publication = NoticePublication.model_validate_json(settings.consent_notices_json)
        for purpose, version in [('ai_processing', settings.ai_notice_version), ('storage', settings.storage_notice_version)]:
            notice = getattr(publication, purpose)
            if notice is not None and notice.version != version:
                raise ValueError
    except (ValidationError, ValueError):
        # Config errors can contain arbitrary input; do not echo that input.
        raise ValueError('공개 안내문 구성이 올바르지 않습니다') from None
    return NoticeCatalog(ai_processing=publication.ai_processing, storage=publication.storage)
