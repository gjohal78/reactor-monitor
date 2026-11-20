"""Connects the in-memory AlarmManager to the database and the WebSocket hub.

Everything here runs on the event loop, the same thread as the simulator, so the
manager needs no locking: an acknowledgement and a simulator tick can never interleave.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from app.alarms.manager import AlarmChange, AlarmManager, AlarmNotFoundError, AlarmRecord
from app.alarms.states import AlarmState, InvalidTransitionError
from app.alarms.store import AlarmStore
from app.realtime.hub import TelemetryHub
from app.schemas import AlarmChangeOut, AlarmMessage, AlarmOut, AlarmSnapshotMessage
from app.sim.reactor import ReactorState

logger = logging.getLogger(__name__)


class AlarmAckError(Exception):
    """Base for acknowledgement failures."""


class AlarmAckNotFoundError(AlarmAckError):
    pass


class AlarmAckConflictError(AlarmAckError):
    def __init__(self, message: str, state: AlarmState) -> None:
        super().__init__(message)
        self.state = state


class AlarmService:
    def __init__(
        self,
        manager: AlarmManager,
        store: AlarmStore,
        hub: TelemetryHub,
        clock: Callable[[], datetime],
    ) -> None:
        self.manager = manager
        self.store = store
        self.hub = hub
        self._clock = clock
        self._pending: set[asyncio.Future[None]] = set()

    async def restore(self) -> None:
        """Reload alarms left open by a previous run, so unacknowledged ones still need an ack."""
        self.manager.restore(await self.store.load_open())

    def evaluate(self, state: ReactorState, now: datetime) -> list[AlarmChange]:
        """Called by the simulator every tick. Broadcasts and persists without waiting."""
        changes = self.manager.evaluate(state, now)
        for change in changes:
            self._publish(change)
            self._persist_in_background(change.record)
        return changes

    async def acknowledge(self, alarm_id: uuid.UUID) -> AlarmRecord:
        try:
            change = self.manager.acknowledge(alarm_id, self._clock())
        except AlarmNotFoundError:
            if await self.store.exists(alarm_id):
                raise AlarmAckConflictError(
                    "Alarm has already returned to NORMAL", AlarmState.NORMAL
                ) from None
            raise AlarmAckNotFoundError(f"No alarm with id {alarm_id}") from None
        except InvalidTransitionError as error:
            raise AlarmAckConflictError(
                f"Alarm is {error.state}: nothing to acknowledge", error.state
            ) from None
        self._publish(change)
        await self.store.save(change.record)  # respond only once the ack is stored
        return change.record

    def snapshot_message(self) -> str:
        alarms = [AlarmOut.from_record(r) for r in self.manager.open_alarms]
        return AlarmSnapshotMessage(data=alarms).model_dump_json()

    async def drain(self) -> None:
        """Wait for background writes queued so far (used at shutdown and in tests)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    def _publish(self, change: AlarmChange) -> None:
        message = AlarmMessage(data=AlarmChangeOut.from_change(change))
        self.hub.publish(message.model_dump_json(), critical=True)

    def _persist_in_background(self, record: AlarmRecord) -> None:
        future = asyncio.ensure_future(self.store.save(record))
        self._pending.add(future)
        future.add_done_callback(self._on_saved)

    def _on_saved(self, future: asyncio.Future[None]) -> None:
        self._pending.discard(future)
        if not future.cancelled() and (error := future.exception()) is not None:
            logger.error("Failed to save alarm", exc_info=error)
