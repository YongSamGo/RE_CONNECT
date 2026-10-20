"""본문 없는 프로필 저장 응답 멱등 기록."""

from alembic import op
import sqlalchemy as sa

revision = '0004_profile_receipts'
down_revision = '0003_initial_role_catalog'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('profile_write_receipts',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('key_id', sa.Uuid(), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created', sa.Boolean(), nullable=False),
        sa.Column('replaced_version', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('length(input_hash) = 64', name=op.f('ck_profile_write_receipts_input_hash')),
        sa.CheckConstraint('version > 0 AND (replaced_version IS NULL OR replaced_version > 0)', name=op.f('ck_profile_write_receipts_versions')),
        sa.CheckConstraint('expires_at > recorded_at', name=op.f('ck_profile_write_receipts_expiry')),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE', name=op.f('fk_profile_write_receipts_owner_id_users')),
        sa.PrimaryKeyConstraint('owner_id', 'key_id', name=op.f('pk_profile_write_receipts')))
    op.create_index('ix_profile_receipts_owner_expiry', 'profile_write_receipts', ['owner_id', 'expires_at'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE TRIGGER immutable_profile_receipt BEFORE UPDATE ON profile_write_receipts FOR EACH ROW EXECUTE FUNCTION reject_saved_version_update()')
    else:
        op.execute("CREATE TRIGGER immutable_profile_receipt BEFORE UPDATE ON profile_write_receipts BEGIN SELECT RAISE(ABORT, 'Saved receipt is immutable'); END")


def downgrade():
    op.drop_table('profile_write_receipts')
