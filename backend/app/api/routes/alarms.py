"""Alarm list and operator acknowledgement."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.alarms.service import AlarmAckConflictError, AlarmAckNotFoundError, AlarmService
from app.schemas import AlarmOut

router = APIRouter(prefix="/alarms", tags=["alarms"])


def get_alarm_service(request: Request) -> AlarmService:
    service: AlarmService = request.app.state.alarms
    return service


AlarmServiceDep = Annotated[AlarmService, Depends(get_alarm_service)]


@router.get("", response_model=list[AlarmOut])
async def list_open_alarms(service: AlarmServiceDep) -> list[AlarmOut]:
    """Alarms that are not NORMAL (active, or cleared but unacknowledged), oldest first."""
    return [AlarmOut.from_record(r) for r in service.manager.open_alarms]


@router.post(
    "/{alarm_id}/ack",
    response_model=AlarmOut,
    responses={
        404: {"description": "No alarm with this id"},
        409: {"description": "Alarm has nothing to acknowledge"},
    },
)
async def acknowledge_alarm(alarm_id: uuid.UUID, service: AlarmServiceDep) -> AlarmOut:
    """Acknowledge an alarm.

    ACTIVE_UNACKED becomes ACTIVE_ACKED, and CLEARED_UNACKED becomes NORMAL. An alarm
    that is already ACTIVE_ACKED, or already back to NORMAL, gives 409 Conflict.
    """
    try:
        record = await service.acknowledge(alarm_id)
    except AlarmAckNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except AlarmAckConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return AlarmOut.from_record(record)
