"""FastAPI application factory and ASGI entrypoint (`uvicorn app.main:app`).

URL layout:
  /api/*  JSON API (health, history), proxied by Vite at the same path in development
  /ws/*   WebSockets (telemetry)

Startup builds the DB engine, telemetry hub and simulator runner, and starts the 10 Hz
loop. The schema itself is created by Alembic (`alembic upgrade head`), not by the app.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import health, history, telemetry
from app.core.config import Settings, get_settings
from app.db.session import make_engine, make_session_factory
from app.realtime.hub import TelemetryHub
from app.sim.reactor import Reactor
from app.sim.runner import SimulationRunner, utc_now


def create_app(
    settings: Settings | None = None, *, clock: Callable[[], datetime] = utc_now
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
        hub = TelemetryHub()
        runner = SimulationRunner(
            Reactor(),
            hub,
            session_factory,
            hz=settings.simulator_hz,
            persist_interval_s=settings.persist_interval_s,
            clock=clock,
        )
        app.state.session_factory = session_factory
        app.state.hub = hub
        app.state.runner = runner
        app.state.clock = clock
        if settings.simulator_enabled:
            runner.start()
        try:
            yield
        finally:
            await runner.stop()
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
    app.include_router(telemetry.router)
    return app


app = create_app()
