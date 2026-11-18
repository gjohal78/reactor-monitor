"""Runs the reactor in the background: steps it at a fixed rate, broadcasts every sample
and persists one reading per ``persist_interval_s``.

Timing: each tick advances simulated time by exactly ``1 / hz`` seconds, and ticks are
scheduled against absolute deadlines (``next += period``) rather than by sleeping a fixed
period after each step. Sleeping after the work would add the step's own run time every
tick and slowly drift behind the wall clock. If the loop ever falls more than a second
behind (e.g. the laptop slept), it resynchronises instead of firing a burst of catch-up
ticks, so the simulation pauses rather than fast-forwarding.

Persistence runs in a worker thread (``asyncio.to_thread``) so a slow database never
blocks the 10 Hz loop. If the previous insert is still running when the next one is due,
the new one is skipped and logged instead of queueing up behind it.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Reading
from app.realtime.hub import TelemetryHub
from app.schemas import Telemetry
from app.sim.reactor import Reactor

logger = logging.getLogger(__name__)

MAX_LAG_S = 1.0


def utc_now() -> datetime:
    return datetime.now(UTC)


class SimulationRunner:
    def __init__(
        self,
        reactor: Reactor,
        hub: TelemetryHub,
        session_factory: sessionmaker[Session],
        *,
        hz: float = 10.0,
        persist_interval_s: float = 1.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.reactor = reactor
        self.hub = hub
        self._session_factory = session_factory
        self.period_s = 1.0 / hz
        self.persist_every = max(1, round(persist_interval_s * hz))
        self._clock = clock
        self.ticks = 0
        self._task: asyncio.Task[None] | None = None
        self._persist_task: asyncio.Task[None] | None = None

    # --- Lifecycle ----------------------------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run(), name="simulation-runner")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.wait_for_persist()

    async def wait_for_persist(self) -> None:
        """Wait for an in-flight insert (if any) to finish. Errors are already logged."""
        if self._persist_task is not None:
            with contextlib.suppress(Exception):
                await self._persist_task

    # --- Loop ---------------------------------------------------------------------------

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        while True:
            try:
                self.tick()
            except Exception:
                logger.exception("Simulation tick failed")
            next_deadline += self.period_s
            delay = next_deadline - loop.time()
            if delay < -MAX_LAG_S:
                logger.warning("Simulation fell %.1f s behind; resynchronising", -delay)
                next_deadline = loop.time()
                delay = 0.0
            await asyncio.sleep(max(delay, 0.0))

    def tick(self) -> Telemetry:
        """Advance one period, broadcast the new state and persist it when due."""
        state = self.reactor.step(self.period_s)
        self.ticks += 1
        telemetry = Telemetry.from_state(state, self._clock())
        self.hub.publish(telemetry.model_dump_json())
        if self.ticks % self.persist_every == 0:
            self._schedule_persist(telemetry)
        return telemetry

    # --- Persistence --------------------------------------------------------------------

    def _schedule_persist(self, telemetry: Telemetry) -> None:
        if self._persist_task is not None and not self._persist_task.done():
            logger.warning("Previous reading still being saved; skipping this one")
            return
        self._persist_task = asyncio.create_task(asyncio.to_thread(self._save, telemetry))
        self._persist_task.add_done_callback(self._log_persist_error)

    def _save(self, telemetry: Telemetry) -> None:
        with self._session_factory() as session, session.begin():
            session.add(Reading(**telemetry.model_dump()))

    @staticmethod
    def _log_persist_error(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("Failed to save reading", exc_info=error)
