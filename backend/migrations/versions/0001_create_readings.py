"""Create readings table.

Revision ID: 0001
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sim_time_s", sa.Float(), nullable=False),
        sa.Column("power_percent", sa.Float(), nullable=False),
        sa.Column("coolant_temp_c", sa.Float(), nullable=False),
        sa.Column("rod_position_percent", sa.Float(), nullable=False),
        sa.Column("rod_target_percent", sa.Float(), nullable=False),
        sa.Column("reactor_period_s", sa.Float(), nullable=True),
        sa.Column("reactivity_pcm", sa.Float(), nullable=False),
        sa.Column("scrammed", sa.Boolean(), nullable=False),
    )
    # History queries are always "WHERE timestamp >= cutoff ORDER BY timestamp".
    op.create_index("ix_readings_timestamp", "readings", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_readings_timestamp", table_name="readings")
    op.drop_table("readings")
