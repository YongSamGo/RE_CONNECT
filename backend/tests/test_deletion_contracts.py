"""운영 대체 금지와 외부 최소 이력의 엄격한 버전·범위·유효기간."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.deletions.models import DeletionEvent


@pytest.mark.parametrize('environment', ['production', 'test'])
def test_development_journal_cannot_activate_production_deletion(environment, tmp_path):
    app = create_app(Settings(_env_file=None, app_env=environment, deletion_journal_directory=tmp_path))
    with pytest.raises(AppError) as denied: app.state.deletion_service.journal.check()
    assert denied.value.code == 'SERVICE_UNAVAILABLE' and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('changes', [{'schema_version': 2}, {'schema_version': True}, {'generation': True}, {'generation': 0}, {'generation': 2147483647},
    {'scope': 'profile'}, {'owner_id': str(uuid4())}, {'body': '본문은 기록하지 않는다'}, {'expires_at': utc_now()}])
def test_recovery_rejects_unknown_or_ambiguous_event(changes):
    owner = uuid4(); now = utc_now()
    with pytest.raises(ValidationError):
        DeletionEvent.model_validate({'id': uuid4(), 'owner_id': owner, 'target_id': owner, 'scope': 'account',
            'action': 'account_delete', 'generation': 1, 'deleted_at': now, 'expires_at': now + timedelta(days=30), **changes})


def member_settings(environment, **changes):
    import json
    def notice(version):
        return dict(version=version, title='가상 안내', controller='가상 시험 주체', contact='시험 문의처',
            aws_region='시험 리전', body='가상 계정과 저장 자료를 시험합니다.', retention='시험 보관 정책', deletion='시험 삭제 정책')
    publication = json.dumps(dict(state='approved', ai_processing=notice('fixture-ai'), storage=notice('fixture-storage')), ensure_ascii=False)
    return Settings(_env_file=None, app_env=environment, public_origin='https://reconnect.test',
        ai_notice_version='fixture-ai', storage_notice_version='fixture-storage', consent_notices_json=publication,
        kakao_rest_api_key='fixture-key', kakao_client_secret='fixture-client-secret', kakao_app_id=123, **changes)


def test_production_without_deletion_journal_closes_storage_consent_and_member_login():
    # 저장은 되는데 탈퇴·삭제·철회가 503인 상태를 운영에서 만들지 않는다.
    from fastapi.testclient import TestClient
    app = create_app(member_settings('production'))
    assert app.state.member_storage_enabled is False
    assert app.state.consent_service.versions['storage'] is None
    assert app.state.consent_service.versions['ai_processing'] == 'fixture-ai'
    assert app.state.oauth_service.adapter is None
    with TestClient(app, base_url='https://reconnect.test') as client:
        catalog = client.get('/api/v1/consents/notices').json()
        assert catalog['storage'] is None and catalog['login_available'] is False
        assert catalog['ai_processing']['version'] == 'fixture-ai'
    # 세션 저장소와 무관하게 로그인 시작 자체가 카카오 주소를 만들지 않는다.
    import asyncio
    with pytest.raises(AppError) as closed:
        asyncio.run(app.state.oauth_service.start(object(), 'login'))
    assert closed.value.code == 'SERVICE_UNAVAILABLE'


@pytest.mark.parametrize('environment', ['development', 'test'])
def test_non_production_keeps_configured_storage_and_login(environment, tmp_path):
    app = create_app(member_settings(environment, deletion_journal_directory=tmp_path))
    assert app.state.member_storage_enabled is True
    assert app.state.consent_service.versions['storage'] == 'fixture-storage'
    assert app.state.notice_catalog.storage.version == 'fixture-storage'
    assert app.state.oauth_service.adapter is not None
