"""수도권 봉사 수집의 지역별 재개 위치 보존."""

from alembic import op
import sqlalchemy as sa


revision = "0008_volunteer_region"
down_revision = "0007_member_ingestion"
branch_labels = None
depends_on = None


def reset_volunteer_page():
    # 전국 목록과 지역 목록의 페이지 번호는 호환되지 않는다. 사용량·공고는 보존한다.
    op.execute(sa.text("UPDATE ingestion_states SET next_page = 1 "
                       "WHERE source_id IN (SELECT id FROM sources WHERE code = 'volunteer')"))


def upgrade():
    with op.batch_alter_table("ingestion_states") as batch:
        batch.add_column(sa.Column("region_index", sa.Integer(), nullable=False, server_default="0"))
        batch.create_check_constraint("region_index", "region_index BETWEEN 0 AND 2")
    reset_volunteer_page()


def downgrade():
    reset_volunteer_page()
    with op.batch_alter_table("ingestion_states") as batch:
        batch.drop_constraint(op.f("ck_ingestion_states_region_index"), type_="check")
        batch.drop_column("region_index")
