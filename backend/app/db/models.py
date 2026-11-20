"""ORM models. Alembic migrations in ``migrations/`` are the source of truth for the schema."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, Integer, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UTCDateTime


class Base(DeclarativeBase):
    pass


class Reading(Base):
    """One persisted snapshot of the simulator state (written once per second)."""

    __tablename__ = "readings"

    # BigInteger in Postgres (1 row/s is ~31.5 M rows/year); plain INTEGER on SQLite so
    # the column is a rowid alias and autoincrements in tests.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    sim_time_s: Mapped[float] = mapped_column(Float)
    power_percent: Mapped[float] = mapped_column(Float)
    coolant_temp_c: Mapped[float] = mapped_column(Float)
    rod_position_percent: Mapped[float] = mapped_column(Float)
    rod_target_percent: Mapped[float] = mapped_column(Float)
    reactor_period_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    reactivity_pcm: Mapped[float] = mapped_column(Float)
    scrammed: Mapped[bool] = mapped_column(Boolean)


class Alarm(Base):
    """One alarm occurrence: from activation until it returns to NORMAL.

    The row is updated on every state change, so its timestamps record the whole
    lifecycle (activated, acknowledged, cleared, closed).
    """

    __tablename__ = "alarms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(20), index=True)
    limit: Mapped[float] = mapped_column(Float)
    deadband: Mapped[float] = mapped_column(Float)
    trigger_value: Mapped[float] = mapped_column(Float)
    activation_count: Mapped[int] = mapped_column(Integer)
    activated_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
