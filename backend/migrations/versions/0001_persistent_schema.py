"""최초 15개 영구 테이블. 당시 모델의 독립 스냅샷."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_persistent_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('audit_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_role', sa.String(length=16), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('target_type', sa.String(length=16), nullable=True),
    sa.Column('target_id', sa.Uuid(), nullable=True),
    sa.Column('result', sa.String(length=16), nullable=False),
    sa.Column('request_id', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("action IN ('opportunity.create', 'opportunity.update', 'opportunity.approve', 'opportunity.reject', 'opportunity.hide', 'opportunity.close', 'report.update', 'mfa.verify', 'mfa.fail', 'mfa.lock', 'role.grant', 'role.revoke', 'access.denied')", name=op.f('ck_audit_events_action')),
    sa.CheckConstraint("actor_role IN ('operator', 'user', 'system')", name=op.f('ck_audit_events_actor_role')),
    sa.CheckConstraint("result IN ('success', 'denied', 'failed')", name=op.f('ck_audit_events_result')),
    sa.CheckConstraint("target_type IS NULL OR target_type IN ('opportunity', 'report', 'user')", name=op.f('ck_audit_events_target_type')),
    sa.CheckConstraint('(target_type IS NULL AND target_id IS NULL) OR (target_type IS NOT NULL AND target_id IS NOT NULL)', name=op.f('ck_audit_events_target_pair')),
    sa.CheckConstraint('expires_at > at', name=op.f('ck_audit_events_expiry')),
    sa.CheckConstraint('length(request_id) BETWEEN 14 AND 36', name=op.f('ck_audit_events_request_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_at', 'audit_events', ['at'], unique=False)
    op.create_index('ix_audit_events_expiry', 'audit_events', ['expires_at'], unique=False)
    op.create_table('deletion_records',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("scope IN ('account', 'profile', 'application')", name=op.f('ck_deletion_records_scope')),
    sa.CheckConstraint("status IN ('pending', 'completed', 'failed')", name=op.f('ck_deletion_records_status')),
    sa.CheckConstraint('expires_at > deleted_at', name=op.f('ck_deletion_records_expiry')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deletion_records'))
    )
    op.create_index('ix_deletion_records_expiry', 'deletion_records', ['expires_at'], unique=False)
    op.create_index('ix_deletion_records_target', 'deletion_records', ['scope', 'target_id'], unique=False)
    op.create_table('role_definitions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=False),
    sa.Column('skill_tags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('aliases', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('experience_rules', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.CheckConstraint('length(description) BETWEEN 1 AND 1000', name=op.f('ck_role_definitions_description')),
    sa.CheckConstraint('length(id) BETWEEN 2 AND 64', name=op.f('ck_role_definitions_id_length')),
    sa.CheckConstraint('length(name) BETWEEN 1 AND 100', name=op.f('ck_role_definitions_name')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_role_definitions'))
    )
    op.create_table('sources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('base_url', sa.String(length=2000), nullable=False),
    sa.Column('terms_url', sa.String(length=2000), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("base_url LIKE 'https://%'", name=op.f('ck_sources_https')),
    sa.CheckConstraint('length(code) BETWEEN 1 AND 64', name=op.f('ck_sources_code')),
    sa.CheckConstraint('length(name) BETWEEN 1 AND 200', name=op.f('ck_sources_name')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sources')),
    sa.UniqueConstraint('code', name=op.f('uq_sources_code'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('kakao_subject', sa.String(length=128), nullable=False),
    sa.Column('role', sa.String(length=16), server_default='user', nullable=False),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('user', 'admin')", name=op.f('ck_users_role')),
    sa.CheckConstraint("status IN ('active', 'suspended')", name=op.f('ck_users_status')),
    sa.CheckConstraint('length(kakao_subject) BETWEEN 1 AND 128', name=op.f('ck_users_subject_length')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('kakao_subject', name=op.f('uq_users_kakao_subject'))
    )
    op.create_table('consents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('notice_version', sa.String(length=32), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("purpose IN ('ai_processing', 'storage')", name=op.f('ck_consents_purpose')),
    sa.CheckConstraint('length(notice_version) BETWEEN 1 AND 32', name=op.f('ck_consents_notice_version')),
    sa.CheckConstraint('withdrawn_at IS NULL OR withdrawn_at >= accepted_at', name=op.f('ck_consents_withdrawal_order')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_consents_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consents'))
    )
    op.create_index('ix_consents_owner_purpose', 'consents', ['owner_id', 'purpose', 'accepted_at'], unique=False)
    op.create_table('ingestion_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_code', sa.String(length=32), nullable=True),
    sa.Column('fetched_count', sa.Integer(), nullable=False),
    sa.Column('created_count', sa.Integer(), nullable=False),
    sa.Column('changed_count', sa.Integer(), nullable=False),
    sa.Column('rejected_count', sa.Integer(), nullable=False),
    sa.CheckConstraint("(status = 'running' AND finished_at IS NULL) OR (status <> 'running' AND finished_at IS NOT NULL AND finished_at >= started_at)", name=op.f('ck_ingestion_runs_completion')),
    sa.CheckConstraint("failure_code IS NULL OR failure_code IN ('network', 'parse', 'response_limit', 'source_unavailable', 'cancelled', 'invalid_payload')", name=op.f('ck_ingestion_runs_failure_code')),
    sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name=op.f('ck_ingestion_runs_status')),
    sa.CheckConstraint('fetched_count >= 0 AND created_count >= 0 AND changed_count >= 0 AND rejected_count >= 0', name=op.f('ck_ingestion_runs_counts')),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name=op.f('fk_ingestion_runs_source_id_sources'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingestion_runs'))
    )
    op.create_index('ix_ingestion_runs_source_started', 'ingestion_runs', ['source_id', 'started_at'], unique=False)
    op.create_table('opportunity_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=False),
    sa.Column('external_id', sa.String(length=200), nullable=True),
    sa.CheckConstraint('external_id IS NULL OR length(external_id) BETWEEN 1 AND 200', name=op.f('ck_opportunity_documents_external_id')),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], name=op.f('fk_opportunity_documents_source_id_sources'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_opportunity_documents')),
    sa.UniqueConstraint('source_id', 'external_id', name=op.f('uq_opportunity_documents_source_id'))
    )
    op.create_table('profile_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_profile_documents_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_documents')),
    sa.UniqueConstraint('owner_id', 'id', name=op.f('uq_profile_documents_owner_id')),
    sa.UniqueConstraint('owner_id', name=op.f('uq_profile_documents_owner_id'))
    )
    op.create_table('application_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id', 'profile_id'], ['profile_documents.owner_id', 'profile_documents.id'], name=op.f('fk_application_documents_owner_id_profile_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_application_documents')),
    sa.UniqueConstraint('owner_id', 'id', 'profile_id', name=op.f('uq_application_documents_owner_id'))
    )
    op.create_index('ix_application_documents_profile', 'application_documents', ['owner_id', 'profile_id'], unique=False)
    op.create_table('opportunity_versions',
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('organization_name', sa.String(length=200), nullable=False),
    sa.Column('activity_type', sa.String(length=16), nullable=False),
    sa.Column('is_public_job', sa.Boolean(), nullable=True),
    sa.Column('role_tags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('skill_tags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('activity_province', sa.String(length=16), nullable=True),
    sa.Column('activity_district', sa.String(length=64), nullable=True),
    sa.Column('location_text', sa.String(length=500), nullable=True),
    sa.Column('remote_allowed', sa.Boolean(), nullable=True),
    sa.Column('schedule_text', sa.String(length=500), nullable=True),
    sa.Column('hours_per_week', sa.Float(), nullable=True),
    sa.Column('paid', sa.Boolean(), nullable=True),
    sa.Column('compensation_text', sa.String(length=500), nullable=True),
    sa.Column('description_text', sa.String(length=5000), nullable=True),
    sa.Column('description_truncated', sa.Boolean(), nullable=False),
    sa.Column('requirements', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('required_documents', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('application_method', sa.String(length=16), nullable=False),
    sa.Column('application_instructions', sa.String(length=2000), nullable=False),
    sa.Column('source_url', sa.String(length=2000), nullable=False),
    sa.Column('application_url', sa.String(length=2000), nullable=False),
    sa.Column('deadline_date', sa.Date(), nullable=True),
    sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('recruitment_status', sa.String(length=16), nullable=False),
    sa.Column('review_status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('source_checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.CheckConstraint("activity_province IS NULL OR activity_province IN ('seoul', 'gyeonggi', 'incheon')", name=op.f('ck_opportunity_versions_province')),
    sa.CheckConstraint("activity_type IN ('employment', 'volunteering')", name=op.f('ck_opportunity_versions_activity_type')),
    sa.CheckConstraint("application_method IN ('online', 'phone', 'visit', 'email', 'mixed')", name=op.f('ck_opportunity_versions_application_method')),
    sa.CheckConstraint("recruitment_status IN ('open', 'closed', 'unknown')", name=op.f('ck_opportunity_versions_recruitment_status')),
    sa.CheckConstraint("review_status <> 'approved' OR reviewed_at IS NOT NULL", name=op.f('ck_opportunity_versions_approved_review_time')),
    sa.CheckConstraint("review_status IN ('pending', 'approved', 'rejected', 'hidden')", name=op.f('ck_opportunity_versions_review_status')),
    sa.CheckConstraint('activity_district IS NULL OR activity_province IS NOT NULL', name=op.f('ck_opportunity_versions_district_province')),
    sa.CheckConstraint('description_text IS NULL OR length(description_text) BETWEEN 1 AND 5000', name=op.f('ck_opportunity_versions_description_length')),
    sa.CheckConstraint('hours_per_week IS NULL OR (hours_per_week >= 0 AND hours_per_week <= 168)', name=op.f('ck_opportunity_versions_hours')),
    sa.CheckConstraint('length(content_hash) = 64', name=op.f('ck_opportunity_versions_content_hash')),
    sa.CheckConstraint('length(title) BETWEEN 1 AND 200 AND length(organization_name) BETWEEN 1 AND 200', name=op.f('ck_opportunity_versions_title_organization')),
    sa.CheckConstraint('version > 0', name=op.f('ck_opportunity_versions_version')),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunity_documents.id'], name=op.f('fk_opportunity_versions_opportunity_id_opportunity_documents'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('opportunity_id', 'version', name=op.f('pk_opportunity_versions')),
    sa.UniqueConstraint('opportunity_id', 'version', 'review_status', name=op.f('uq_opportunity_versions_opportunity_id'))
    )
    op.create_index('ix_opportunity_versions_freshness', 'opportunity_versions', ['source_checked_at'], unique=False)
    op.create_index('ix_opportunity_versions_public_search', 'opportunity_versions', ['review_status', 'recruitment_status', 'activity_type', 'activity_province'], unique=False)
    op.create_table('profile_versions',
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('nonce', sa.LargeBinary(), nullable=False),
    sa.Column('key_id', sa.String(length=128), nullable=False),
    sa.Column('algorithm', sa.String(length=16), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.CheckConstraint("algorithm = 'AES-256-GCM'", name=op.f('ck_profile_versions_algorithm')),
    sa.CheckConstraint('length(ciphertext) BETWEEN 17 AND 262144', name=op.f('ck_profile_versions_ciphertext_length')),
    sa.CheckConstraint('length(key_id) BETWEEN 1 AND 128', name=op.f('ck_profile_versions_key_reference')),
    sa.CheckConstraint('length(nonce) = 12', name=op.f('ck_profile_versions_nonce_length')),
    sa.CheckConstraint('saved_at >= confirmed_at', name=op.f('ck_profile_versions_confirmation_order')),
    sa.CheckConstraint('schema_version > 0', name=op.f('ck_profile_versions_schema_version')),
    sa.CheckConstraint('version > 0', name=op.f('ck_profile_versions_version')),
    sa.ForeignKeyConstraint(['owner_id', 'profile_id'], ['profile_documents.owner_id', 'profile_documents.id'], name=op.f('fk_profile_versions_owner_id_profile_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('profile_id', 'version', name=op.f('pk_profile_versions')),
    sa.UniqueConstraint('key_id', 'nonce', name=op.f('uq_profile_versions_key_id')),
    sa.UniqueConstraint('owner_id', 'profile_id', 'version', name=op.f('uq_profile_versions_owner_id'))
    )
    op.create_table('application_drafts',
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_version', sa.Integer(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('nonce', sa.LargeBinary(), nullable=False),
    sa.Column('key_id', sa.String(length=128), nullable=False),
    sa.Column('algorithm', sa.String(length=16), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.CheckConstraint("algorithm = 'AES-256-GCM'", name=op.f('ck_application_drafts_algorithm')),
    sa.CheckConstraint('length(ciphertext) BETWEEN 17 AND 262144', name=op.f('ck_application_drafts_ciphertext_length')),
    sa.CheckConstraint('length(key_id) BETWEEN 1 AND 128', name=op.f('ck_application_drafts_key_reference')),
    sa.CheckConstraint('length(nonce) = 12', name=op.f('ck_application_drafts_nonce_length')),
    sa.CheckConstraint('saved_at >= approved_at', name=op.f('ck_application_drafts_approval_order')),
    sa.CheckConstraint('schema_version > 0', name=op.f('ck_application_drafts_schema_version')),
    sa.CheckConstraint('version > 0 AND profile_version > 0 AND opportunity_version > 0', name=op.f('ck_application_drafts_versions')),
    sa.ForeignKeyConstraint(['opportunity_id', 'opportunity_version'], ['opportunity_versions.opportunity_id', 'opportunity_versions.version'], name=op.f('fk_application_drafts_opportunity_id_opportunity_versions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id', 'document_id', 'profile_id'], ['application_documents.owner_id', 'application_documents.id', 'application_documents.profile_id'], name=op.f('fk_application_drafts_owner_id_application_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id', 'profile_id', 'profile_version'], ['profile_versions.owner_id', 'profile_versions.profile_id', 'profile_versions.version'], name=op.f('fk_application_drafts_owner_id_profile_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('document_id', 'version', name=op.f('pk_application_drafts')),
    sa.UniqueConstraint('key_id', 'nonce', name=op.f('uq_application_drafts_key_id'))
    )
    op.create_index('ix_application_drafts_profile', 'application_drafts', ['owner_id', 'profile_id', 'profile_version'], unique=False)
    op.create_table('opportunity_publications',
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('review_status', sa.String(length=16), server_default='approved', nullable=False),
    sa.CheckConstraint("review_status = 'approved'", name=op.f('ck_opportunity_publications_approved_only')),
    sa.ForeignKeyConstraint(['opportunity_id', 'version', 'review_status'], ['opportunity_versions.opportunity_id', 'opportunity_versions.version', 'opportunity_versions.review_status'], name=op.f('fk_opportunity_publications_opportunity_id_opportunity_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('opportunity_id', name=op.f('pk_opportunity_publications'))
    )
    op.create_table('reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_version', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('details_ciphertext', sa.LargeBinary(), nullable=True),
    sa.Column('details_nonce', sa.LargeBinary(), nullable=True),
    sa.Column('details_key_id', sa.String(length=128), nullable=True),
    sa.CheckConstraint("status IN ('received', 'in_progress', 'resolved', 'dismissed')", name=op.f('ck_reports_status')),
    sa.CheckConstraint("type <> 'other' OR details_ciphertext IS NOT NULL", name=op.f('ck_reports_other_details')),
    sa.CheckConstraint("type IN ('already_closed', 'wrong_requirements', 'wrong_schedule_or_location', 'wrong_application_method', 'broken_link', 'other')", name=op.f('ck_reports_type')),
    sa.CheckConstraint('(details_ciphertext IS NULL AND details_nonce IS NULL AND details_key_id IS NULL) OR (details_ciphertext IS NOT NULL AND details_nonce IS NOT NULL AND details_key_id IS NOT NULL AND length(details_ciphertext) BETWEEN 17 AND 16384 AND length(details_nonce) = 12 AND length(details_key_id) BETWEEN 1 AND 128)', name=op.f('ck_reports_details_envelope')),
    sa.CheckConstraint('version > 0', name=op.f('ck_reports_version')),
    sa.ForeignKeyConstraint(['opportunity_id', 'opportunity_version'], ['opportunity_versions.opportunity_id', 'opportunity_versions.version'], name=op.f('fk_reports_opportunity_id_opportunity_versions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reports'))
    )
    op.create_index('ix_reports_status_received', 'reports', ['status', 'received_at'], unique=False)

def downgrade():
    op.drop_index('ix_reports_status_received', table_name='reports')
    op.drop_table('reports')
    op.drop_table('opportunity_publications')
    op.drop_index('ix_application_drafts_profile', table_name='application_drafts')
    op.drop_table('application_drafts')
    op.drop_table('profile_versions')
    op.drop_index('ix_opportunity_versions_public_search', table_name='opportunity_versions')
    op.drop_index('ix_opportunity_versions_freshness', table_name='opportunity_versions')
    op.drop_table('opportunity_versions')
    op.drop_index('ix_application_documents_profile', table_name='application_documents')
    op.drop_table('application_documents')
    op.drop_table('profile_documents')
    op.drop_table('opportunity_documents')
    op.drop_index('ix_ingestion_runs_source_started', table_name='ingestion_runs')
    op.drop_table('ingestion_runs')
    op.drop_index('ix_consents_owner_purpose', table_name='consents')
    op.drop_table('consents')
    op.drop_table('users')
    op.drop_table('sources')
    op.drop_table('role_definitions')
    op.drop_index('ix_deletion_records_target', table_name='deletion_records')
    op.drop_index('ix_deletion_records_expiry', table_name='deletion_records')
    op.drop_table('deletion_records')
    op.drop_index('ix_audit_events_expiry', table_name='audit_events')
    op.drop_index('ix_audit_events_at', table_name='audit_events')
    op.drop_table('audit_events')
