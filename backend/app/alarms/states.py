"""Alarm state machine, modelled on ISA-18.2 / EEMUA 191 control-room practice.

Two independent facts make up an alarm's state: is the process condition still
abnormal, and has an operator acknowledged it? That gives four states::

    NORMAL           condition clear, nothing to acknowledge
    ACTIVE_UNACKED   condition abnormal, operator has not acknowledged   (new alarm)
    ACTIVE_ACKED     condition abnormal, operator has acknowledged
    CLEARED_UNACKED  condition back to normal, but the operator never acknowledged it
                     (ISA-18.2 "return to normal unacknowledged")

Transitions::

    NORMAL          --condition active-->  ACTIVE_UNACKED
    ACTIVE_UNACKED  --ack-->               ACTIVE_ACKED
    ACTIVE_UNACKED  --condition clear-->   CLEARED_UNACKED
    ACTIVE_ACKED    --condition clear-->   NORMAL
    CLEARED_UNACKED --ack-->               NORMAL
    CLEARED_UNACKED --condition active-->  ACTIVE_UNACKED   (it came back before anyone saw it)

Two consequences worth knowing. First, an alarm only reaches NORMAL once the condition
has cleared *and* someone has acknowledged it, in either order, so a transient that came
and went is never lost. Second, an acknowledged alarm that clears goes straight to NORMAL,
because there is nothing left to acknowledge. So ACTIVE_ACKED never passes through
CLEARED_UNACKED.

Re-reporting the condition an alarm is already in is a no-op. Acknowledging an alarm
that has nothing to acknowledge (NORMAL or ACTIVE_ACKED) is an error, which the API
reports as 409 Conflict.
"""

from enum import StrEnum


class AlarmState(StrEnum):
    NORMAL = "NORMAL"
    ACTIVE_UNACKED = "ACTIVE_UNACKED"
    ACTIVE_ACKED = "ACTIVE_ACKED"
    CLEARED_UNACKED = "CLEARED_UNACKED"

    @property
    def condition_active(self) -> bool:
        return self in (AlarmState.ACTIVE_UNACKED, AlarmState.ACTIVE_ACKED)

    @property
    def needs_ack(self) -> bool:
        return self in (AlarmState.ACTIVE_UNACKED, AlarmState.CLEARED_UNACKED)


class AlarmEvent(StrEnum):
    CONDITION_ACTIVE = "CONDITION_ACTIVE"
    CONDITION_CLEAR = "CONDITION_CLEAR"
    ACK = "ACK"


class InvalidTransitionError(Exception):
    def __init__(self, state: AlarmState, event: AlarmEvent) -> None:
        super().__init__(f"{event} is not allowed in state {state}")
        self.state = state
        self.event = event


_S = AlarmState
_E = AlarmEvent

# Every (state, event) pair is listed; a missing pair is an invalid transition.
TRANSITIONS: dict[tuple[AlarmState, AlarmEvent], AlarmState] = {
    (_S.NORMAL, _E.CONDITION_ACTIVE): _S.ACTIVE_UNACKED,
    (_S.NORMAL, _E.CONDITION_CLEAR): _S.NORMAL,
    (_S.ACTIVE_UNACKED, _E.CONDITION_ACTIVE): _S.ACTIVE_UNACKED,
    (_S.ACTIVE_UNACKED, _E.CONDITION_CLEAR): _S.CLEARED_UNACKED,
    (_S.ACTIVE_UNACKED, _E.ACK): _S.ACTIVE_ACKED,
    (_S.ACTIVE_ACKED, _E.CONDITION_ACTIVE): _S.ACTIVE_ACKED,
    (_S.ACTIVE_ACKED, _E.CONDITION_CLEAR): _S.NORMAL,
    (_S.CLEARED_UNACKED, _E.CONDITION_ACTIVE): _S.ACTIVE_UNACKED,
    (_S.CLEARED_UNACKED, _E.CONDITION_CLEAR): _S.CLEARED_UNACKED,
    (_S.CLEARED_UNACKED, _E.ACK): _S.NORMAL,
}


def transition(state: AlarmState, event: AlarmEvent) -> AlarmState:
    """Return the next state, or raise InvalidTransitionError (ACK with nothing to ack)."""
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidTransitionError(state, event) from None
