"""Alarm list, operator acknowledgement and (supervisor) alarm limits."""

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.alarms.definitions import AlarmLimits
from app.alarms.service import AlarmAckConflictError, AlarmAckNotFoundError, AlarmService
from app.api.routes.reactor import AuditDep
from app.audit.log import AuditAction
from app.auth.dependencies import Operator, Supervisor, Viewer
from app.schemas import AlarmLimitsIO, AlarmOut

router = APIRouter(prefix="/alarms", tags=["alarms"])


def get_alarm_service(request: Request) -> AlarmService:
    service: AlarmService = request.app.state.alarms
    return service


AlarmServiceDep = Annotated[AlarmService, Depends(get_alarm_service)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=list[AlarmOut])
async def list_open_alarms(_user: Viewer, service: AlarmServiceDep) -> list[AlarmOut]:
    """Alarms that are not NORMAL (active, or cleared but unacknowledged), oldest first."""
    return [AlarmOut.from_record(r) for r in service.manager.open_alarms]


@router.get("/limits", response_model=AlarmLimitsIO)
async def get_limits(_user: Viewer, service: AlarmServiceDep) -> AlarmLimitsIO:
    return AlarmLimitsIO(**dataclasses.asdict(service.limits))


@router.put("/limits", response_model=AlarmLimitsIO)
async def set_limits(
    limits: AlarmLimitsIO,
    user: Supervisor,
    service: AlarmServiceDep,
    audit: AuditDep,
    request: Request,
) -> AlarmLimitsIO:
    """Replace all alarm limits (supervisor only). Applies from the next simulator tick.

    Changes are held in memory: a restart goes back to the ALARM_* settings. Every change
    is in the audit log with the old and new values.
    """
    old = dataclasses.asdict(service.limits)
    service.set_limits(AlarmLimits(**limits.model_dump()))
    await audit.record(
        AuditAction.ALARM_LIMITS_CHANGE,
        user,
        old_value=old,
        new_value=limits.model_dump(),
        client_ip=client_ip(request),
    )
    return limits


@router.post(
    "/{alarm_id}/ack",
    response_model=AlarmOut,
    responses={
        404: {"description": "No alarm with this id"},
        409: {"description": "Alarm has nothing to acknowledge"},
    },
)
async def acknowledge_alarm(
    alarm_id: uuid.UUID,
    user: Operator,
    service: AlarmServiceDep,
    audit: AuditDep,
    request: Request,
) -> AlarmOut:
    """Acknowledge an alarm (operator or supervisor).

    ACTIVE_UNACKED becomes ACTIVE_ACKED, and CLEARED_UNACKED becomes NORMAL. An alarm
    that is already ACTIVE_ACKED, or already back to NORMAL, gives 409 Conflict.
    """
    try:
        change = await service.acknowledge(alarm_id)
    except (AlarmAckNotFoundError, AlarmAckConflictError) as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if isinstance(error, AlarmAckNotFoundError)
            else status.HTTP_409_CONFLICT
        )
        await audit.record(
            AuditAction.ALARM_ACK,
            user,
            target=str(alarm_id),
            success=False,
            detail=str(error),
            client_ip=client_ip(request),
        )
        raise HTTPException(code, str(error)) from None

    await audit.record(
        AuditAction.ALARM_ACK,
        user,
        target=str(alarm_id),
        old_value={"state": change.previous_state.value},
        new_value={"state": change.record.state.value},
        detail=change.record.code,
        client_ip=client_ip(request),
    )
    return AlarmOut.from_record(change.record)
