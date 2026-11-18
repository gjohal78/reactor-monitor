"""API schemas shared by the WebSocket stream and the history endpoint."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
