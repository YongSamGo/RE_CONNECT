"""출처별 실행 예산·재개 지점과 검수 메타데이터."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_ingestion_state"
down_revision = "0002_immutable_versions"
branch_labels = None
depends_on = None

OLD_CODES = "failure_code IS NULL OR failure_code IN ('network', 'parse', 'response_limit', 'source_unavailable', 'cancelled', 'invalid_payload')"
NEW_CODES = OLD_CODES[:-1] + ", 'budget_exhausted', 'incomplete', 'configuration')"


def upgrade():
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.add_column(sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("rejection_counts", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False, server_default=sa.text("'{}'")))
        batch.drop_constraint(op.f("ck_ingestion_runs_failure_code"), type_="check")
        batch.create_check_constraint(op.f("ck_ingestion_runs_failure_code"), NEW_CODES)
        batch.create_check_constraint(op.f("ck_ingestion_runs_request_count"), "request_count >= 0")
    op.create_table("ingestion_states",
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("next_page", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("request_count >= 0", name="request_count"),
        sa.CheckConstraint("next_page >= 1", name="next_page"))
    op.create_table("ingestion_reviews",
        sa.Column("opportunity_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("review_reasons", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("unmapped_fields", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id", "version"], ["opportunity_versions.opportunity_id", "opportunity_versions.version"], ondelete="CASCADE"))


def downgrade():
    # 새 실패 사유를 이전 계약으로 되돌린다. 본문·성공 시각은 바꾸지 않는다.
    op.execute("UPDATE ingestion_runs SET failure_code = 'source_unavailable' WHERE failure_code IN ('budget_exhausted', 'incomplete', 'configuration')")
    op.drop_table("ingestion_reviews")
    op.drop_table("ingestion_states")
    with op.batch_alter_table("ingestion_runs") as batch:
        batch.drop_constraint(op.f("ck_ingestion_runs_request_count"), type_="check")
        batch.drop_constraint(op.f("ck_ingestion_runs_failure_code"), type_="check")
        batch.create_check_constraint(op.f("ck_ingestion_runs_failure_code"), OLD_CODES)
        batch.drop_column("request_count")
        batch.drop_column("rejection_counts")
