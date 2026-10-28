"""백업·삭제 이력 보존 경계: S3 템플릿 보호 설정과 RDS 스냅샷 점검. AWS에 연결하지 않는다."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import boto3
from botocore.stub import Stubber
import pytest

import manage_backups

TEMPLATE = Path(__file__).resolve().parents[2] / 'infra' / 'backup' / 'deletion-journal.json'
TODAY = datetime(2026, 10, 28, tzinfo=timezone.utc)


def resources():
    return json.loads(TEMPLATE.read_text(encoding='utf-8'))['Resources']


def test_bucket_keeps_history_independent_and_unrewritable_for_30_days():
    bucket = resources()['DeletionJournalBucket']; props = bucket['Properties']
    assert bucket['DeletionPolicy'] == bucket['UpdateReplacePolicy'] == 'Retain'
    assert props['ObjectLockEnabled'] is True and props['VersioningConfiguration'] == {'Status': 'Enabled'}
    assert props['ObjectLockConfiguration']['Rule']['DefaultRetention']['Days'] == 30
    assert all(props['PublicAccessBlockConfiguration'].values())
    expire = props['LifecycleConfiguration']['Rules'][0]
    # 앱은 지우지 않는다. 보존 30일이 끝난 뒤 수명주기가 정리한다.
    assert expire['Prefix'] == 'deletion-events/' and expire['ExpirationInDays'] == 31


def test_runtime_role_cannot_delete_or_weaken_history():
    statements = resources()['DeletionJournalRuntimePolicy']['Properties']['PolicyDocument']['Statement']
    allowed = {action for statement in statements for action in ([statement['Action']] if isinstance(statement['Action'], str) else statement['Action'])}
    assert allowed == {'s3:PutObject', 's3:GetObject', 's3:ListBucket', 's3:GetBucketVersioning', 's3:GetBucketObjectLockConfiguration'}
    assert all(statement['Effect'] == 'Allow' and '*' not in json.dumps(statement['Action']) for statement in statements)
    policy = resources()['DeletionJournalBucketPolicy']['Properties']['PolicyDocument']['Statement']
    denied = {statement['Sid']: statement for statement in policy}
    assert denied['DenyInsecureTransport']['Condition'] == {'Bool': {'aws:SecureTransport': 'false'}}
    assert 's3:BypassGovernanceRetention' in denied['DenyRetentionBypassAndShortening']['Action']
    assert {'s3:DeleteObject', 's3:DeleteObjectVersion', 's3:PutLifecycleConfiguration'} <= set(denied['DenyRuntimeDeleteAndReconfigure']['Action'])


def rds():
    return boto3.session.Session(aws_access_key_id='fixture', aws_secret_access_key='fixture').client('rds', region_name='ap-northeast-2')


def snapshot(name, age_days, expires_in=None, purpose='pre-migration', encrypted=True):
    created = TODAY - timedelta(days=age_days); tags = []
    if expires_in is not None: tags.append({'Key': 'expires-at', 'Value': (created + timedelta(days=expires_in)).date().isoformat()})
    if purpose: tags.append({'Key': 'purpose', 'Value': purpose})
    return {'DBSnapshotIdentifier': name, 'SnapshotCreateTime': created, 'Encrypted': encrypted, 'TagList': tags}


def run(database, *pages, now=TODAY):
    client = rds()
    with Stubber(client) as stub:
        stub.add_response('describe_db_instances', {'DBInstances': [database]}, {'DBInstanceIdentifier': 'reconnect-db'})
        marker = None
        for index, page in enumerate(pages):
            response = {'DBSnapshots': page}
            if index + 1 < len(pages): response['Marker'] = f'page-{index + 1}'
            stub.add_response('describe_db_snapshots', response, {'DBInstanceIdentifier': 'reconnect-db', 'SnapshotType': 'manual',
                'MaxRecords': 100, **({'Marker': marker} if marker else {})})
            marker = response.get('Marker')
        report = manage_backups.inspect(client, 'reconnect-db', now)
        stub.assert_no_pending_responses()
    return report


HEALTHY = {'BackupRetentionPeriod': 7, 'StorageEncrypted': True}


def test_tagged_recent_snapshots_pass_and_are_listed_across_pages():
    report = run(HEALTHY, [snapshot('before-release', 3, expires_in=14)], [snapshot('before-migration', 10, expires_in=29)])
    assert report['findings'] == []
    assert [item['snapshot'] for item in report['manual_snapshots']] == ['before-release', 'before-migration']
    assert all(item['restorable'] for item in report['manual_snapshots'])


@pytest.mark.parametrize('database,item,problem', [
    ({'BackupRetentionPeriod': 35, 'StorageEncrypted': True}, None, 'automated_retention_not_7_days'),
    ({'BackupRetentionPeriod': 7, 'StorageEncrypted': False}, None, 'storage_not_encrypted'),
    # 스택 삭제 시 생기는 최종 스냅샷처럼 태그가 없는 경우
    (HEALTHY, snapshot('final', 1, expires_in=None, purpose=None), 'missing_expiry_or_purpose_tag'),
    (HEALTHY, snapshot('long', 1, expires_in=90), 'expiry_beyond_deletion_history'),
    (HEALTHY, snapshot('edge', 1, expires_in=30), 'expiry_beyond_deletion_history'),
    (HEALTHY, snapshot('stale', 20, expires_in=14), 'expired_delete_after_review'),
    (HEALTHY, snapshot('old', 31, expires_in=29), 'older_than_deletion_history_do_not_restore'),
    (HEALTHY, snapshot('plain', 1, expires_in=7, encrypted=False), 'snapshot_not_encrypted'),
])
def test_unsafe_backup_state_is_reported(database, item, problem):
    report = run(database, [item] if item else [])
    assert problem in {finding['problem'] for finding in report['findings']}


@pytest.mark.parametrize('age,restorable', [(timedelta(days=28, hours=23), True), (timedelta(days=29), False),
    # 날짜 차이는 30일이지만 실제로는 30일 23시간 40분이 지난 경우
    (timedelta(days=30, hours=23, minutes=40), False)])
def test_restorable_uses_exact_time_with_recovery_margin(age, restorable):
    item = {'DBSnapshotIdentifier': 'edge', 'SnapshotCreateTime': TODAY - age, 'Encrypted': True,
        'TagList': [{'Key': 'expires-at', 'Value': (TODAY - age).date().isoformat()}, {'Key': 'purpose', 'Value': 'test'}]}
    report = run(HEALTHY, [item])
    assert report['manual_snapshots'][0]['restorable'] is restorable
    assert ('older_than_deletion_history_do_not_restore' in {finding['problem'] for finding in report['findings']}) is not restorable


def test_inspect_requires_aware_time():
    with pytest.raises(ValueError): manage_backups.inspect(rds(), 'reconnect-db', TODAY.replace(tzinfo=None))


def test_cli_reports_failure_without_error_details(capsys):
    def factory(service, region):
        client = rds(); stub = Stubber(client)
        stub.add_client_error('describe_db_instances', 'AccessDenied', 'arn:aws:iam::111122223333:role/secret-role', 403)
        stub.activate(); return client
    assert manage_backups.main(['--db-instance', 'reconnect-db', '--region', 'ap-northeast-2'], client_factory=factory) == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {'completed': False, 'code': 'SERVICE_UNAVAILABLE'} and '111122223333' not in output


@pytest.mark.parametrize('argv', [['--db-instance', 'Bad_Name', '--region', 'ap-northeast-2'], ['--db-instance', 'reconnect-db', '--region', 'http://x']])
def test_cli_rejects_malformed_targets(argv):
    with pytest.raises(SystemExit): manage_backups.main(argv, client_factory=lambda *args: pytest.fail('AWS 호출 없음'))
