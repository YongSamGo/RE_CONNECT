"""운영 초안을 동의로 취급하지 않는 공개 안내문 경계. 모든 본문은 가상 자료다."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.consents.notices import published_catalog


def notice(version='fixture-storage'):
    return dict(version=version, title='가상 저장 안내', controller='가상 시험 주체', contact='시험 문의처',
        aws_region='시험 리전', body='가상 계정과 저장 자료를 시험합니다.', retention='시험 보관 정책', deletion='시험 삭제 정책')


def settings(**changes):
    return Settings(_env_file=None, app_env='test', **changes)


def publication(**changes):
    return json.dumps(dict(state='approved', ai_processing=None, storage=notice(), **changes), ensure_ascii=False)


def test_default_and_version_only_configuration_never_publish_or_enable_login():
    for config in [settings(), settings(storage_notice_version='fixture-storage')]:
        with TestClient(create_app(config)) as client:
            result = client.get('/api/v1/consents/notices')
            assert result.status_code == 200
            assert result.json() == dict(ai_processing=None, storage=None, login_available=False)
            assert result.headers['cache-control'] == 'no-store' and 'set-cookie' not in result.headers


def test_publication_is_plain_public_data_and_requires_provider_before_login_entry():
    config = settings(storage_notice_version='fixture-storage', consent_notices_json=publication())
    app = create_app(config)
    with TestClient(app) as client:
        response = client.get('/api/v1/consents/notices')
        assert response.json() == dict(ai_processing=None, storage=notice(), login_available=False)
        app.state.oauth_service.adapter = object()  # readiness fixture; not an actual Kakao login
        assert client.get('/api/v1/consents/notices').json()['login_available'] is True
        assert 'consent_notices_json' not in repr(config)


@pytest.mark.parametrize('changes', [
    {'state': 'draft'}, {'storage': {'version': 'fixture-storage'}},
    {'storage': {**notice(), 'version': 'old-version'}}, {'storage': {**notice(), 'controller': ' '}},
    {'storage': {**notice(), 'contact': 'hidden\u202econtact'}}, {'owner_id': 'private-owner'},
])
def test_invalid_draft_incomplete_or_mismatched_publication_is_rejected_without_raw_input(changes):
    value = dict(state='approved', ai_processing=None, storage=notice())
    value.update(changes)
    config = settings(storage_notice_version='fixture-storage', consent_notices_json=json.dumps(value))
    with pytest.raises(ValueError, match='^공개 안내문 구성이 올바르지 않습니다$'):
        published_catalog(config)


def test_notice_cannot_be_published_without_the_same_server_accepted_version():
    with pytest.raises(ValueError, match='공개 안내문'):
        published_catalog(settings(consent_notices_json=publication()))


def test_purposes_are_published_independently_without_inventing_missing_purpose():
    config = settings(ai_notice_version='fixture-ai', consent_notices_json=json.dumps({
        'state': 'approved', 'ai_processing': notice('fixture-ai'), 'storage': None,
    }))
    catalog = published_catalog(config)
    assert catalog.storage is None and catalog.ai_processing.version == 'fixture-ai' and not catalog.login_available
