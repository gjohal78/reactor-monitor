"""Trend data from persisted readings."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Viewer
from app.db.models import Reading
from app.db.session import get_session
from app.schemas import HistoryResponse, ReadingOut

router = APIRouter(tags=["history"])

MAX_MINUTES = 24 * 60


def get_clock(request: Request) -> Callable[[], datetime]:
    clock: Callable[[], datetime] = request.app.state.clock
    return clock


@router.get("/history", response_model=HistoryResponse)
def history(
    _user: Viewer,
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Callable[[], datetime], Depends(get_clock)],
    minutes: Annotated[int, Query(ge=1, le=MAX_MINUTES, description="Look-back window")] = 15,
) -> HistoryResponse:
    """Readings from the last ``minutes`` minutes, oldest first (one per second)."""
    cutoff = clock() - timedelta(minutes=minutes)
    rows = session.scalars(
        select(Reading).where(Reading.timestamp >= cutoff).order_by(Reading.timestamp)
    ).all()
    readings = [ReadingOut.model_validate(row) for row in rows]
    return HistoryResponse(minutes=minutes, count=len(readings), readings=readings)
