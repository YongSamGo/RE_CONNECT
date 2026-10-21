"""초기 두 역할: OpenAPI의 예시 이름·태그만 사용하고 별칭을 추정하지 않는다."""

from alembic import op
import sqlalchemy as sa

revision = "0003_initial_role_catalog"
down_revision = "0002_immutable_versions"
branch_labels = None
depends_on = None

_ROWS = (
    {"id": "reading_companion", "name": "책 읽어주기 활동가",
     "description": "도서관·복지관에서 아이나 어르신에게 책을 읽어 주는 역할", "skill_tags": ["낭독"], "aliases": [], "experience_rules": []},
    {"id": "library_assistant", "name": "도서관 자료 정리 도우미",
     "description": "도서 정리와 대출 안내를 돕는 역할", "skill_tags": ["자료 정리"], "aliases": [], "experience_rules": []},
)


def upgrade():
    table = sa.table("role_definitions", sa.column("id", sa.String), sa.column("name", sa.String),
                     sa.column("description", sa.String), sa.column("skill_tags", sa.JSON),
                     sa.column("aliases", sa.JSON), sa.column("experience_rules", sa.JSON))
    existing = set(op.get_bind().execute(sa.select(table.c.id).where(table.c.id.in_([r["id"] for r in _ROWS]))).scalars())
    rows = [dict(row) for row in _ROWS if row["id"] not in existing]
    if rows:
        op.bulk_insert(table, rows)


def downgrade():
    """기존 공고 참조와 운영자 수정 자료를 지우지 않는다. 데이터 행은 유지한다."""
