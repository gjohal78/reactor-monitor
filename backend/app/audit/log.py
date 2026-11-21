"""Writing audit entries. There is deliberately no update or delete function."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditLog, User


class AuditAction(StrEnum):
    LOGIN = "LOGIN"
    ALARM_ACK = "ALARM_ACK"
    ROD_MOVE = "ROD_MOVE"
    SCRAM = "SCRAM"
    SCRAM_RESET = "SCRAM_RESET"
    ALARM_LIMITS_CHANGE = "ALARM_LIMITS_CHANGE"


def write_audit(
    session: Session,
    *,
    timestamp: datetime,
    action: AuditAction,
    user: User | None,
    username: str | None = None,
    success: bool = True,
    target: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    detail: str | None = None,
    client_ip: str | None = None,
) -> AuditLog:
    """Add an entry to ``session`` (the caller commits, so it can share a transaction)."""
    entry = AuditLog(
        timestamp=timestamp,
        user_id=user.id if user else None,
        username=(user.username if user else username or "")[:64],
        role=user.role if user else None,
        action=action.value,
        target=target,
        success=success,
        old_value=old_value,
        new_value=new_value,
        detail=detail[:200] if detail else None,
        client_ip=client_ip,
    )
    session.add(entry)
    return entry


class AuditLogger:
    """For async endpoints: writes one entry in its own transaction, off the event loop."""

    def __init__(
        self, session_factory: sessionmaker[Session], clock: Callable[[], datetime]
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def record(self, action: AuditAction, user: User, **fields: Any) -> None:
        timestamp = self._clock()

        def insert() -> None:
            with self._session_factory() as session, session.begin():
                write_audit(session, timestamp=timestamp, action=action, user=user, **fields)

        await asyncio.to_thread(insert)
