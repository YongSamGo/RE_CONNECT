"""운영자 MFA 비밀값·실패 상태와 등록·복구 감사 종류 (W07-01 · #52)."""

from alembic import op
import sqlalchemy as sa

revision = "0010_operator_mfa"
down_revision = "0009_role_catalog_draft"
branch_labels = None
depends_on = None

_BASE_ACTIONS = ("'opportunity.create', 'opportunity.update', 'opportunity.approve', 'opportunity.reject', 'opportunity.hide', "
                 "'opportunity.close', 'report.update', 'mfa.verify', 'mfa.fail', 'mfa.lock'")
_TAIL_ACTIONS = "'role.grant', 'role.revoke', 'access.denied'"


def _replace_action_check(actions):
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_constraint(op.f("ck_audit_events_action"), type_="check")
        batch.create_check_constraint("action", f"action IN ({actions})")


def upgrade():
    op.create_table("operator_mfa_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("last_step", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(128), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("failed_count BETWEEN 0 AND 4", name=op.f("ck_operator_mfa_credentials_failed_count")),
        sa.CheckConstraint("last_step IS NULL OR last_step > 0", name=op.f("ck_operator_mfa_credentials_last_step")),
        sa.CheckConstraint("length(ciphertext) BETWEEN 17 AND 262144", name=op.f("ck_operator_mfa_credentials_ciphertext_length")),
        sa.CheckConstraint("length(nonce) = 12", name=op.f("ck_operator_mfa_credentials_nonce_length")),
        sa.CheckConstraint("length(key_id) BETWEEN 1 AND 128", name=op.f("ck_operator_mfa_credentials_key_reference")),
        sa.CheckConstraint("algorithm = 'AES-256-GCM'", name=op.f("ck_operator_mfa_credentials_algorithm")),
        sa.CheckConstraint("schema_version > 0", name=op.f("ck_operator_mfa_credentials_schema_version")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_operator_mfa_credentials_user_id_users")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_operator_mfa_credentials")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_operator_mfa_credentials_credential_id")),
        sa.UniqueConstraint("key_id", "nonce", name=op.f("uq_operator_mfa_credentials_key_id")))
    _replace_action_check(f"{_BASE_ACTIONS}, 'mfa.enroll', 'mfa.reset', {_TAIL_ACTIONS}")


def downgrade():
    # 이전 제약으로 되돌리기 전에 새 감사 종류를 지운다. 감사 기록은 30일 보관 대상이다.
    op.execute("DELETE FROM audit_events WHERE action IN ('mfa.enroll', 'mfa.reset')")
    _replace_action_check(f"{_BASE_ACTIONS}, {_TAIL_ACTIONS}")
    op.drop_table("operator_mfa_credentials")
