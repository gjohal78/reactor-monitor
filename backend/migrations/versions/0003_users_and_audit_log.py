"""Create users and append-only audit_log tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('viewer', 'operator', 'supervisor')", name="ck_users_role"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target", sa.String(64), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("old_value", JSON, nullable=True),
        sa.Column("new_value", JSON, nullable=True),
        sa.Column("detail", sa.String(200), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    # Make audit_log append-only at the database level.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION audit_log_reject_change() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only';
            END
            $$
            """
        )
        op.execute(
            "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION audit_log_reject_change()"
        )
        op.execute(
            "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_change()"
        )
    else:  # SQLite
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER audit_log_no_{operation.lower()} BEFORE {operation} "
                "ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
            )


def downgrade() -> None:
    op.drop_table("audit_log")  # drops its triggers too
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS audit_log_reject_change()")
    op.drop_table("users")
