"""수동 공고 버전의 공식 근거 기록."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_manual_evidence"
down_revision = "0003_ingestion_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("manual_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evidence_url", sa.String(2000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quotes", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id", "version"], ["opportunity_versions.opportunity_id", "opportunity_versions.version"], ondelete="CASCADE"),
        sa.UniqueConstraint("opportunity_id", "version", "evidence_hash"),
        sa.CheckConstraint("length(evidence_hash) = 64", name="hash"),
        sa.CheckConstraint("observed_at <= recorded_at", name="chronology"),
        sa.CheckConstraint("evidence_url LIKE 'https://%'", name="https"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION prevent_manual_evidence_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'immutable evidence' USING ERRCODE = '23514'; END; $$""")
        op.execute("CREATE TRIGGER immutable_manual_evidence BEFORE UPDATE ON manual_evidence FOR EACH ROW EXECUTE FUNCTION prevent_manual_evidence_update()")
    else:
        op.execute("CREATE TRIGGER immutable_manual_evidence BEFORE UPDATE ON manual_evidence BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END")


def downgrade():
    op.drop_table("manual_evidence")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION prevent_manual_evidence_update()")
