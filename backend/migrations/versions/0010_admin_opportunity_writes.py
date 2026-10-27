"""운영자 공고 등록·수정 (W07-02 · #53): 버전 생성 시각과 등록 재전송 기록."""

from alembic import op
import sqlalchemy as sa

revision = "0010_admin_opportunity_writes"
down_revision = "0009_role_catalog_draft"
branch_labels = None
depends_on = None


# 0002의 SQLite 공고 내용 보호 칸 목록에 생성 시각을 더한다. 식별자는 고정 목록이다.
_CONTENT_COLUMNS = (
    "opportunity_id", "version", "title", "organization_name", "activity_type", "is_public_job",
    "role_tags", "skill_tags", "activity_province", "activity_district", "location_text", "remote_allowed",
    "schedule_text", "hours_per_week", "paid", "compensation_text", "description_text", "description_truncated",
    "requirements", "required_documents", "application_method", "application_instructions", "source_url",
    "application_url", "deadline_date", "deadline_at", "content_hash",
)


def _sqlite_content_trigger(columns):
    predicate = " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in columns)
    predicate += " OR (NEW.recruitment_status IS NOT OLD.recruitment_status AND NEW.recruitment_status <> 'closed')"
    op.execute(f"CREATE TRIGGER immutable_opportunity_content BEFORE UPDATE ON opportunity_versions WHEN {predicate} BEGIN SELECT RAISE(ABORT, 'Opportunity content requires a new version'); END")


def upgrade():
    dialect = op.get_bind().dialect.name
    # 기존 버전의 생성 시각은 남아 있지 않다. 그 버전을 만든 관측 시각으로 채운다.
    # 내용 보호 트리거가 새 칸 채우기도 막으므로 이 한 번만 잠시 끈다.
    if dialect == "postgresql":
        op.add_column("opportunity_versions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        op.execute("ALTER TABLE opportunity_versions DISABLE TRIGGER immutable_opportunity_content")
        op.execute("UPDATE opportunity_versions SET created_at = source_checked_at WHERE created_at IS NULL")
        op.execute("ALTER TABLE opportunity_versions ENABLE TRIGGER immutable_opportunity_content")
        op.alter_column("opportunity_versions", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    else:
        # 다른 표가 이 표를 외래키로 참조해 SQLite 표 재생성(batch)을 쓸 수 없다. NOT NULL 칸은 상수 기본값으로만
        # 더할 수 있으므로 임시값으로 추가한 뒤 곧바로 실제 관측 시각으로 바꾼다. 앱은 생성 시각을 항상 직접 넣는다.
        op.execute("DROP TRIGGER immutable_opportunity_content")
        op.execute("ALTER TABLE opportunity_versions ADD COLUMN created_at DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00.000000'")
        op.execute("UPDATE opportunity_versions SET created_at = source_checked_at")
        _sqlite_content_trigger(_CONTENT_COLUMNS + ("created_at",))

    op.create_table("opportunity_write_receipts",
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(input_hash) = 64", name=op.f("ck_opportunity_write_receipts_input_hash")),
        sa.CheckConstraint("version > 0", name=op.f("ck_opportunity_write_receipts_version")),
        sa.CheckConstraint("expires_at > recorded_at", name=op.f("ck_opportunity_write_receipts_expiry")),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_opportunity_write_receipts_operator_id_users")),
        sa.ForeignKeyConstraint(["opportunity_id", "version"], ["opportunity_versions.opportunity_id", "opportunity_versions.version"],
                                ondelete="CASCADE", name=op.f("fk_opportunity_write_receipts_opportunity_id_opportunity_versions")),
        sa.PrimaryKeyConstraint("operator_id", "key_id", name=op.f("pk_opportunity_write_receipts")))
    op.create_index("ix_opportunity_receipts_operator_expiry", "opportunity_write_receipts", ["operator_id", "expires_at"])
    if dialect == "postgresql":
        op.execute("CREATE TRIGGER immutable_opportunity_receipt BEFORE UPDATE ON opportunity_write_receipts FOR EACH ROW EXECUTE FUNCTION reject_saved_version_update()")
    else:
        op.execute("CREATE TRIGGER immutable_opportunity_receipt BEFORE UPDATE ON opportunity_write_receipts BEGIN SELECT RAISE(ABORT, 'Saved receipt is immutable'); END")


def downgrade():
    op.drop_table("opportunity_write_receipts")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_column("opportunity_versions", "created_at")
    else:
        op.execute("DROP TRIGGER immutable_opportunity_content")
        op.execute("ALTER TABLE opportunity_versions DROP COLUMN created_at")
        _sqlite_content_trigger(_CONTENT_COLUMNS)
