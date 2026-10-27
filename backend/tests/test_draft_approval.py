"""지원서 본문 CAS·명시 승인·수정 시 승인 해제의 실제 저장 경계."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, update

from app.contracts.drafts import DraftUpdate
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.persistence.operations import OpportunityPublication, OpportunityVersion
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_consents import csrf
from tests.test_journey_drafts import OPPORTUNITY, body, setup
from tests.test_journeys import BODY
from tests.test_profile_confirmation import ready_edit


@pytest.mark.parametrize('database', ['sqlite', 'postgresql'])
def test_http_edit_and_explicit_approval_are_distinct_and_old_revisions_conflict(database):
    async def scenario(admission, admission_store, redis):
        with open_test_database(database) as db:
            issued, sessions, journeys, journey, identity, runtime, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
            app.state.session_service, app.state.admission_service, app.state.draft_service = sessions, admission, service
            # 수동 편집/사용자 승인은 추론이나 AI 동의 성공으로 대체하지 않는다.
            await redis.hdel(journeys.store.session_key(issued.session.digest), 'ai_notice_version', 'ai_granted_ms')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
                client.cookies.set('__Host-rc_session', issued.token)
                await client.get('/api/v1/me')
                path = f'/api/v1/journeys/{journey.journey_id}/drafts/{draft.draft_id}'
                edited_body = {'self_introduction': '직접 확인한 경험입니다.', 'motivation': '직접 작성한 지원동기입니다.', 'base_revision': 1}
                assert (await client.patch(path, json=edited_body)).status_code == 403
                edited = await client.patch(path, json=edited_body, headers=csrf(client))
                assert edited.status_code == 200 and edited.headers['cache-control'] == 'no-store'
                assert edited.json()['revision'] == 2 and edited.json()['approved_at'] is None
                approved = await client.post(path + '/approve', json={'base_revision': 2}, headers=csrf(client))
                assert approved.status_code == 200 and approved.json()['approved_at'] is not None and approved.json()['revision'] == 3
                assert approved.json()['self_introduction'] == edited_body['self_introduction']
                assert approved.json()['motivation'] == edited_body['motivation']
                assert (await client.post(path + '/approve', json={'base_revision': 2}, headers=csrf(client))).status_code == 409
                assert (await client.patch(path, json=edited_body, headers=csrf(client))).status_code == 409
                updated = await client.patch(path, json={**edited_body, 'motivation': '', 'base_revision': 3}, headers=csrf(client))
                assert updated.status_code == 200 and updated.json()['approved_at'] is None and updated.json()['revision'] == 4
                assert updated.json()['self_introduction'] == edited_body['self_introduction'] and updated.json()['motivation'] == ''
                for changes in [{'approved_at': '2026-10-18T00:00:00Z'}, {'base_revision': True}, {'owner_id': str(uuid4())}, {'self_introduction': '가' * 2001}]:
                    assert (await client.patch(path, json={**edited_body, **changes, 'base_revision': changes.get('base_revision', 4)}, headers=csrf(client))).status_code == 422
                assert (await client.patch(path.replace(str(draft.draft_id), str(uuid4())), json={**edited_body, 'base_revision': 4}, headers=csrf(client))).status_code == 404
                other = await sessions.issue()
                client.cookies.set('__Host-rc_session', other.token)
                await client.get('/api/v1/me')
                assert (await client.patch(path, json={**edited_body, 'base_revision': 4}, headers=csrf(client))).status_code == 404
                assert (await client.post(path + '/approve', json={'base_revision': 4}, headers=csrf(client))).status_code == 404
            assert runtime.calls == 0
            stored = await service.store.read(issued.session, journey.journey_id, draft.draft_id)
            assert stored.approved_at is None and stored.revision == 4
    with_redis(scenario)


def test_two_actual_concurrent_edits_commit_exactly_one_body(monkeypatch):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, _, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            read = service.store.read
            barrier, reads = asyncio.Event(), 0
            async def simultaneous(*args):
                nonlocal reads
                result = await read(*args)
                reads += 1
                if reads == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 3)
                return result
            monkeypatch.setattr(service.store, 'read', simultaneous)
            results = await asyncio.gather(*(service.update(issued.session, journey.journey_id, draft.draft_id,
                DraftUpdate(self_introduction=value, motivation='', base_revision=1)) for value in ['첫 편집', '다른 편집']), return_exceptions=True)
            assert sum(isinstance(result, AppError) and result.code == 'VERSION_CONFLICT' for result in results) == 1
            success = next(result for result in results if not isinstance(result, BaseException))
            assert success.revision == 2 and success.approved_at is None
            assert await read(issued.session, journey.journey_id, draft.draft_id) == success
    with_redis(scenario)


@pytest.mark.parametrize('change', ['edit', 'reconfirm', 'delete', 'expire', 'revoke'])
def test_approval_rechecks_at_atomic_write_and_does_not_restore_a_deleted_body(change, monkeypatch):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            mutate = service.store.mutate
            resource = journeys.store.resource_key(identity.subject_id, journey.journey_id)
            async def changed_before_commit(*args, **kwargs):
                if change == 'edit':
                    await journeys.update_profile(issued.session, journey.journey_id, ready_edit(revision=3))
                elif change == 'reconfirm':
                    await journeys.confirm_profile(issued.session, journey.journey_id, 3)
                elif change == 'delete':
                    await journeys.end(issued.session, journey.journey_id)
                elif change == 'expire':
                    await redis.hset(resource + ':lifecycle', mapping={'created_ms': 0, 'last_ms': 0})
                else:
                    await redis.delete(journeys.store.session_key(issued.session.digest))
                return await mutate(*args, **kwargs)
            monkeypatch.setattr(service.store, 'mutate', changed_before_commit)
            with pytest.raises(AppError):
                await service.approve(issued.session, journey.journey_id, draft.draft_id, 1)
            raw = await redis.hget(resource + ':lifecycle', f'draft:{draft.draft_id}')
            assert raw is None if change == 'delete' else raw == draft.model_dump_json()
    with_redis(scenario)


@pytest.mark.parametrize('change', ['reconfirm', 'closed', 'unpublish', 'new_version'])
def test_dependency_changes_block_new_approval_without_changing_existing_body(change):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            if change == 'reconfirm':
                await journeys.confirm_profile(issued.session, journey.journey_id, 3)
            elif change == 'closed':
                db.execute(update(OpportunityVersion).where(OpportunityVersion.opportunity_id == OPPORTUNITY).values(recruitment_status='closed'))
            elif change == 'unpublish':
                db.execute(delete(OpportunityPublication).where(OpportunityPublication.opportunity_id == OPPORTUNITY))
            else:
                # 실제 공개본 포인터를 2번 버전으로 옮긴다.
                from sqlalchemy import insert, select
                row = dict(db.execute(select(OpportunityVersion.__table__).where(OpportunityVersion.opportunity_id == OPPORTUNITY)).mappings().one())
                row['version'] = 2
                db.execute(insert(OpportunityVersion), row)
                db.execute(update(OpportunityPublication).where(OpportunityPublication.opportunity_id == OPPORTUNITY).values(version=2))
            with pytest.raises(AppError):
                await service.approve(issued.session, journey.journey_id, draft.draft_id, 1)
            assert await service.store.read(issued.session, journey.journey_id, draft.draft_id) == draft
            # 수정은 허용해 사용자가 직접 적은 내용을 계속 다룰 수 있다. 승인은 유지하지 않는다.
            edited = await service.update(issued.session, journey.journey_id, draft.draft_id,
                DraftUpdate(self_introduction='보존할 직접 작성 내용', motivation='', base_revision=1))
            assert edited.revision == 2 and edited.approved_at is None
    with_redis(scenario)


def test_draft_id_cannot_be_used_in_another_owned_journey():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            other = await journeys.create(issued.session, identity, str(uuid4()), BODY)
            with pytest.raises(AppError, match='NOT_FOUND'):
                await service.update(issued.session, other.journey_id, draft.draft_id, DraftUpdate(self_introduction='타 체험 편집', motivation='', base_revision=1))
    with_redis(scenario)
