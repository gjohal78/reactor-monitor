import asyncio
import json
from datetime import timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Reading
from app.db.session import make_session_factory
from app.realtime.hub import TelemetryHub
from app.sim.reactor import Reactor
from app.sim.runner import SimulationRunner
from tests.conftest import FROZEN_NOW


def make_runner(engine: Engine, hub: TelemetryHub) -> SimulationRunner:
    ticks = iter(range(10_000))
    return SimulationRunner(
        Reactor(),
        hub,
        make_session_factory(engine),
        hz=10.0,
        persist_interval_s=1.0,
        clock=lambda: FROZEN_NOW + timedelta(seconds=0.1 * next(ticks)),
    )


def test_persists_one_reading_per_second_and_broadcasts_every_tick(engine: Engine) -> None:
    hub = TelemetryHub(queue_size=100)

    async def scenario() -> None:
        queue = hub.subscribe()
        runner = make_runner(engine, hub)
        for _ in range(30):  # 3 simulated seconds at 10 Hz
            runner.tick()
            await runner.wait_for_persist()
        assert queue.qsize() == 30
        last = json.loads(hub.latest or "{}")
        assert round(last["sim_time_s"], 6) == 3.0

    asyncio.run(scenario())

    with Session(engine) as session:
        readings = session.scalars(select(Reading).order_by(Reading.timestamp)).all()
    assert [round(r.sim_time_s, 6) for r in readings] == [1.0, 2.0, 3.0]
    assert readings[0].timestamp == FROZEN_NOW + timedelta(seconds=0.9)
    assert readings[0].timestamp.tzinfo is not None


def test_slow_client_queue_drops_oldest_messages() -> None:
    hub = TelemetryHub(queue_size=3)

    async def scenario() -> list[str]:
        queue = hub.subscribe()
        for i in range(5):
            hub.publish(str(i))
        return [queue.get_nowait() for _ in range(queue.qsize())]

    assert asyncio.run(scenario()) == ["2", "3", "4"]


def test_runner_loop_ticks_at_configured_rate(engine: Engine) -> None:
    hub = TelemetryHub()
    runner = SimulationRunner(Reactor(), hub, make_session_factory(engine), hz=50.0)

    async def scenario() -> None:
        runner.start()
        await asyncio.sleep(0.5)
        await runner.stop()

    asyncio.run(scenario())

    assert 20 <= runner.ticks <= 30  # ~25 ticks in 0.5 s at 50 Hz
