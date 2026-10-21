"""DB 밖 개발용 이력의 제한 경로·권한·동일 요청·변조/다른 파일 거절."""

from datetime import timedelta
import os
from uuid import uuid4

import pytest

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.modules.deletions.journal import FileDeletionJournal
from app.modules.deletions.models import DeletionEvent

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Linux POSIX 폴더/파일 권한·fsync 검증')


def event():
    now = utc_now(); owner = uuid4()
    return DeletionEvent(id=uuid4(), owner_id=owner, target_id=owner, scope='account', action='account_delete',
        generation=1, deleted_at=now, expires_at=now + timedelta(days=30))


def test_actual_separate_file_journal_roundtrip_idempotence_and_expiry(tmp_path):
    tmp_path.chmod(0o700); journal = FileDeletionJournal(tmp_path); value = event()
    journal.check(); journal.append(value); journal.append(value)
    assert len(list(tmp_path.iterdir())) == 1
    assert journal.events(utc_now()) == [value]
    assert journal.events(value.expires_at) == []
    assert next(tmp_path.iterdir()).stat().st_mode & 0o777 == 0o600
    with pytest.raises(AppError): journal.append(value.model_copy(update={'owner_id': uuid4(), 'target_id': uuid4()}))
    assert journal.prune(utc_now()) == 0
    assert journal.prune(value.expires_at) == 1 and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('attack', ['directory_permission', 'symlink_file', 'fifo', 'oversize', 'hardlink', 'wrong_owner_scope', 'unknown_field'])
def test_recovery_fails_closed_on_untrusted_or_ambiguous_files(tmp_path, attack):
    tmp_path.chmod(0o700); journal = FileDeletionJournal(tmp_path); value = event(); path = tmp_path / (str(value.id) + '.json')
    if attack == 'directory_permission': tmp_path.chmod(0o755)
    elif attack == 'symlink_file':
        other = tmp_path.parent / (uuid4().hex + '.fixture'); other.write_text(value.model_dump_json()); path.symlink_to(other)
    elif attack == 'fifo': os.mkfifo(path, 0o600)
    elif attack == 'oversize': path.write_text('x' * 2049); path.chmod(0o600)
    elif attack == 'hardlink':
        journal.append(value); os.link(path, tmp_path.parent / (uuid4().hex + '.fixture'))
    elif attack == 'wrong_owner_scope':
        path.write_text(value.model_copy(update={'scope': 'profile'}).model_dump_json()); path.chmod(0o600)
    else:
        path.write_text(value.model_dump_json()[:-1] + ',"body":"not allowed"}'); path.chmod(0o600)
    with pytest.raises(AppError): journal.events(utc_now())


def test_configured_directory_symlink_is_rejected_without_writing(tmp_path):
    target = tmp_path / 'real'; target.mkdir(mode=0o700)
    alias = tmp_path / 'alias'; alias.symlink_to(target)
    with pytest.raises(AppError): FileDeletionJournal(alias).append(event())
    assert list(target.iterdir()) == []
