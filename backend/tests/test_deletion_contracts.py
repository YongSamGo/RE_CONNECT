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
