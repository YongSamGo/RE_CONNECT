"""재검토 표시는 원래 본문·승인·근거 버전을 바꾸지 않는 조회 투영이다."""

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, insert, select, update

from app.contracts.drafts import DraftUpdate
from app.contracts.time import utc_now
from app.core.business_errors import AppError
from app.core.config import Settings
from app.main import create_app
from app.persistence.operations import OpportunityPublication, OpportunityVersion
from tests.persistence_helpers import open_test_database
from tests.test_admission import with_redis
from tests.test_journey_drafts import OPPORTUNITY, body, setup
from tests.test_profile_confirmation import ready_edit


@pytest.mark.parametrize('database', ['sqlite', 'postgresql'])
def test_http_review_projection_preserves_old_approved_body_and_never_refreshes_ttl(database):
    async def scenario(admission, admission_store, redis):
        with open_test_database(database) as db:
            issued, sessions, journeys, journey, identity, runtime, service = await setup(admission, admission_store, redis, db)
            original = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            edited = await service.update(issued.session, journey.journey_id, original.draft_id,
                DraftUpdate(self_introduction='사용자가 직접 쓴 본문', motivation='직접 쓴 동기', base_revision=1))
            approved = await service.approve(issued.session, journey.journey_id, original.draft_id, edited.revision)
            resource = journeys.store.resource_key(identity.subject_id, journey.journey_id)
            raw = await redis.hget(resource + ':lifecycle', f'draft:{original.draft_id}')
            await journeys.update_profile(issued.session, journey.journey_id, ready_edit(revision=3, description='바뀐 확정 경험'))
            during_edit = await service.get(issued.session, journey.journey_id, original.draft_id)
            assert during_edit.review_reasons == [] and any('수정 중' in warning for warning in during_edit.warnings)
            await journeys.confirm_profile(issued.session, journey.journey_id, 4)
            app = create_app(Settings(_env_file=None, app_env='test', public_origin='https://testserver'))
            app.state.session_service, app.state.admission_service, app.state.draft_service = sessions, admission, service
            ttl = await redis.pttl(resource)
            last = await redis.hget(resource + ':lifecycle', 'last_ms')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://testserver') as client:
                client.cookies.set('__Host-rc_session', issued.token)
                path = f'/api/v1/journeys/{journey.journey_id}/drafts/{original.draft_id}'
                response = await client.get(path)
                assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
                result = response.json()
                assert result['review_reasons'] == ['profile_changed']
                assert result['profile_version'] == 1 and result['revision'] == approved.revision
                assert result['opportunity'] == approved.opportunity.model_dump(mode='json')
                assert result['self_introduction'] == approved.self_introduction and result['motivation'] == approved.motivation
                assert result['approved_at'] == approved.model_dump(mode='json')['approved_at']
                other = await sessions.issue()
                client.cookies.set('__Host-rc_session', other.token)
                assert (await client.get(path)).status_code == 404
            assert await redis.hget(resource + ':lifecycle', f'draft:{original.draft_id}') == raw
            assert await redis.hget(resource + ':lifecycle', 'last_ms') == last and 0 < await redis.pttl(resource) <= ttl
            assert runtime.calls == 0
            with pytest.raises(AppError, match='VERSION_CONFLICT'):
                await service.approve(issued.session, journey.journey_id, original.draft_id, approved.revision)
    with_redis(scenario)


@pytest.mark.parametrize('change,expected', [('new_version', ['opportunity_changed']), ('pending_material', ['opportunity_changed']),
    ('pending_title', []), ('closed', ['opportunity_closed']), ('unpublish', ['opportunity_closed']), ('stale', []), ('unknown', [])])
def test_current_opportunity_review_reasons_do_not_rewrite_the_original_reference(change, expected):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            original = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            if change.startswith('pending') or change == 'new_version':
                row = dict(db.execute(select(OpportunityVersion.__table__).where(OpportunityVersion.opportunity_id == OPPORTUNITY)).mappings().one())
                row['version'] = 2
                if change.startswith('pending'):
                    row.update(review_status='pending', reviewed_at=None)
                    row['application_instructions' if change == 'pending_material' else 'title'] = '새로운 가상 안내'
                db.execute(insert(OpportunityVersion), row)
                if change == 'new_version':
                    db.execute(update(OpportunityPublication).where(OpportunityPublication.opportunity_id == OPPORTUNITY).values(version=2))
            elif change == 'unpublish':
                db.execute(delete(OpportunityPublication).where(OpportunityPublication.opportunity_id == OPPORTUNITY))
            else:
                db.execute(update(OpportunityVersion).where(OpportunityVersion.opportunity_id == OPPORTUNITY).values(**(
                    {'source_checked_at': utc_now() - timedelta(hours=49)} if change == 'stale' else {'recruitment_status': change})))
            displayed = await service.get(issued.session, journey.journey_id, original.draft_id)
            assert displayed.review_reasons == expected
            assert displayed.opportunity == original.opportunity and displayed.profile_version == original.profile_version
            assert displayed.self_introduction == original.self_introduction and displayed.approved_at == original.approved_at
            assert await service.store.read(issued.session, journey.journey_id, original.draft_id) == original
            if change in {'stale', 'unknown'}:
                assert any('모집 상태' in warning for warning in displayed.warnings)
            edited = await service.update(issued.session, journey.journey_id, original.draft_id,
                DraftUpdate(self_introduction='사용자가 보존한 편집', motivation='', base_revision=1))
            assert edited.review_reasons == expected and edited.approved_at is None
    with_redis(scenario)


def test_all_changed_dependencies_are_reported_without_changing_a_previous_approval():
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            approved = await service.approve(issued.session, journey.journey_id, draft.draft_id, 1)
            await journeys.confirm_profile(issued.session, journey.journey_id, 3)
            db.execute(delete(OpportunityPublication).where(OpportunityPublication.opportunity_id == OPPORTUNITY))
            result = await service.get(issued.session, journey.journey_id, draft.draft_id)
            assert result.review_reasons == ['profile_changed', 'opportunity_closed']
            assert result.approved_at == approved.approved_at
            assert await service.store.read(issued.session, journey.journey_id, draft.draft_id) == approved
    with_redis(scenario)


@pytest.mark.parametrize('change', ['edit', 'delete', 'reconfirm'])
def test_final_read_rejects_body_changes_during_public_dependency_lookup(change, monkeypatch):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, journeys, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            original = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            display = service._display
            async def change_after_lookup(*args):
                result = await display(*args)
                if change == 'delete':
                    await journeys.end(issued.session, journey.journey_id)
                elif change == 'edit':
                    await service.store.mutate(issued.session, journey.journey_id, original,
                        original.model_copy(update={'revision': 2, 'self_introduction': '새 편집'}))
                else:
                    await journeys.confirm_profile(issued.session, journey.journey_id, 3)
                return result
            monkeypatch.setattr(service, '_display', change_after_lookup)
            with pytest.raises(AppError, match='NOT_FOUND' if change == 'delete' else 'VERSION_CONFLICT'):
                await service.get(issued.session, journey.journey_id, original.draft_id)
    with_redis(scenario)


def test_database_lookup_failure_preserves_both_approved_body_and_uncommitted_edit(monkeypatch):
    async def scenario(admission, admission_store, redis):
        with open_test_database('sqlite') as db:
            issued, _, _, journey, identity, _, service = await setup(admission, admission_store, redis, db)
            draft = await service.create(issued.session, identity, journey.journey_id, str(uuid4()), body())
            approved = await service.approve(issued.session, journey.journey_id, draft.draft_id, 1)
            def unavailable(*args):
                raise AppError('SERVICE_UNAVAILABLE')
            monkeypatch.setattr(service.opportunities, 'get', unavailable)
            with pytest.raises(AppError, match='SERVICE_UNAVAILABLE'):
                await service.update(issued.session, journey.journey_id, draft.draft_id,
                    DraftUpdate(self_introduction='아직 서버에 반영하지 않은 편집', motivation='', base_revision=2))
            assert await service.store.read(issued.session, journey.journey_id, draft.draft_id) == approved
    with_redis(scenario)
