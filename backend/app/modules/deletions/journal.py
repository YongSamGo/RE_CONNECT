"""DB 밖 최신 최소 삭제 이력. 운영은 별도 S3 버킷, 개발은 POSIX 폴더. 어댑터가 없으면 삭제 완료를 꾸미지 않는다."""

import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from botocore.exceptions import BotoCoreError, ClientError

from app.core.business_errors import AppError
from app.modules.deletions.models import DeletionEvent

MAX_EVENT_BYTES = 2048


class UnavailableDeletionJournal:
    def append(self, *args, **kwargs):
        raise AppError('SERVICE_UNAVAILABLE')

    events = append
    check = append
    prune = append


class FileDeletionJournal:
    """절대 경로·현재 uid 소유 0700 폴더, O_NOFOLLOW/0600·fsync·불변 파일.

    저장 위치는 서버 설정이며 HTTP 입력으로 선택하지 않는다. 운영 RDS 백업과
    독립된 보관·권한·복구가 검증된 운영 어댑터를 대체하지 않는 개발용이다.
    """
    def __init__(self, directory):
        self.directory = Path(directory)

    def _open(self):
        if os.name != 'posix' or not self.directory.is_absolute() or '..' in self.directory.parts:
            raise AppError('SERVICE_UNAVAILABLE')
        current = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.directory.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current); current = child
            info = os.fstat(current)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise AppError('SERVICE_UNAVAILABLE')
            return current
        except BaseException:
            os.close(current)
            raise

    def check(self):
        try:
            descriptor = self._open()
            os.close(descriptor)
        except OSError:
            raise AppError('SERVICE_UNAVAILABLE') from None

    @staticmethod
    def _read(directory, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise ValueError
            if info.st_size > MAX_EVENT_BYTES: raise ValueError
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                return stream.read(MAX_EVENT_BYTES + 1)
        finally:
            os.close(descriptor)

    def append(self, event):
        directory = None; temporary = None
        try:
            event = DeletionEvent.model_validate(event)
            directory = self._open(); name = str(event.id) + '.json'
            raw = event.model_dump_json().encode('utf-8')
            if len(raw) > MAX_EVENT_BYTES: raise ValueError
            try:
                existing = self._read(directory, name)
            except FileNotFoundError:
                temporary = '.' + uuid4().hex + '.pending'
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                # link는 기존 최종 이력을 덮어쓰지 않는다. 동시 재전송도 원문 일치만 허용한다.
                try:
                    os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                except FileExistsError:
                    pass
                os.unlink(temporary, dir_fd=directory); temporary = None
                os.fsync(directory)
                existing = self._read(directory, name)
            if existing != raw: raise ValueError
        except (OSError, ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None
        finally:
            if directory is not None:
                if temporary is not None:
                    try: os.unlink(temporary, dir_fd=directory)
                    except OSError: pass
                os.close(directory)

    def events(self, now, *, limit=1000):
        directory = None
        try:
            if type(limit) is not int or not 1 <= limit <= 1000: raise ValueError
            directory = self._open(); result = []
            # 조회가 무제한 순회·메모리 소비로 확대되지 않게 서버 작업량을 제한한다.
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.startswith('.') and entry.name.endswith('.pending'): continue
                    if not entry.name.endswith('.json') or str(UUID(entry.name[:-5])) + '.json' != entry.name: raise ValueError
                    if len(result) >= limit: raise ValueError
                    event = DeletionEvent.model_validate_json(self._read(directory, entry.name))
                    if str(event.id) + '.json' != entry.name: raise ValueError
                    result.append(event)
            return sorted((event for event in result if event.expires_at > now), key=lambda event: (event.deleted_at, str(event.id)))
        except (OSError, ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None
        finally:
            if directory is not None: os.close(directory)

    def prune(self, now):
        directory = None
        try:
            directory = self._open(); expired = []; scanned = 0
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > 1000: raise ValueError
                    if entry.name.startswith('.') and entry.name.endswith('.pending'): continue
                    event = DeletionEvent.model_validate_json(self._read(directory, entry.name))
                    if str(event.id) + '.json' != entry.name: raise ValueError
                    if event.expires_at <= now: expired.append(entry.name)
            for name in expired: os.unlink(name, dir_fd=directory)
            os.fsync(directory)
            return len(expired)
        except (OSError, ValueError, TypeError):
            raise AppError('SERVICE_UNAVAILABLE') from None
        finally:
            if directory is not None: os.close(directory)


class S3DeletionJournal:
    """운영용: 버전 관리와 Object Lock 기본 보존(30일 이상)을 켠 별도 S3 버킷.

    RDS 자동 백업·스냅샷과 독립이라 DB를 과거 시점으로 복원해도 이력이 함께 되돌아가지 않는다.
    앱 권한은 생성·조회뿐이고 만료 삭제는 버킷 수명주기가 한다. 덮어쓰기는 조건부 쓰기로 막고
    같은 요청의 재전송만 원문 일치로 허용한다. 버킷 소유 계정을 매 호출에 확인한다.
    """
    def __init__(self, client, bucket, owner, prefix='deletion-events/'):
        self.client, self.bucket, self.owner, self.prefix = client, bucket, owner, prefix

    def _call(self, name, **arguments):
        return getattr(self.client, name)(Bucket=self.bucket, ExpectedBucketOwner=self.owner, **arguments)

    def _key(self, event_id):
        return self.prefix + str(event_id) + '.json'

    def _read(self, key):
        response = self._call('get_object', Key=key)
        body = response['Body']
        try:
            if response['ContentLength'] > MAX_EVENT_BYTES: raise ValueError
            raw = body.read(MAX_EVENT_BYTES + 1)
        finally:
            body.close()
        if len(raw) > MAX_EVENT_BYTES: raise ValueError
        return raw

    def check(self):
        try:
            versioning = self._call('get_bucket_versioning')
            lock = self._call('get_object_lock_configuration')['ObjectLockConfiguration']
            retention = lock['Rule']['DefaultRetention']
            days = retention.get('Days', 0) + 365 * retention.get('Years', 0)
            if (versioning.get('Status') != 'Enabled' or lock.get('ObjectLockEnabled') != 'Enabled'
                    or retention.get('Mode') not in {'GOVERNANCE', 'COMPLIANCE'} or days < 30):
                raise ValueError
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def append(self, event):
        try:
            event = DeletionEvent.model_validate(event); key = self._key(event.id)
            raw = event.model_dump_json().encode('utf-8')
            if len(raw) > MAX_EVENT_BYTES: raise ValueError
            try:
                # Object Lock 버킷은 체크섬이 있어야 쓰기를 받는다. 보존 기한은 버킷 기본값을 따른다.
                self._call('put_object', Key=key, Body=raw, ContentType='application/json',
                    IfNoneMatch='*', ChecksumAlgorithm='SHA256')
            except ClientError as error:
                # 이미 있는 이력(412)이나 동시 쓰기(409)는 아래 원문 비교로만 통과시킨다.
                if error.response.get('Error', {}).get('Code') not in {'PreconditionFailed', 'ConditionalRequestConflict'}: raise
            if self._read(key) != raw: raise ValueError
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def events(self, now, *, limit=1000):
        try:
            if type(limit) is not int or not 1 <= limit <= 1000: raise ValueError
            result = []; token = None
            # 수명주기가 아직 지우지 않은 만료 이력까지 세어 조회 작업량을 제한한다.
            while True:
                page = self._call('list_objects_v2', Prefix=self.prefix, MaxKeys=1000,
                    **({'ContinuationToken': token} if token else {}))
                for item in page.get('Contents', []):
                    name = item['Key'][len(self.prefix):]
                    if not name.endswith('.json') or str(UUID(name[:-5])) + '.json' != name: raise ValueError
                    if item['Size'] > MAX_EVENT_BYTES or len(result) >= limit: raise ValueError
                    event = DeletionEvent.model_validate_json(self._read(item['Key']))
                    if self._key(event.id) != item['Key']: raise ValueError
                    result.append(event)
                if not page.get('IsTruncated'): break
                token = page['NextContinuationToken']
            return sorted((event for event in result if event.expires_at > now), key=lambda event: (event.deleted_at, str(event.id)))
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError):
            raise AppError('SERVICE_UNAVAILABLE') from None

    def prune(self, now):
        # 앱 역할에는 삭제 권한이 없다. 30일 만료 정리는 버킷 수명주기 규칙이 맡는다.
        self.check()
        return 0


def build_deletion_journal(settings, client_factory):
    if settings.app_env == 'production' and settings.deletion_journal_bucket is not None:
        return S3DeletionJournal(client_factory('s3', settings.deletion_journal_region),
            settings.deletion_journal_bucket, settings.deletion_journal_bucket_owner)
    if settings.app_env == 'development' and settings.deletion_journal_directory is not None:
        return FileDeletionJournal(settings.deletion_journal_directory)
    return UnavailableDeletionJournal()
