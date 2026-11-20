"""Limits and deadbands for each alarm type."""

import pytest

from app.alarms.definitions import AlarmDefinition, AlarmLimits, Direction, build_definitions
from tests.alarm_helpers import make_state

DEFS = {d.code: d for d in build_definitions()}


def sweep(definition: AlarmDefinition, values: list[float | None]) -> list[bool]:
    """Feed values in order, carrying the active flag forward like the manager does."""
    active, out = False, []
    for value in values:
        active = definition.condition_active(value, active)
        out.append(active)
    return out


def test_hi_power_activates_above_limit_and_clears_below_deadband() -> None:
    # limit 105, deadband 2: on above 105, off only below 103
    values: list[float | None] = [100, 105, 105.1, 104, 103, 102.9, 104, 105.5]
    assert sweep(DEFS["HI_POWER"], values) == [
        False,  # normal
        False,  # exactly at the limit is not above it
        True,  # crossed the limit
        True,  # back below the limit but inside the deadband: still active
        True,  # at limit - deadband: still active
        False,  # below limit - deadband: clears
        False,  # inside the deadband again, but rising from clear: stays clear
        True,  # above the limit again
    ]


def test_hi_temp_deadband() -> None:
    # limit 314, deadband 1
    assert sweep(DEFS["HI_TEMP"], [313, 314.5, 313.5, 312.9]) == [False, True, True, False]


def test_short_period_activates_below_limit_and_clears_above_deadband() -> None:
    # limit 15 s, deadband 5 s: on below 15 s, off only above 20 s
    assert sweep(DEFS["SHORT_PERIOD"], [60, 14, 19, 20, 20.1, 17]) == [
        False,
        True,
        True,
        True,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        (None, None),  # steady (infinite period): nothing to measure
        (-5.0, None),  # power falling fast is not a short-period alarm
        (0.0, None),
        (12.0, 12.0),
    ],
)
def test_short_period_only_measures_rising_power(
    period: float | None, expected: float | None
) -> None:
    assert DEFS["SHORT_PERIOD"].measure(make_state(period=period)) == expected


def test_missing_value_clears_an_active_alarm() -> None:
    assert sweep(DEFS["SHORT_PERIOD"], [10, None]) == [True, False]


def test_zero_deadband_has_no_hysteresis() -> None:
    definition = build_definitions(AlarmLimits(hi_power_deadband=0.0))[0]
    assert sweep(definition, [106, 105, 104.99]) == [True, True, False]


def test_limits_are_configurable() -> None:
    definitions = {d.code: d for d in build_definitions(AlarmLimits(hi_power_percent=90.0))}

    assert definitions["HI_POWER"].limit == 90.0
    assert definitions["HI_POWER"].condition_active(95.0, currently_active=False)


def test_negative_deadband_is_rejected() -> None:
    with pytest.raises(ValueError, match="deadband"):
        AlarmDefinition(
            code="X",
            description="x",
            unit="",
            direction=Direction.HIGH,
            limit=1.0,
            deadband=-1.0,
            measure=lambda s: s.power_percent,
        )
