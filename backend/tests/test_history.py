from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import Reading
from tests.conftest import FROZEN_NOW


def add_reading(engine: Engine, minutes_ago: float, power: float = 100.0) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            Reading(
                timestamp=FROZEN_NOW - timedelta(minutes=minutes_ago),
                sim_time_s=1000.0 - minutes_ago * 60,
                power_percent=power,
                coolant_temp_c=310.0,
                rod_position_percent=20.0,
                rod_target_percent=20.0,
                reactor_period_s=None,
                reactivity_pcm=0.0,
                scrammed=False,
            )
        )


def test_history_empty(client: TestClient) -> None:
    response = client.get("/api/history")

    assert response.status_code == 200
    assert response.json() == {"minutes": 15, "count": 0, "readings": []}


def test_history_defaults_to_last_15_minutes_oldest_first(
    client: TestClient, engine: Engine
) -> None:
    # Inserted out of order on purpose; 20 min ago is outside the default window.
    add_reading(engine, minutes_ago=5, power=105.0)
    add_reading(engine, minutes_ago=20, power=90.0)
    add_reading(engine, minutes_ago=14.9, power=101.0)
    add_reading(engine, minutes_ago=0, power=110.0)

    body = client.get("/api/history").json()

    assert body["count"] == 3
    assert [r["power_percent"] for r in body["readings"]] == [101.0, 105.0, 110.0]


def test_history_respects_minutes_parameter(client: TestClient, engine: Engine) -> None:
    add_reading(engine, minutes_ago=0.5)
    add_reading(engine, minutes_ago=3)
    add_reading(engine, minutes_ago=30)

    assert client.get("/api/history?minutes=1").json()["count"] == 1
    assert client.get("/api/history?minutes=60").json()["count"] == 3


def test_history_window_boundary_is_inclusive(client: TestClient, engine: Engine) -> None:
    add_reading(engine, minutes_ago=15)

    assert client.get("/api/history?minutes=15").json()["count"] == 1


def test_history_reading_shape(client: TestClient, engine: Engine) -> None:
    add_reading(engine, minutes_ago=1)

    reading = client.get("/api/history").json()["readings"][0]

    assert set(reading) == {
        "id",
        "timestamp",
        "sim_time_s",
        "power_percent",
        "coolant_temp_c",
        "rod_position_percent",
        "rod_target_percent",
        "reactor_period_s",
        "reactivity_pcm",
        "scrammed",
    }
    assert reading["timestamp"] == "2026-11-18T11:59:00Z"
    assert reading["reactor_period_s"] is None


@pytest.mark.parametrize("minutes", ["0", "-5", "1441", "abc"])
def test_history_rejects_invalid_minutes(client: TestClient, minutes: str) -> None:
    response = client.get(f"/api/history?minutes={minutes}")

    assert response.status_code == 422
