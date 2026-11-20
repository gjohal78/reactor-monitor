"""FastAPI application factory and ASGI entrypoint (`uvicorn app.main:app`).

URL layout:
  /api/*  JSON API (health, history, alarms), proxied by Vite at the same path in dev
  /ws/*   WebSockets (telemetry + alarm changes)

Startup builds the DB engine, telemetry hub, alarm service and simulator runner,
reloads alarms left open by a previous run, and starts the 10 Hz loop. The schema
itself is created by Alembic (`alembic upgrade head`), not by the app.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.alarms.definitions import AlarmLimits, build_definitions
from app.alarms.manager import AlarmManager
from app.alarms.service import AlarmService
from app.alarms.store import AlarmStore
from app.api.routes import alarms, health, history, telemetry
from app.core.config import Settings, get_settings
from app.db.session import make_engine, make_session_factory
from app.realtime.hub import TelemetryHub
from app.sim.reactor import Reactor
from app.sim.runner import SimulationRunner, utc_now


def alarm_limits(settings: Settings) -> AlarmLimits:
    return AlarmLimits(
        hi_power_percent=settings.alarm_hi_power_percent,
        hi_power_deadband=settings.alarm_hi_power_deadband,
        hi_temp_c=settings.alarm_hi_temp_c,
        hi_temp_deadband=settings.alarm_hi_temp_deadband,
        short_period_s=settings.alarm_short_period_s,
        short_period_deadband=settings.alarm_short_period_deadband,
    )


def create_app(
    settings: Settings | None = None, *, clock: Callable[[], datetime] = utc_now
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
        hub = TelemetryHub()
        alarm_store = AlarmStore(session_factory)
        alarm_service = AlarmService(
            AlarmManager(build_definitions(alarm_limits(settings))), alarm_store, hub, clock
        )
        await alarm_service.restore()
        runner = SimulationRunner(
            Reactor(),
            hub,
            session_factory,
            hz=settings.simulator_hz,
            persist_interval_s=settings.persist_interval_s,
            clock=clock,
            alarms=alarm_service,
        )
        app.state.session_factory = session_factory
        app.state.hub = hub
        app.state.runner = runner
        app.state.alarms = alarm_service
        app.state.clock = clock
        if settings.simulator_enabled:
            runner.start()
        try:
            yield
        finally:
            await runner.stop()
            await alarm_service.drain()
            alarm_store.close()
            engine.dispose()

    app = FastAPI(
        title="reactor-monitor API",
        version=__version__,
        description="Educational, simplified reactor monitoring API. Not a real safety system.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(alarms.router, prefix="/api")
    app.include_router(telemetry.router)
    return app


app = create_app()
