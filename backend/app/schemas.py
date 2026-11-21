"""API schemas shared by the WebSocket stream and the history endpoint."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.alarms.manager import AlarmChange, AlarmRecord
from app.alarms.states import AlarmEvent, AlarmState
from app.sim.reactor import ReactorState


class StateFields(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sim_time_s: float
    power_percent: float
    coolant_temp_c: float
    rod_position_percent: float
    rod_target_percent: float
    # Seconds; null means effectively infinite (steady). Negative means power is falling.
    reactor_period_s: float | None
    reactivity_pcm: float
    scrammed: bool


class Telemetry(StateFields):
    """One live sample, as broadcast on /ws/telemetry (and stored as a Reading)."""

    timestamp: datetime

    @classmethod
    def from_state(cls, state: ReactorState, timestamp: datetime) -> "Telemetry":
        return cls(
            timestamp=timestamp,
            sim_time_s=state.time_s,
            power_percent=state.power_percent,
            coolant_temp_c=state.coolant_temp_c,
            rod_position_percent=state.rod_position_percent,
            rod_target_percent=state.rod_target_percent,
            reactor_period_s=state.reactor_period_s,
            reactivity_pcm=state.reactivity_pcm,
            scrammed=state.scrammed,
        )


class ReadingOut(StateFields):
    id: int
    timestamp: datetime


class HistoryResponse(BaseModel):
    minutes: int
    count: int
    readings: list[ReadingOut]


# --- Alarms ---------------------------------------------------------------------------------


class AlarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str
    unit: str
    state: AlarmState
    limit: float
    deadband: float
    trigger_value: float
    activation_count: int
    activated_at: datetime
    acknowledged_at: datetime | None
    cleared_at: datetime | None
    closed_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_record(cls, record: AlarmRecord) -> "AlarmOut":
        return cls.model_validate(record)


class AlarmChangeOut(AlarmOut):
    previous_state: AlarmState
    event: AlarmEvent

    @classmethod
    def from_change(cls, change: AlarmChange) -> "AlarmChangeOut":
        base = AlarmOut.from_record(change.record).model_dump()
        return cls(**base, previous_state=change.previous_state, event=change.event)


# --- WebSocket messages -----------------------------------------------------------------------
# Every frame on /ws/telemetry is {"type": ..., "data": ...} so clients can dispatch on type.


class TelemetryMessage(BaseModel):
    type: Literal["telemetry"] = "telemetry"
    data: Telemetry


class AlarmMessage(BaseModel):
    type: Literal["alarm"] = "alarm"
    data: AlarmChangeOut


class AlarmSnapshotMessage(BaseModel):
    """Sent once on connect: every alarm that is currently open."""

    type: Literal["alarm_snapshot"] = "alarm_snapshot"
    data: list[AlarmOut]


# --- Auth -------------------------------------------------------------------------------------


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access token lifetime, seconds


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str


# --- Reactor control ------------------------------------------------------------------------


class RodCommandIn(BaseModel):
    target_percent: float = Field(ge=0, le=100, description="Rod insertion target, % of stroke")


class ReactorControlOut(BaseModel):
    rod_target_percent: float
    rod_position_percent: float
    scrammed: bool


# --- Alarm limits ---------------------------------------------------------------------------


class AlarmLimitsIO(BaseModel):
    hi_power_percent: float = Field(gt=0, le=200)
    hi_power_deadband: float = Field(ge=0, le=50)
    hi_temp_c: float = Field(gt=0, le=1000)
    hi_temp_deadband: float = Field(ge=0, le=50)
    short_period_s: float = Field(gt=0, le=3600)
    short_period_deadband: float = Field(ge=0, le=600)


# --- Audit ----------------------------------------------------------------------------------


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    user_id: int | None
    username: str
    role: str | None
    action: str
    target: str | None
    success: bool
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    detail: str | None
    client_ip: str | None
