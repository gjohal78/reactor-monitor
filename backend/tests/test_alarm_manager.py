"""AlarmManager: each transition as it happens on a real alarm occurrence."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.alarms.definitions import build_definitions
from app.alarms.manager import AlarmManager, AlarmNotFoundError
from app.alarms.states import AlarmEvent, AlarmState, InvalidTransitionError
from app.sim.reactor import Reactor, ReactorParams
from tests.alarm_helpers import HIGH_POWER_STATE, NORMAL_STATE, make_state

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def manager() -> AlarmManager:
    return AlarmManager(build_definitions())


def raise_hi_power(manager: AlarmManager) -> uuid.UUID:
    (change,) = manager.evaluate(HIGH_POWER_STATE, at(0))
    return change.record.id


def test_normal_to_active_unacked(manager: AlarmManager) -> None:
    (change,) = manager.evaluate(HIGH_POWER_STATE, at(0))

    record = change.record
    assert (change.previous_state, record.state) == (AlarmState.NORMAL, AlarmState.ACTIVE_UNACKED)
    assert change.event is AlarmEvent.CONDITION_ACTIVE
    assert record.code == "HI_POWER"
    assert record.trigger_value == 110.0
    assert (record.limit, record.deadband) == (105.0, 2.0)
    assert record.activated_at == at(0)
    assert record.activation_count == 1
    assert record.acknowledged_at is record.cleared_at is record.closed_at is None
    assert manager.open_alarms == [record]


def test_normal_stays_normal_without_changes(manager: AlarmManager) -> None:
    assert manager.evaluate(NORMAL_STATE, at(0)) == []
    assert manager.open_alarms == []


def test_active_unacked_stays_active_without_new_changes(manager: AlarmManager) -> None:
    raise_hi_power(manager)

    assert manager.evaluate(make_state(power=104.0), at(1)) == []  # inside the deadband


def test_active_unacked_to_active_acked(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)

    change = manager.acknowledge(alarm_id, at(5))

    assert (change.previous_state, change.record.state) == (
        AlarmState.ACTIVE_UNACKED,
        AlarmState.ACTIVE_ACKED,
    )
    assert change.event is AlarmEvent.ACK
    assert change.record.acknowledged_at == at(5)
    assert manager.open_alarms == [change.record]


def test_active_unacked_to_cleared_unacked(manager: AlarmManager) -> None:
    raise_hi_power(manager)

    (change,) = manager.evaluate(NORMAL_STATE, at(10))

    assert (change.previous_state, change.record.state) == (
        AlarmState.ACTIVE_UNACKED,
        AlarmState.CLEARED_UNACKED,
    )
    assert change.record.cleared_at == at(10)
    assert change.record.closed_at is None
    assert manager.open_alarms == [change.record]  # still waiting for an ack


def test_active_acked_to_normal(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)
    manager.acknowledge(alarm_id, at(5))

    (change,) = manager.evaluate(NORMAL_STATE, at(10))

    assert (change.previous_state, change.record.state) == (
        AlarmState.ACTIVE_ACKED,
        AlarmState.NORMAL,
    )
    assert change.record.cleared_at == change.record.closed_at == at(10)
    assert manager.open_alarms == []


def test_active_acked_cannot_be_acked_again(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)
    manager.acknowledge(alarm_id, at(5))

    with pytest.raises(InvalidTransitionError):
        manager.acknowledge(alarm_id, at(6))


def test_cleared_unacked_to_normal_on_ack(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)
    manager.evaluate(NORMAL_STATE, at(10))

    change = manager.acknowledge(alarm_id, at(20))

    assert (change.previous_state, change.record.state) == (
        AlarmState.CLEARED_UNACKED,
        AlarmState.NORMAL,
    )
    assert change.record.acknowledged_at == change.record.closed_at == at(20)
    assert manager.open_alarms == []


def test_cleared_unacked_back_to_active_unacked(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)
    manager.evaluate(NORMAL_STATE, at(10))

    (change,) = manager.evaluate(make_state(power=120.0), at(15))

    record = change.record
    assert (change.previous_state, record.state) == (
        AlarmState.CLEARED_UNACKED,
        AlarmState.ACTIVE_UNACKED,
    )
    assert record.id == alarm_id  # same occurrence: nobody acknowledged it yet
    assert record.activation_count == 2
    assert record.trigger_value == 120.0
    assert record.activated_at == at(0)
    assert record.cleared_at is None


def test_closed_alarm_is_not_found_and_new_occurrence_gets_new_id(
    manager: AlarmManager,
) -> None:
    first_id = raise_hi_power(manager)
    manager.acknowledge(first_id, at(1))
    manager.evaluate(NORMAL_STATE, at(2))

    with pytest.raises(AlarmNotFoundError):
        manager.acknowledge(first_id, at(3))
    (change,) = manager.evaluate(HIGH_POWER_STATE, at(4))
    assert change.record.id != first_id


def test_unknown_id_is_not_found(manager: AlarmManager) -> None:
    with pytest.raises(AlarmNotFoundError):
        manager.acknowledge(uuid.uuid4(), at(0))


def test_alarms_are_independent(manager: AlarmManager) -> None:
    changes = manager.evaluate(make_state(power=125.0, temp=316.0, period=10.0), at(0))

    assert {c.record.code for c in changes} == {"HI_POWER", "HI_TEMP", "SHORT_PERIOD"}
    hi_temp = next(c.record for c in changes if c.record.code == "HI_TEMP")
    manager.acknowledge(hi_temp.id, at(1))

    states = {r.code: r.state for r in manager.open_alarms}
    assert states == {
        "HI_POWER": AlarmState.ACTIVE_UNACKED,
        "HI_TEMP": AlarmState.ACTIVE_ACKED,
        "SHORT_PERIOD": AlarmState.ACTIVE_UNACKED,
    }


def test_restore_reloads_open_alarms_only(manager: AlarmManager) -> None:
    alarm_id = raise_hi_power(manager)
    saved = manager.open_alarms

    fresh = AlarmManager(build_definitions())
    fresh.restore(saved)

    assert fresh.get(alarm_id) == saved[0]
    (change,) = fresh.evaluate(NORMAL_STATE, at(10))  # restart at normal power
    assert change.record.state is AlarmState.CLEARED_UNACKED  # still needs an ack


def run_withdrawal(manager: AlarmManager, reactor: Reactor) -> list[tuple[str, AlarmState]]:
    reactor.set_rod_target(18.0)  # withdraw 2 % of stroke: +126 pcm
    seen: list[tuple[str, AlarmState]] = []
    for tick in range(600):  # 60 s at 10 Hz
        state = reactor.step(0.1)
        seen += [(c.record.code, c.record.state) for c in manager.evaluate(state, at(tick))]
    return seen


def test_normal_rod_withdrawal_raises_hi_power_but_not_short_period(
    manager: AlarmManager,
) -> None:
    seen = run_withdrawal(manager, Reactor())

    # Power settles near 132 % and coolant near 316 deg C ...
    assert ("HI_POWER", AlarmState.ACTIVE_UNACKED) in seen
    assert ("HI_TEMP", AlarmState.ACTIVE_UNACKED) in seen
    # ... but at normal drive speed the period bottoms out at ~19 s: no nuisance alarm.
    assert all(code != "SHORT_PERIOD" for code, _ in seen)


def test_fast_rod_withdrawal_raises_short_period(manager: AlarmManager) -> None:
    fast_rods = replace(ReactorParams(), rod_speed_percent_per_s=1.0)  # 2x drive speed

    seen = run_withdrawal(manager, Reactor(fast_rods))

    assert ("SHORT_PERIOD", AlarmState.ACTIVE_UNACKED) in seen
    # Rods stop, feedback turns the rise over, and the alarm clears unacknowledged.
    assert ("SHORT_PERIOD", AlarmState.CLEARED_UNACKED) in seen
