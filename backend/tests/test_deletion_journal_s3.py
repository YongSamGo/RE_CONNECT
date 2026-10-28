"""운영 S3 삭제 이력: 버킷 보호 확인·덮어쓰기 거절·동일 재전송·변조/다른 객체 거절. AWS에 연결하지 않는다."""

from datetime import timedelta
import io
from uuid import uuid4

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber
import pytest
from pydantic import ValidationError

from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.modules.deletions.journal import (FileDeletionJournal, S3DeletionJournal, UnavailableDeletionJournal,
    build_deletion_journal)
from app.modules.deletions.models import DeletionEvent

BUCKET, OWNER, PREFIX = 'reconnect-deletion-fixture', '111122223333', 'deletion-events/'


def event(deleted_at=None):
    now = deleted_at or utc_now(); owner = uuid4()
    return DeletionEvent(id=uuid4(), owner_id=owner, target_id=owner, scope='account', action='account_delete',
        generation=1, deleted_at=now, expires_at=now + timedelta(days=30))


@pytest.fixture
def stubbed():
    client = boto3.session.Session(aws_access_key_id='fixture', aws_secret_access_key='fixture').client('s3', region_name='ap-northeast-2')
    with Stubber(client) as stub:
        yield S3DeletionJournal(client, BUCKET, OWNER), stub
        stub.assert_no_pending_responses()


def scoped(**params):
    return {'Bucket': BUCKET, 'ExpectedBucketOwner': OWNER, **params}


def body(raw):
    return {'Body': StreamingBody(io.BytesIO(raw), len(raw)), 'ContentLength': len(raw)}


def protected(stub, status='Enabled', retention=None):
    stub.add_response('get_bucket_versioning', {'Status': status}, scoped())
    stub.add_response('get_object_lock_configuration', {'ObjectLockConfiguration': {'ObjectLockEnabled': 'Enabled',
        'Rule': {'DefaultRetention': retention or {'Mode': 'GOVERNANCE', 'Days': 30}}}}, scoped())


def test_check_accepts_only_versioned_object_locked_bucket(stubbed):
    journal, stub = stubbed
    protected(stub); journal.check()
    protected(stub, retention={'Mode': 'COMPLIANCE', 'Years': 1}); journal.check()


@pytest.mark.parametrize('attack', ['versioning_suspended', 'short_retention', 'no_lock', 'other_owner'])
def test_check_fails_closed_when_bucket_can_lose_or_rewrite_history(stubbed, attack):
    journal, stub = stubbed
    if attack == 'versioning_suspended': protected(stub, status='Suspended')
    elif attack == 'short_retention': protected(stub, retention={'Mode': 'GOVERNANCE', 'Days': 7})
    elif attack == 'no_lock':
        stub.add_response('get_bucket_versioning', {'Status': 'Enabled'}, scoped())
        stub.add_client_error('get_object_lock_configuration', 'ObjectLockConfigurationNotFoundError', http_status_code=404, expected_params=scoped())
    else:
        # 같은 이름을 다른 계정이 가져간 버킷에는 ExpectedBucketOwner 불일치로 접근하지 않는다.
        stub.add_client_error('get_bucket_versioning', 'AccessDenied', http_status_code=403, expected_params=scoped())
    with pytest.raises(AppError) as denied: journal.check()
    assert denied.value.code == 'SERVICE_UNAVAILABLE'


def test_append_writes_once_without_overwrite_and_verifies_stored_bytes(stubbed):
    journal, stub = stubbed; value = event(); key = PREFIX + str(value.id) + '.json'; raw = value.model_dump_json().encode()
    stub.add_response('put_object', {}, scoped(Key=key, Body=raw, ContentType='application/json', IfNoneMatch='*', ChecksumAlgorithm='SHA256'))
    stub.add_response('get_object', body(raw), scoped(Key=key))
    journal.append(value)


@pytest.mark.parametrize('code,status', [('PreconditionFailed', 412), ('ConditionalRequestConflict', 409)])
def test_resent_identical_event_is_accepted(stubbed, code, status):
    journal, stub = stubbed; value = event(); key = PREFIX + str(value.id) + '.json'; raw = value.model_dump_json().encode()
    stub.add_client_error('put_object', code, http_status_code=status)
    stub.add_response('get_object', body(raw), scoped(Key=key))
    journal.append(value)


@pytest.mark.parametrize('attack', ['different_existing', 'access_denied', 'oversize_existing'])
def test_append_never_reports_success_for_unverified_history(stubbed, attack):
    journal, stub = stubbed; value = event(); key = PREFIX + str(value.id) + '.json'
    if attack == 'access_denied':
        stub.add_client_error('put_object', 'AccessDenied', http_status_code=403)
    else:
        stub.add_client_error('put_object', 'PreconditionFailed', http_status_code=412)
        other = value.model_copy(update={'generation': 2}).model_dump_json().encode()
        stub.add_response('get_object', body(other if attack == 'different_existing' else b'x' * 2049), scoped(Key=key))
    with pytest.raises(AppError) as denied: journal.append(value)
    assert denied.value.code == 'SERVICE_UNAVAILABLE'


def listing(*items, truncated=False, token=None):
    page = {'Contents': [{'Key': key, 'Size': size, 'LastModified': written} for key, size, written in
        ((item + (utc_now(),))[:3] for item in items)], 'IsTruncated': truncated}
    if token: page['NextContinuationToken'] = token
    return page


def test_events_pages_filters_expired_and_sorts(stubbed):
    journal, stub = stubbed
    old = event(utc_now() - timedelta(days=31)); first = event(utc_now() - timedelta(days=2)); second = event(utc_now() - timedelta(days=1))
    values = [second, old, first]
    keys = [PREFIX + str(value.id) + '.json' for value in values]; raws = [value.model_dump_json().encode() for value in values]
    stub.add_response('list_objects_v2', listing((keys[0], len(raws[0])), truncated=True, token='next'), scoped(Prefix=PREFIX, MaxKeys=1000))
    stub.add_response('get_object', body(raws[0]), scoped(Key=keys[0]))
    stub.add_response('list_objects_v2', listing((keys[1], len(raws[1]), old.deleted_at), (keys[2], len(raws[2]))),
        scoped(Prefix=PREFIX, MaxKeys=1000, ContinuationToken='next'))
    # 쓴 지 30일이 지난 객체(old)는 읽지 않는다.
    stub.add_response('get_object', body(raws[2]), scoped(Key=keys[2]))
    assert journal.events(utc_now()) == [first, second]


def test_expired_objects_awaiting_lifecycle_do_not_consume_recovery_limit(stubbed):
    journal, stub = stubbed; live = event(); key = PREFIX + str(live.id) + '.json'; raw = live.model_dump_json().encode()
    expired = [(PREFIX + str(uuid4()) + '.json', 400, utc_now() - timedelta(days=31)) for _ in range(3)]
    stub.add_response('list_objects_v2', listing(*expired, (key, len(raw))), scoped(Prefix=PREFIX, MaxKeys=1000))
    stub.add_response('get_object', body(raw), scoped(Key=key))
    assert journal.events(utc_now(), limit=1) == [live]


def test_listing_scan_is_bounded_even_when_objects_are_expired(stubbed, monkeypatch):
    from app.modules.deletions import journal as module
    monkeypatch.setattr(module, 'MAX_LISTED_OBJECTS', 2)
    journal, stub = stubbed; old = utc_now() - timedelta(days=31)
    stub.add_response('list_objects_v2', listing(*[(PREFIX + str(uuid4()) + '.json', 400, old) for _ in range(3)]))
    with pytest.raises(AppError): journal.events(utc_now())


@pytest.mark.parametrize('attack', ['foreign_name', 'oversize', 'moved_object', 'unknown_field', 'limit'])
def test_recovery_fails_closed_on_untrusted_or_ambiguous_objects(stubbed, attack):
    journal, stub = stubbed; value = event(); key = PREFIX + str(value.id) + '.json'; raw = value.model_dump_json().encode()
    if attack == 'foreign_name':
        stub.add_response('list_objects_v2', listing((PREFIX + 'notes.txt', 10)))
    elif attack == 'oversize':
        stub.add_response('list_objects_v2', listing((key, 2049)))
    elif attack == 'limit':
        other = event(); other_key = PREFIX + str(other.id) + '.json'
        stub.add_response('list_objects_v2', listing((key, len(raw)), (other_key, 10)))
        stub.add_response('get_object', body(raw), scoped(Key=key))
    else:
        # 다른 이름으로 옮긴 이력·허용하지 않는 필드(원문)를 복구 근거로 쓰지 않는다.
        moved = PREFIX + str(uuid4()) + '.json'
        content = raw if attack == 'moved_object' else raw[:-1] + b',"body":"not allowed"}'
        stub.add_response('list_objects_v2', listing((moved if attack == 'moved_object' else key, len(content))))
        stub.add_response('get_object', body(content), scoped(Key=moved if attack == 'moved_object' else key))
    with pytest.raises(AppError) as denied: journal.events(utc_now(), limit=1 if attack == 'limit' else 1000)
    assert denied.value.code == 'SERVICE_UNAVAILABLE'


def test_prune_deletes_nothing_and_leaves_expiry_to_bucket_lifecycle(stubbed):
    journal, stub = stubbed
    protected(stub)
    assert journal.prune(utc_now()) == 0


def bucket_settings(environment='production', **changes):
    return Settings(_env_file=None, app_env=environment, **{'deletion_journal_bucket': BUCKET,
        'deletion_journal_bucket_owner': OWNER, 'deletion_journal_region': 'ap-northeast-2', **changes})


def test_builder_selects_s3_only_in_production_and_file_only_in_development(tmp_path):
    calls = []
    def factory(service, region):
        calls.append((service, region)); return object()
    journal = build_deletion_journal(bucket_settings(), factory)
    assert isinstance(journal, S3DeletionJournal) and (journal.bucket, journal.owner) == (BUCKET, OWNER)
    assert calls == [('s3', 'ap-northeast-2')]
    assert isinstance(build_deletion_journal(bucket_settings('test'), factory), UnavailableDeletionJournal)
    assert isinstance(build_deletion_journal(bucket_settings('development', deletion_journal_directory=tmp_path), factory), FileDeletionJournal)
    assert isinstance(build_deletion_journal(Settings(_env_file=None, app_env='production', deletion_journal_directory=tmp_path), factory), UnavailableDeletionJournal)
    assert len(calls) == 1


@pytest.mark.parametrize('changes', [{'deletion_journal_bucket_owner': None}, {'deletion_journal_region': None},
    {'deletion_journal_bucket': 'Bad_Bucket'}, {'deletion_journal_bucket_owner': '12345'}, {'deletion_journal_region': 'https://evil.test'}])
def test_partial_or_malformed_bucket_settings_are_rejected(changes):
    with pytest.raises(ValidationError): bucket_settings(**changes)


def test_production_with_bucket_opens_member_storage_without_contacting_aws():
    from tests.test_deletion_contracts import member_settings
    settings = member_settings('production', deletion_journal_bucket=BUCKET, deletion_journal_bucket_owner=OWNER,
        deletion_journal_region='ap-northeast-2')
    app = create_app(settings)
    assert isinstance(app.state.deletion_service.journal, S3DeletionJournal)
    assert app.state.member_storage_enabled is True
