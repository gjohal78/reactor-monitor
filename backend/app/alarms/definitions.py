"""Alarm definitions: what is measured, the limit, and the deadband.

A deadband (hysteresis) stops an alarm from chattering when the value hovers at the
limit: the alarm activates when the value crosses the limit, but only clears once the
value is back past ``limit - deadband`` (HIGH alarms) or ``limit + deadband`` (LOW
alarms). ISA-18.2 recommends deadbands for exactly this reason.

Default limits are EDUCATIONAL values chosen to sit sensibly against this simulator
(full power 100 %, 310 deg C coolant), not plant setpoints.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.sim.reactor import ReactorState


class Direction(StrEnum):
    HIGH = "HIGH"  # alarm when the value rises above the limit
    LOW = "LOW"  # alarm when the value falls below the limit


@dataclass(frozen=True, slots=True)
class AlarmDefinition:
    code: str
    description: str
    unit: str
    direction: Direction
    limit: float
    deadband: float
    # Returns None when the quantity is not meaningful (e.g. infinite period): that
    # always counts as "condition clear".
    measure: Callable[[ReactorState], float | None]

    def __post_init__(self) -> None:
        if self.deadband < 0:
            raise ValueError(f"{self.code}: deadband must be >= 0")

    def condition_active(self, value: float | None, currently_active: bool) -> bool:
        """Is the condition abnormal, given whether it was abnormal last time?

        HIGH: activates when value > limit; clears when value < limit - deadband.
        LOW:  activates when value < limit; clears when value > limit + deadband.
        """
        if value is None:
            return False
        if self.direction is Direction.HIGH:
            if currently_active:
                return value >= self.limit - self.deadband
            return value > self.limit
        if currently_active:
            return value <= self.limit + self.deadband
        return value < self.limit


def _positive_period(state: ReactorState) -> float | None:
    """Only a *rising* power has a "short period". Falling or steady power never alarms."""
    period = state.reactor_period_s
    return period if period is not None and period > 0 else None


@dataclass(frozen=True, slots=True)
class AlarmLimits:
    # HI power: 105 %. Below a typical PWR overpower trip setpoint (around 109-118 %),
    # so the operator is warned before automatic protection would act.
    hi_power_percent: float = 105.0
    hi_power_deadband: float = 2.0
    # HI coolant temperature: 314 deg C, which this model reaches at about 120 % power
    # (310 deg C at 100 %). Deadband 1 K.
    hi_temp_c: float = 314.0
    hi_temp_deadband: float = 1.0
    # Short period: power e-folding in under 15 s. Chosen against this model: a normal
    # rod withdrawal at drive speed (0.5 %/s, about 35 pcm/s) bottoms out at an 18.9 s
    # period however far the rods go, so normal operation never alarms. A withdrawal at
    # twice drive speed reaches 9.4 s and does. Alarms should mean "operator action
    # needed", not "operator just moved the rods" (ISA-18.2 nuisance-alarm guidance).
    # Deadband 5 s.
    short_period_s: float = 15.0
    short_period_deadband: float = 5.0


def build_definitions(limits: AlarmLimits | None = None) -> tuple[AlarmDefinition, ...]:
    lim = limits or AlarmLimits()
    return (
        AlarmDefinition(
            code="HI_POWER",
            description="Reactor power high",
            unit="%",
            direction=Direction.HIGH,
            limit=lim.hi_power_percent,
            deadband=lim.hi_power_deadband,
            measure=lambda s: s.power_percent,
        ),
        AlarmDefinition(
            code="HI_TEMP",
            description="Coolant temperature high",
            unit="°C",
            direction=Direction.HIGH,
            limit=lim.hi_temp_c,
            deadband=lim.hi_temp_deadband,
            measure=lambda s: s.coolant_temp_c,
        ),
        AlarmDefinition(
            code="SHORT_PERIOD",
            description="Reactor period short (power rising fast)",
            unit="s",
            direction=Direction.LOW,
            limit=lim.short_period_s,
            deadband=lim.short_period_deadband,
            measure=_positive_period,
        ),
    )
