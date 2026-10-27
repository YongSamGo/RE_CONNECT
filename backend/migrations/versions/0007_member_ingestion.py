"""회원 저장과 공고 수집 이력 연결"""

from alembic import op
import sqlalchemy as sa


revision = '0007_member_ingestion'
down_revision = ('0006_deletion_generations', '0004_manual_evidence')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
