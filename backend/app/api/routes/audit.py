"""Audit log (supervisor only). Read-only: there are no write routes for it."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.log import AuditAction
from app.auth.dependencies import Supervisor
from app.db.models import AuditLog
from app.db.session import get_session
from app.schemas import AuditEntryOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
def list_audit_entries(
    _user: Supervisor,
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: AuditAction | None = None,
    username: str | None = None,
) -> list[AuditEntryOut]:
    """Newest first. Filter by ``action`` and/or ``username``; page with limit/offset."""
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if action is not None:
        query = query.where(AuditLog.action == action.value)
    if username is not None:
        query = query.where(AuditLog.username == username)
    return [AuditEntryOut.model_validate(row) for row in session.scalars(query)]
