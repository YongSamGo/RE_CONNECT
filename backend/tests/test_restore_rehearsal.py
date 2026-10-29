"""W12-06 로컬 복원 리허설: 실제 pg_dump 스냅숏·별도 DB 복원·잠금 S3 삭제 이력·migrate·공개 전 확인.

운영 RDS·S3가 아니다. 잠금 S3 에뮬레이터와 PostgreSQL이 있을 때만 실행한다 (docs/security/backup-restore.md).
  RESTORE_REHEARSAL_S3_ENDPOINT  S3 호환 엔드포인트(Object Lock 지원). 접근 키는 boto3 기본 환경변수로 준다.
  RESTORE_REHEARSAL_S3_OWNER     에뮬레이터 버킷 소유 계정(12자리)
  RESTORE_REHEARSAL_EVIDENCE     선택. 건수만 담은 증거 JSON을 쓸 경로(security-reports/ 아래 권장)
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import UUID, uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.modules.auth.member_cleanup import RedisMemberCleanup
from app.modules.deletions.journal import S3DeletionJournal
from app.modules.deletions.repository import SqlDeletionRepository
from app.modules.deletions.service import DeletionService
from app.persistence import User
from manage_restore import check
from tests.test_member_auth import headers
from tests.test_member_lifecycle_matrix import member_rows, reauth, sql_traces
from tests.test_migrations import migration_config
from tests.test_save_intents import run
from tests.test_saved_material_editing import editing

ENDPOINT = os.environ.get('RESTORE_REHEARSAL_S3_ENDPOINT')
DATABASE = os.environ.get('PERSISTENCE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not (ENDPOINT and DATABASE and shutil.which('pg_dump') and shutil.which('psql')),
    reason='로컬 복원 리허설 환경(잠금 S3 에뮬레이터·PostgreSQL·pg_dump) 없음')


def locked_bucket():
    import boto3
    client = boto3.client('s3', endpoint_url=ENDPOINT, region_name='ap-northeast-2')
    bucket = 'rehearsal-' + uuid4().hex[:12]
    # 운영 템플릿(infra/backup/deletion-journal.json)과 같은 보호: 버전 관리·Object Lock GOVERNANCE 30일.
    client.create_bucket(Bucket=bucket, CreateBucketConfiguration={'LocationConstraint': 'ap-northeast-2'}, ObjectLockEnabledForBucket=True)
    client.put_object_lock_configuration(Bucket=bucket, ObjectLockConfiguration={'ObjectLockEnabled': 'Enabled',
        'Rule': {'DefaultRetention': {'Mode': 'GOVERNANCE', 'Days': 30}}})
    return client, bucket


def libpq_env(database=None):
    url = make_url(DATABASE)
    return {**os.environ, 'PGHOST': url.host or '127.0.0.1', 'PGPORT': str(url.port or 5432), 'PGUSER': url.username or '',
        'PGPASSWORD': url.password or '', 'PGDATABASE': database or url.database}


def snapshot(schema, path):
    """삭제 전 시점의 DB 덤프. pg_dump 17이 내는 16 미지원 설정 한 줄만 뺀다."""
    dump = subprocess.run(['pg_dump', '--no-owner', '--no-privileges', '-n', schema], env=libpq_env(),
        check=True, capture_output=True, text=True).stdout
    path.write_text('\n'.join(line for line in dump.splitlines() if not line.startswith('SET transaction_timeout')), encoding='utf-8')


def test_isolated_snapshot_restore_reapplies_latest_deletions_before_publish(tmp_path):
    client, bucket = locked_bucket()
    journal = S3DeletionJournal(client, bucket, os.environ.get('RESTORE_REHEARSAL_S3_OWNER', '000000000000'))
    evidence = {}

    async def scenario(ctx, browser):
        ctx['journeys'].consents = ctx['consents']
        cleanup = RedisMemberCleanup(ctx['members'].store)
        service = DeletionService(SqlDeletionRepository(sessionmaker(ctx['engine']).begin), journal,
            ctx['members'], ctx['intents'].policy, cleanup)
        ctx['app'].state.deletion_service = service
        _, document, _, _, _ = await editing(ctx, browser)
        user_id = UUID((await browser.get('/api/v1/me')).json()['user']['id'])
        with ctx['engine'].connect() as db:
            schema = db.scalar(text('select current_schema()'))
            subject = db.scalar(select(User.kakao_subject).where(User.id == user_id))

        # 1. 스냅숏(복원 지점) 뒤에 지원서 삭제와 탈퇴가 일어난다. 이력은 DB가 아니라 잠금 버킷에 남는다.
        dump = tmp_path / 'snapshot.sql'; snapshot(schema, dump)
        assert (await browser.delete('/api/v1/drafts/' + document['document_id'], headers=headers(browser))).status_code == 204
        await reauth(browser)
        assert (await browser.delete('/api/v1/me', headers=headers(browser))).status_code == 204
        versions = client.list_object_versions(Bucket=bucket)['Versions']
        assert len(versions) == 2
        with pytest.raises(client.exceptions.ClientError) as denied:
            client.delete_object(Bucket=bucket, Key=versions[0]['Key'], VersionId=versions[0]['VersionId'])
        assert denied.value.response['Error']['Code'] == 'AccessDenied'
        evidence['journal_objects_locked'] = len(versions)

        # 2. 격리 복원: 운영 DB가 아닌 새 DB에 스냅숏을 올린다.
        restored_name = 'restored_' + uuid4().hex[:12]
        admin = create_engine(DATABASE, isolation_level='AUTOCOMMIT')
        with admin.connect() as db: db.exec_driver_sql(f'CREATE DATABASE "{restored_name}"')
        restored = create_engine(make_url(DATABASE).set(database=restored_name), connect_args={'options': f'-csearch_path={schema}'})
        try:
            subprocess.run(['psql', '-q', '-v', 'ON_ERROR_STOP=1', '-f', str(dump)], env=libpq_env(restored_name),
                check=True, capture_output=True)
            restored_ctx = {'engine': restored}
            assert {table.name for table, _ in member_rows(restored_ctx, user_id)} >= {'users', 'profile_versions', 'application_drafts'}
            evidence['restored_member_tables'] = len({table.name for table, _ in member_rows(restored_ctx, user_id)})
            restored_service = DeletionService(SqlDeletionRepository(sessionmaker(restored).begin), journal, None, None, cleanup)

            # 3. 옛 스키마의 스냅숏이면 재적용하지 않고 닫는다. migrate 뒤에만 진행한다.
            with restored.begin() as db: command.downgrade(migration_config(db), '-1')
            behind = await check(restored_service, restored, 1000)
            assert behind['problems'] == {'schema_not_current': 1} and len(member_rows(restored_ctx, user_id)) > 0
            with restored.begin() as db: command.upgrade(migration_config(db), 'head')

            # 4. 재적용 전 확인은 공개를 막고, 재적용 뒤에만 연다.
            stale = await check(restored_service, restored, 1000, reapply=False)
            assert stale['ready_to_publish'] is False
            assert stale['problems'] == {'record_missing': 2, 'session_not_revoked': 2, 'target_remains': 2}
            result = await check(restored_service, restored, 1000)
            assert result == {'reapplied': 2, 'retried': 0, 'checked_events': 2, 'ready_to_publish': True, 'problems': {}}
            again = await check(restored_service, restored, 1000, reapply=False)
            assert again['ready_to_publish'] is True
            # 5. 복원 DB에 회원 흔적(회원 ID·카카오 식별자)이 최소 이력 표 밖에 없다.
            assert sql_traces(restored_ctx, user_id, subject) == set()
            evidence.update(schema_behind=behind['problems'], before_reapply=stale['problems'], after_reapply=result,
                verify_only=again['ready_to_publish'], member_traces_after=0)
        finally:
            restored.dispose()
            with admin.connect() as db: db.exec_driver_sql(f'DROP DATABASE IF EXISTS "{restored_name}" WITH (FORCE)')
            admin.dispose()

    run(tmp_path, scenario, 'postgresql')
    target = os.environ.get('RESTORE_REHEARSAL_EVIDENCE')
    if target:
        # 건수·판정만 남긴다. 회원 ID·대상 ID·버킷 이름·본문은 넣지 않는다.
        Path(target).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
