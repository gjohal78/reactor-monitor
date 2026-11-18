"""ORM models. Alembic migrations in ``migrations/`` are the source of truth for the schema."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, Integer
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
