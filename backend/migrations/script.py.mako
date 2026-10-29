"""${message}"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}
# 이 마이그레이션을 적용한 DB에서 바로 앞 릴리스의 앱이 그대로 동작하면 True (추가만 하는 변경).
# 리뷰에서 확인한 경우에만 바꾼다. False면 이미지 되돌리기 대신 스냅샷 복원이 필요하다 (docs/operations/rollback.md).
rollback_safe = False


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
