"""ORM models. Alembic migrations in ``migrations/`` are the source of truth for the schema."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, Float, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
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


ROLE_VALUES = ("viewer", "operator", "supervisor")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN {ROLE_VALUES}", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bump to invalidate every token issued so far (password change, deactivation, ...).
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


# JSONB on Postgres (indexable, compact); plain JSON elsewhere (SQLite in tests).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    """Append-only record of logins and control actions.

    The application only ever INSERTs. The migration also adds database triggers that
    reject UPDATE and DELETE (and TRUNCATE on Postgres), so the log can't be edited
    through this app or by hand without first dropping the triggers.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    # user_id is null for a failed login with an unknown username. username and role are
    # copied in, so the entry stays meaningful even if the user is later renamed.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
