"""Create alarms table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alarms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("limit", sa.Float(), nullable=False),
        sa.Column("deadband", sa.Float(), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=False),
        sa.Column("activation_count", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alarms_code", "alarms", ["code"])
    # Startup restores open alarms with "WHERE state != 'NORMAL'".
    op.create_index("ix_alarms_state", "alarms", ["state"])
    op.create_index("ix_alarms_activated_at", "alarms", ["activated_at"])


def downgrade() -> None:
    op.drop_index("ix_alarms_activated_at", table_name="alarms")
    op.drop_index("ix_alarms_state", table_name="alarms")
    op.drop_index("ix_alarms_code", table_name="alarms")
    op.drop_table("alarms")
