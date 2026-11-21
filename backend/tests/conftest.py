"""Test fixtures.

Each test gets a fresh SQLite database file whose schema is built by running the real
Alembic migrations, so the migrations themselves are exercised on every test run. Set
TEST_DATABASE_URL to run the same suite against PostgreSQL instead (the database must
exist and be empty; tables are dropped again after each test).
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.roles import Role
from app.auth.users import create_user
from app.core.config import Settings
from app.db.session import make_engine
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
FROZEN_NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)
TEST_JWT_SECRET = "test-secret-" + "x" * 40
PASSWORD = "correct-horse-battery"
Headers = dict[str, str]


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False  # keep pytest's logging setup
    return config


@pytest.fixture
def database_url(tmp_path: Path) -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    yield url
    command.downgrade(config, "base")


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        cors_origins=["http://test"],
        simulator_enabled=False,  # tests drive the simulator explicitly
        jwt_secret=TEST_JWT_SECRET,
        bcrypt_rounds=4,  # fast hashing in tests
    )


@pytest.fixture
def users(engine: Engine) -> dict[Role, int]:
    """One user per role; the username is the role name, the password is PASSWORD."""
    ids = {}
    with Session(engine) as session, session.begin():
        for role in Role:
            ids[role] = create_user(session, role.value, PASSWORD, role, rounds=4).id
    return ids


def login(client: TestClient, username: str, password: str = PASSWORD) -> Headers:
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def access_token(headers: Headers) -> str:
    return headers["Authorization"].removeprefix("Bearer ")


def build_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings, clock=lambda: FROZEN_NOW)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    yield from build_client(app)


@pytest.fixture
def as_viewer(client: TestClient, users: dict[Role, int]) -> Headers:
    return login(client, "viewer")


@pytest.fixture
def as_operator(client: TestClient, users: dict[Role, int]) -> Headers:
    return login(client, "operator")


@pytest.fixture
def as_supervisor(client: TestClient, users: dict[Role, int]) -> Headers:
    return login(client, "supervisor")


@pytest.fixture
def live_client(settings: Settings, users: dict[Role, int]) -> Iterator[TestClient]:
    """App with the 10 Hz simulator loop actually running (real clock)."""
    app = create_app(settings.model_copy(update={"simulator_enabled": True}))
    yield from build_client(app)
