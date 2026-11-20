"""Tracks live alarms. Pure in-memory logic, no I/O; persistence and broadcasting live in
:mod:`app.alarms.service`.

Each alarm *occurrence* is an :class:`AlarmRecord` with its own id, from the moment its
condition first goes abnormal until it returns to NORMAL. There is at most one open
occurrence per alarm code. If an alarm in CLEARED_UNACKED re-activates, the same
occurrence goes back to ACTIVE_UNACKED (``activation_count`` goes up) rather than a new
one being created: nobody has acknowledged it yet, so it is still the same problem.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from app.alarms.definitions import AlarmDefinition
from app.alarms.states import AlarmEvent, AlarmState, transition
from app.sim.reactor import ReactorState


@dataclass(frozen=True, slots=True)
class AlarmRecord:
    id: uuid.UUID
    code: str
    description: str
    unit: str
    state: AlarmState
    limit: float
    deadband: float
    trigger_value: float  # value that (most recently) activated the alarm
    activation_count: int
    activated_at: datetime
    acknowledged_at: datetime | None = None
    cleared_at: datetime | None = None
    closed_at: datetime | None = None  # when it returned to NORMAL
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AlarmChange:
    record: AlarmRecord
    previous_state: AlarmState
    event: AlarmEvent


class AlarmNotFoundError(Exception):
    pass


class AlarmManager:
    def __init__(self, definitions: Sequence[AlarmDefinition]) -> None:
        self.definitions = {d.code: d for d in definitions}
        if len(self.definitions) != len(definitions):
            raise ValueError("Alarm codes must be unique")
        self._open: dict[str, AlarmRecord] = {}  # code -> open (non-NORMAL) occurrence

    @property
    def open_alarms(self) -> list[AlarmRecord]:
        return sorted(self._open.values(), key=lambda r: r.activated_at)

    def get(self, alarm_id: uuid.UUID) -> AlarmRecord | None:
        return next((r for r in self._open.values() if r.id == alarm_id), None)

    def restore(self, records: Iterable[AlarmRecord]) -> None:
        """Reload open occurrences (e.g. from the DB after a restart)."""
        for record in records:
            if record.state is not AlarmState.NORMAL and record.code in self.definitions:
                self._open[record.code] = record

    # --- Process condition ----------------------------------------------------------------

    def evaluate(self, state: ReactorState, now: datetime) -> list[AlarmChange]:
        """Check every limit against ``state``; return the alarms whose state changed."""
        changes: list[AlarmChange] = []
        for code, definition in self.definitions.items():
            record = self._open.get(code)
            current = record.state if record else AlarmState.NORMAL
            value = definition.measure(state)
            active = definition.condition_active(value, current.condition_active)
            event = AlarmEvent.CONDITION_ACTIVE if active else AlarmEvent.CONDITION_CLEAR
            new_state = transition(current, event)
            if new_state is current:
                continue

            if record is None:  # NORMAL -> ACTIVE_UNACKED: a new occurrence
                assert value is not None  # an active condition always has a value
                record = AlarmRecord(
                    id=uuid.uuid4(),
                    code=code,
                    description=definition.description,
                    unit=definition.unit,
                    state=new_state,
                    limit=definition.limit,
                    deadband=definition.deadband,
                    trigger_value=value,
                    activation_count=1,
                    activated_at=now,
                    updated_at=now,
                )
            elif active:  # CLEARED_UNACKED -> ACTIVE_UNACKED: came back before an ack
                assert value is not None
                record = replace(
                    record,
                    state=new_state,
                    trigger_value=value,
                    activation_count=record.activation_count + 1,
                    cleared_at=None,
                    updated_at=now,
                )
            else:  # condition cleared: -> CLEARED_UNACKED, or -> NORMAL if already acked
                record = replace(record, state=new_state, cleared_at=now, updated_at=now)
                if new_state is AlarmState.NORMAL:
                    record = replace(record, closed_at=now)

            changes.append(self._store(record, current, event))
        return changes

    # --- Operator acknowledgement -----------------------------------------------------------

    def acknowledge(self, alarm_id: uuid.UUID, now: datetime) -> AlarmChange:
        """Acknowledge an open alarm.

        Raises AlarmNotFoundError if the id is not an open alarm, or
        InvalidTransitionError if it has nothing to acknowledge (ACTIVE_ACKED).
        """
        record = self.get(alarm_id)
        if record is None:
            raise AlarmNotFoundError(alarm_id)
        new_state = transition(record.state, AlarmEvent.ACK)
        updated = replace(record, state=new_state, acknowledged_at=now, updated_at=now)
        if new_state is AlarmState.NORMAL:
            updated = replace(updated, closed_at=now)
        return self._store(updated, record.state, AlarmEvent.ACK)

    def _store(self, record: AlarmRecord, previous: AlarmState, event: AlarmEvent) -> AlarmChange:
        if record.state is AlarmState.NORMAL:
            self._open.pop(record.code, None)
        else:
            self._open[record.code] = record
        return AlarmChange(record=record, previous_state=previous, event=event)
