"""운영자 공고 검수 결정의 근거 기록 (W07-03 · #54).

감사 기록은 최소 메타데이터만 30일 보관하므로 검수 사유·메모는 공고 버전에 딸린 이 테이블에 둔다.
허용 값은 실행 시점의 코드와 무관하게 여기에 고정한다.
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_opportunity_reviews"
down_revision = "0011_admin_opportunity_writes"
branch_labels = None
depends_on = None

_REJECT = "'source_unverifiable', 'out_of_scope', 'recruitment_closed', 'duplicate', 'insufficient_information', 'inappropriate_content', 'other'"
_CLOSE = "'source_closed', 'deadline_passed', 'organization_notice', 'report_confirmed', 'other'"


def upgrade():
    op.create_table("opportunity_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id", "version"], ["opportunity_versions.opportunity_id", "opportunity_versions.version"], ondelete="CASCADE"),
        sa.CheckConstraint("action IN ('approve', 'reject', 'hide', 'close')", name="action"),
        sa.CheckConstraint(
            "(action IN ('approve', 'hide') AND reason_code IS NULL AND note IS NOT NULL)"
            f" OR (action = 'reject' AND reason_code IN ({_REJECT}))"
            f" OR (action = 'close' AND reason_code IN ({_CLOSE}))",
            name="reason"),
        sa.CheckConstraint("reason_code IS NULL OR reason_code <> 'other' OR note IS NOT NULL", name="other_note"),
        sa.CheckConstraint("note IS NULL OR length(note) BETWEEN 1 AND 500", name="note"),
        sa.CheckConstraint("length(request_id) BETWEEN 14 AND 36", name="request_id"))
    op.create_index("ix_opportunity_reviews_target", "opportunity_reviews", ["opportunity_id", "version"])


def downgrade():
    op.drop_index("ix_opportunity_reviews_target", table_name="opportunity_reviews")
    op.drop_table("opportunity_reviews")
