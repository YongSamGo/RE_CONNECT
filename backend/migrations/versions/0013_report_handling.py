"""공고 오류 신고 처리 (W07-05 · #56): 처리 사유 암호화 봉투·처리 시각·보관 정리 표시."""

from alembic import op
import sqlalchemy as sa


revision = "0013_report_handling"
# 정한 머지 순서는 #267 → #270 → #266 → #269다. 앞 PR이 머지되면 바로 앞 리비전으로 다시 잇는다.
down_revision = "0010_operator_mfa"
branch_labels = None
depends_on = None

_TERMINAL = "status IN ('resolved', 'dismissed')"


def _envelope(prefix):
    c, n, k = f"{prefix}_ciphertext", f"{prefix}_nonce", f"{prefix}_key_id"
    return (f"({c} IS NULL AND {n} IS NULL AND {k} IS NULL) OR ({c} IS NOT NULL AND {n} IS NOT NULL AND {k} IS NOT NULL"
            f" AND length({c}) BETWEEN 17 AND 16384 AND length({n}) = 12 AND length({k}) BETWEEN 1 AND 128)")


def upgrade():
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("resolution_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("resolution_nonce", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("resolution_key_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    # 기존 신고는 처리 이력이 없으므로 접수 시각을 마지막 변경 시각으로 둔다.
    op.execute(sa.text("UPDATE reports SET updated_at = received_at"))
    with op.batch_alter_table("reports") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.drop_constraint(op.f("ck_reports_other_details"), type_="check")
        batch.create_check_constraint("other_details", "type <> 'other' OR details_ciphertext IS NOT NULL OR purged_at IS NOT NULL")
        batch.create_check_constraint("resolution_envelope", _envelope("resolution"))
        batch.create_check_constraint("resolution_required", f"NOT ({_TERMINAL}) OR resolution_ciphertext IS NOT NULL OR purged_at IS NOT NULL")
        batch.create_check_constraint("received_unhandled", "status <> 'received' OR resolution_ciphertext IS NULL")
        batch.create_check_constraint("purged_terminal", f"purged_at IS NULL OR ({_TERMINAL} AND details_ciphertext IS NULL AND resolution_ciphertext IS NULL)")
        batch.create_check_constraint("updated_order", "updated_at >= received_at")
    op.create_index("ix_reports_status_updated", "reports", ["status", "updated_at"])


def downgrade():
    op.drop_index("ix_reports_status_updated", table_name="reports")
    # 이전 스키마는 '그 밖의 오류'에 설명을 요구한다. 보관 기간이 지나 설명을 지운 신고는 되살릴 수 없어 지운다.
    op.execute(sa.text("DELETE FROM reports WHERE purged_at IS NOT NULL AND type = 'other'"))
    with op.batch_alter_table("reports") as batch:
        for name in ("updated_order", "purged_terminal", "received_unhandled", "resolution_required", "resolution_envelope", "other_details"):
            batch.drop_constraint(op.f(f"ck_reports_{name}"), type_="check")
        batch.create_check_constraint("other_details", "type <> 'other' OR details_ciphertext IS NOT NULL")
        batch.drop_column("purged_at")
        batch.drop_column("resolution_key_id")
        batch.drop_column("resolution_nonce")
        batch.drop_column("resolution_ciphertext")
        batch.drop_column("updated_at")
