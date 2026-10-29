"""RDS 백업 점검: 자동 백업 7일·수동 스냅샷 만료 태그·삭제 이력 보존기간 안의 복원 가능성.

읽기만 한다. 스냅샷 삭제·변경은 운영자가 확인 후 직접 한다 (docs/security/backup-restore.md).
수동 스냅샷이 30일 삭제 이력보다 오래 남으면 그보다 오래된 삭제를 재적용할 근거가 없으므로 복원 금지로 표시한다.
"""

import argparse
from datetime import date, datetime, timedelta
import json
import re

from botocore.exceptions import BotoCoreError, ClientError

from app.contracts.time import utc_now

AUTOMATED_RETENTION_DAYS = 7
JOURNAL_RETENTION_DAYS = 30
# 점검 뒤 복원·recover까지 걸리는 시간. 그 사이 스냅샷 직후의 삭제 이력이 만료되지 않게 여유를 둔다.
RESTORE_MARGIN = timedelta(days=1)
RESTORABLE_AGE = timedelta(days=JOURNAL_RETENTION_DAYS) - RESTORE_MARGIN
MAX_SNAPSHOTS = 100
_INSTANCE = re.compile(r'^[a-z][a-z0-9-]{0,62}$')
_REGION = re.compile(r'^[a-z]{2}(-[a-z]+)+-[0-9]$')


def tags(snapshot):
    return {tag.get('Key'): tag.get('Value') for tag in snapshot.get('TagList', [])}


def expiry(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value): return None
    try: return date.fromisoformat(value)
    except ValueError: return None


def inspect(client, instance, now):
    if not isinstance(now, datetime) or now.tzinfo is None: raise ValueError('now는 UTC 시각입니다')
    findings = []; today = now.date()
    database = client.describe_db_instances(DBInstanceIdentifier=instance)['DBInstances'][0]
    if database.get('BackupRetentionPeriod') != AUTOMATED_RETENTION_DAYS:
        findings.append({'target': instance, 'problem': 'automated_retention_not_7_days'})
    if database.get('StorageEncrypted') is not True:
        findings.append({'target': instance, 'problem': 'storage_not_encrypted'})
    snapshots = []; marker = None
    while True:
        page = client.describe_db_snapshots(DBInstanceIdentifier=instance, SnapshotType='manual', MaxRecords=100,
            **({'Marker': marker} if marker else {}))
        snapshots.extend(page.get('DBSnapshots', []))
        if len(snapshots) > MAX_SNAPSHOTS: raise ValueError('수동 스냅샷이 점검 한도를 넘었습니다')
        marker = page.get('Marker')
        if not marker: break
    listed = []
    for snapshot in snapshots:
        name = snapshot['DBSnapshotIdentifier']; created = snapshot.get('SnapshotCreateTime')
        labels = tags(snapshot); expires = expiry(labels.get('expires-at'))
        # 날짜가 아니라 시각으로 비교한다. 날짜만 보면 30일을 하루 가까이 넘긴 스냅샷도 통과한다.
        restorable = created is not None and now - created < RESTORABLE_AGE
        listed.append({'snapshot': name, 'created': created.date().isoformat() if created else None,
            'expires_at': expires.isoformat() if expires else None, 'purpose': labels.get('purpose'), 'restorable': restorable})
        if snapshot.get('Encrypted') is not True: findings.append({'target': name, 'problem': 'snapshot_not_encrypted'})
        if expires is None or not labels.get('purpose'): findings.append({'target': name, 'problem': 'missing_expiry_or_purpose_tag'})
        elif created is not None and expires - created.date() > RESTORABLE_AGE:
            findings.append({'target': name, 'problem': 'expiry_beyond_deletion_history'})
        if expires is not None and expires < today: findings.append({'target': name, 'problem': 'expired_delete_after_review'})
        if not restorable: findings.append({'target': name, 'problem': 'older_than_deletion_history_do_not_restore'})
    return {'instance': instance, 'checked_on': today.isoformat(), 'manual_snapshots': listed, 'findings': findings}


def main(argv=None, client_factory=None):
    parser = argparse.ArgumentParser(description='RDS 자동 백업 7일·수동 스냅샷 목록과 만료 점검 (읽기 전용)')
    parser.add_argument('--db-instance', required=True)
    parser.add_argument('--region', required=True)
    args = parser.parse_args(argv)
    if not _INSTANCE.fullmatch(args.db_instance) or not _REGION.fullmatch(args.region): parser.error('DB 식별자 또는 리전 형식')
    if client_factory is None:
        from app.adapters.aws import build_client as client_factory
    try:
        report = inspect(client_factory('rds', args.region), args.db_instance, utc_now())
    except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError):
        # 오류 본문에는 계정·자원 정보가 섞일 수 있어 출력하지 않는다.
        print(json.dumps({'completed': False, 'code': 'SERVICE_UNAVAILABLE'}))
        return 2
    print(json.dumps({'completed': True, **report}, ensure_ascii=False))
    return 1 if report['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
