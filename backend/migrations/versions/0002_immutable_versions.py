"""승인 개인 저장본과 공고 콘텐츠의 bulk SQL 덮어쓰기 거절."""

from alembic import op

revision = "0002_immutable_versions"
down_revision = "0001_persistent_schema"
branch_labels = None
depends_on = None

_SAVED_TABLES = ("profile_versions", "application_drafts")
_CONTENT_COLUMNS = (
    "opportunity_id", "version", "title", "organization_name", "activity_type", "is_public_job",
    "role_tags", "skill_tags", "activity_province", "activity_district", "location_text", "remote_allowed",
    "schedule_text", "hours_per_week", "paid", "compensation_text", "description_text", "description_truncated",
    "requirements", "required_documents", "application_method", "application_instructions", "source_url",
    "application_url", "deadline_date", "deadline_at", "content_hash",
)


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""
CREATE FUNCTION reject_saved_version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Saved version is immutable' USING ERRCODE = '23514';
END;
$$
""")
        for table in _SAVED_TABLES:
            # 식별자는 이 마이그레이션의 고정 목록이며 외부 입력을 받지 않는다.
            op.execute(f"CREATE TRIGGER immutable_saved_version BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_saved_version_update()")
        op.execute("""
CREATE FUNCTION reject_opportunity_content_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - ARRAY['review_status','reviewed_at','source_checked_at','recruitment_status'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['review_status','reviewed_at','source_checked_at','recruitment_status'])
       OR (NEW.recruitment_status IS DISTINCT FROM OLD.recruitment_status AND NEW.recruitment_status <> 'closed') THEN
        RAISE EXCEPTION 'Opportunity content requires a new version' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
""")
        op.execute("CREATE TRIGGER immutable_opportunity_content BEFORE UPDATE ON opportunity_versions FOR EACH ROW EXECUTE FUNCTION reject_opportunity_content_update()")
    elif dialect == "sqlite":
        for table in _SAVED_TABLES:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'Saved version is immutable'); END")
        predicate = " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in _CONTENT_COLUMNS)
        predicate += " OR (NEW.recruitment_status IS NOT OLD.recruitment_status AND NEW.recruitment_status <> 'closed')"
        op.execute(f"CREATE TRIGGER immutable_opportunity_content BEFORE UPDATE ON opportunity_versions WHEN {predicate} BEGIN SELECT RAISE(ABORT, 'Opportunity content requires a new version'); END")
    else:
        raise ValueError("지원하지 않는 마이그레이션 DB")


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER immutable_opportunity_content ON opportunity_versions")
        op.execute("DROP FUNCTION reject_opportunity_content_update()")
        for table in _SAVED_TABLES:
            op.execute(f"DROP TRIGGER immutable_saved_version ON {table}")
        op.execute("DROP FUNCTION reject_saved_version_update()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER immutable_opportunity_content")
        for table in _SAVED_TABLES:
            op.execute(f"DROP TRIGGER immutable_{table}")
