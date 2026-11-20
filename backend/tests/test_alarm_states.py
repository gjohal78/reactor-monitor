"""Exhaustive tests of the alarm state machine: every (state, event) pair."""

import itertools

import pytest

from app.alarms.states import (
    TRANSITIONS,
    AlarmEvent,
    AlarmState,
    InvalidTransitionError,
    transition,
)

S, E = AlarmState, AlarmEvent

VALID = [
    # (from, event, to)
    (S.NORMAL, E.CONDITION_ACTIVE, S.ACTIVE_UNACKED),  # new alarm
    (S.NORMAL, E.CONDITION_CLEAR, S.NORMAL),  # nothing happening
    (S.ACTIVE_UNACKED, E.CONDITION_ACTIVE, S.ACTIVE_UNACKED),  # still abnormal
    (S.ACTIVE_UNACKED, E.ACK, S.ACTIVE_ACKED),  # operator acknowledges
    (S.ACTIVE_UNACKED, E.CONDITION_CLEAR, S.CLEARED_UNACKED),  # cleared before ack
    (S.ACTIVE_ACKED, E.CONDITION_ACTIVE, S.ACTIVE_ACKED),  # still abnormal
    (S.ACTIVE_ACKED, E.CONDITION_CLEAR, S.NORMAL),  # acked and cleared: done
    (S.CLEARED_UNACKED, E.CONDITION_ACTIVE, S.ACTIVE_UNACKED),  # came back before ack
    (S.CLEARED_UNACKED, E.CONDITION_CLEAR, S.CLEARED_UNACKED),  # still waiting for ack
    (S.CLEARED_UNACKED, E.ACK, S.NORMAL),  # late ack closes it
]

INVALID = [
    (S.NORMAL, E.ACK),  # nothing to acknowledge
    (S.ACTIVE_ACKED, E.ACK),  # already acknowledged
]


@pytest.mark.parametrize(("state", "event", "expected"), VALID)
def test_valid_transition(state: AlarmState, event: AlarmEvent, expected: AlarmState) -> None:
    assert transition(state, event) is expected


@pytest.mark.parametrize(("state", "event"), INVALID)
def test_invalid_transition_raises(state: AlarmState, event: AlarmEvent) -> None:
    with pytest.raises(InvalidTransitionError) as excinfo:
        transition(state, event)

    assert excinfo.value.state is state
    assert excinfo.value.event is event


def test_every_state_event_pair_is_covered_exactly_once() -> None:
    covered = [(s, e) for s, e, _ in VALID] + INVALID

    assert sorted(covered) == sorted(itertools.product(AlarmState, AlarmEvent))
    assert set(TRANSITIONS) == {(s, e) for s, e, _ in VALID}


def run(events: list[AlarmEvent]) -> list[AlarmState]:
    state, seen = AlarmState.NORMAL, []
    for event in events:
        state = transition(state, event)
        seen.append(state)
    return seen


def test_lifecycle_ack_while_active() -> None:
    assert run([E.CONDITION_ACTIVE, E.ACK, E.CONDITION_CLEAR]) == [
        S.ACTIVE_UNACKED,
        S.ACTIVE_ACKED,
        S.NORMAL,
    ]


def test_lifecycle_clear_before_ack() -> None:
    assert run([E.CONDITION_ACTIVE, E.CONDITION_CLEAR, E.ACK]) == [
        S.ACTIVE_UNACKED,
        S.CLEARED_UNACKED,
        S.NORMAL,
    ]


def test_lifecycle_returns_before_ack() -> None:
    assert run([E.CONDITION_ACTIVE, E.CONDITION_CLEAR, E.CONDITION_ACTIVE, E.ACK]) == [
        S.ACTIVE_UNACKED,
        S.CLEARED_UNACKED,
        S.ACTIVE_UNACKED,
        S.ACTIVE_ACKED,
    ]


@pytest.mark.parametrize("state", list(AlarmState))
def test_state_flags(state: AlarmState) -> None:
    assert state.condition_active == (state in {S.ACTIVE_UNACKED, S.ACTIVE_ACKED})
    assert state.needs_ack == (state in {S.ACTIVE_UNACKED, S.CLEARED_UNACKED})
