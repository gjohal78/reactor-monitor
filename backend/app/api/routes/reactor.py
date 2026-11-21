"""Reactor control: rods, scram and scram reset.

Every command, accepted or rejected, is written to the audit log with the old and new
values. Role checks happen in the dependencies (Operator / Supervisor). The rod envelope
applies to every role: rods can't be withdrawn above the minimum insertion, and one command
may withdraw them at most ``rod_max_step_percent``. Inserting rods is never limited.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.audit.log import AuditAction, AuditLogger
from app.auth.dependencies import Operator, Supervisor
from app.core.config import Settings, app_settings
from app.db.models import User
from app.schemas import ReactorControlOut, RodCommandIn
from app.sim.reactor import Reactor

router = APIRouter(prefix="/reactor", tags=["reactor control"])


def get_reactor(request: Request) -> Reactor:
    reactor: Reactor = request.app.state.runner.reactor
    return reactor


def get_audit(request: Request) -> AuditLogger:
    audit: AuditLogger = request.app.state.audit
    return audit


ReactorDep = Annotated[Reactor, Depends(get_reactor)]
AuditDep = Annotated[AuditLogger, Depends(get_audit)]


def snapshot(reactor: Reactor) -> dict[str, Any]:
    state = reactor.state
    return {
        "rod_target_percent": round(state.rod_target_percent, 3),
        "rod_position_percent": round(state.rod_position_percent, 3),
        "power_percent": round(state.power_percent, 3),
        "scrammed": state.scrammed,
    }


def control_out(reactor: Reactor) -> ReactorControlOut:
    state = reactor.state
    return ReactorControlOut(
        rod_target_percent=state.rod_target_percent,
        rod_position_percent=state.rod_position_percent,
        scrammed=state.scrammed,
    )


async def reject(
    audit: AuditLogger,
    action: AuditAction,
    user: User,
    reactor: Reactor,
    code: int,
    detail: str,
    request: Request,
    new_value: dict[str, Any] | None = None,
) -> HTTPException:
    await audit.record(
        action,
        user,
        success=False,
        old_value=snapshot(reactor),
        new_value=new_value,
        detail=detail,
        client_ip=request.client.host if request.client else None,
    )
    return HTTPException(code, detail)


@router.post("/rods", response_model=ReactorControlOut)
async def move_rods(
    command: RodCommandIn,
    user: Operator,
    reactor: ReactorDep,
    audit: AuditDep,
    request: Request,
    settings: Annotated[Settings, Depends(app_settings)],
) -> ReactorControlOut:
    """Set the rod insertion target. Rods then move at normal drive speed (0.5 %/s)."""
    requested = {"rod_target_percent": command.target_percent}
    current = reactor.state
    error: tuple[int, str] | None = None
    if current.scrammed:
        error = (status.HTTP_409_CONFLICT, "Reactor is scrammed; a supervisor must reset it")
    elif command.target_percent < settings.rod_min_insertion_percent:
        error = (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Target below the minimum insertion of {settings.rod_min_insertion_percent} %",
        )
    elif current.rod_target_percent - command.target_percent > settings.rod_max_step_percent:
        # Only withdrawal (adding reactivity) is limited per command; inserting rods is the
        # safe direction and is never blocked.
        error = (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"One command may withdraw rods at most {settings.rod_max_step_percent} %",
        )
    if error:
        raise await reject(audit, AuditAction.ROD_MOVE, user, reactor, *error, request, requested)

    old = snapshot(reactor)
    reactor.set_rod_target(command.target_percent)
    await audit.record(
        AuditAction.ROD_MOVE,
        user,
        old_value=old,
        new_value=requested,
        client_ip=request.client.host if request.client else None,
    )
    return control_out(reactor)


@router.post("/scram", response_model=ReactorControlOut)
async def scram(
    user: Operator, reactor: ReactorDep, audit: AuditDep, request: Request
) -> ReactorControlOut:
    """Trip the reactor: all rods driven fully in at scram speed. Operators can always scram."""
    if reactor.state.scrammed:
        raise await reject(
            audit, AuditAction.SCRAM, user, reactor, 409, "Reactor is already scrammed", request
        )
    old = snapshot(reactor)
    reactor.scram()
    await audit.record(
        AuditAction.SCRAM,
        user,
        old_value=old,
        new_value={"scrammed": True, "rod_target_percent": 100.0},
        client_ip=request.client.host if request.client else None,
    )
    return control_out(reactor)


@router.post("/reset-scram", response_model=ReactorControlOut)
async def reset_scram(
    user: Supervisor, reactor: ReactorDep, audit: AuditDep, request: Request
) -> ReactorControlOut:
    """Clear the scram latch (supervisor only). Allowed once the rods are fully inserted;
    they stay there until an operator moves them."""
    state = reactor.state
    if not state.scrammed:
        raise await reject(
            audit, AuditAction.SCRAM_RESET, user, reactor, 409, "Reactor is not scrammed", request
        )
    if state.rod_position_percent < 100.0:
        raise await reject(
            audit,
            AuditAction.SCRAM_RESET,
            user,
            reactor,
            409,
            "Rods are still inserting; reset once they are fully in",
            request,
        )
    old = snapshot(reactor)
    reactor.reset_scram()
    await audit.record(
        AuditAction.SCRAM_RESET,
        user,
        old_value=old,
        new_value={"scrammed": False},
        client_ip=request.client.host if request.client else None,
    )
    return control_out(reactor)
