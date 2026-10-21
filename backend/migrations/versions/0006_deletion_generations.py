"""회원 세션 세대와 본문 없는 삭제 재시도 명령."""

from alembic import op
import sqlalchemy as sa

revision = '0006_deletion_generations'
down_revision = '0005_application_receipts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_deletion_records_owner_status', 'deletion_records', ['owner_id', 'status'])
    op.add_column('users', sa.Column('session_generation', sa.Integer(),
        sa.CheckConstraint('session_generation >= 0 AND session_generation < 2147483647', name=op.f('ck_users_session_generation')),
        nullable=False, server_default='0'))
    op.add_column('deletion_records', sa.Column('action', sa.String(24),
        sa.CheckConstraint("action IN ('legacy', 'profile_delete', 'application_delete', 'storage_withdraw', 'ai_withdraw', 'account_delete')", name=op.f('ck_deletion_records_action')),
        nullable=False, server_default='legacy'))
    op.add_column('deletion_records', sa.Column('generation', sa.Integer(),
        sa.CheckConstraint('generation >= 0 AND generation < 2147483647', name=op.f('ck_deletion_records_generation')),
        nullable=False, server_default='0'))


def downgrade():
    op.drop_index('ix_deletion_records_owner_status', table_name='deletion_records')
    op.drop_column('deletion_records', 'generation')
    op.drop_column('deletion_records', 'action')
    op.drop_column('users', 'session_generation')
