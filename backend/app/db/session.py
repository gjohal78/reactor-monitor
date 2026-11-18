"""Engine and session factory.

The app uses synchronous SQLAlchemy. Request handlers that touch the DB are plain ``def``
functions, which FastAPI runs in its threadpool, and the simulator loop hands its
once-per-second insert to a worker thread. That keeps the event loop free without
pulling in a second (async) driver stack for a write rate of 1 row per second.
"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, from the app's session factory."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session
