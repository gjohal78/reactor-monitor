"""Alarm API, persistence and WebSocket broadcast, through the real app."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.alarms.service import AlarmService
from app.alarms.states import AlarmState
from app.core.config import Settings
from app.db.models import Alarm
from app.main import create_app
from app.sim.reactor import ReactorState
from tests.alarm_helpers import HIGH_POWER_STATE, NORMAL_STATE, make_state
from tests.conftest import FROZEN_NOW, Headers, login


@pytest.fixture(autouse=True)
def _authenticated(client: TestClient, as_operator: Headers) -> None:
    """Acknowledging needs the operator role; these tests run as an operator."""
    client.headers.update(as_operator)


def service(client: TestClient) -> AlarmService:
    alarms: AlarmService = client.app.state.alarms  # type: ignore[attr-defined]
    return alarms


def feed(client: TestClient, state: ReactorState) -> None:
    """Run one alarm evaluation on the app's event loop and wait for the DB write."""
    assert client.portal is not None
    client.portal.call(service(client).evaluate, state, FROZEN_NOW)
    client.portal.call(service(client).drain)


def raise_hi_power(client: TestClient) -> str:
    feed(client, HIGH_POWER_STATE)
    alarm_id: str = client.get("/api/alarms").json()[0]["id"]
    return alarm_id


def db_row(engine: Engine, alarm_id: str) -> Alarm:
    with Session(engine) as session:
        row = session.get(Alarm, uuid.UUID(alarm_id))
        assert row is not None
        return row


def test_no_open_alarms_at_steady_state(client: TestClient) -> None:
    assert client.get("/api/alarms").json() == []


def test_new_alarm_is_listed_and_stored(client: TestClient, engine: Engine) -> None:
    alarm_id = raise_hi_power(client)

    (alarm,) = client.get("/api/alarms").json()
    assert alarm["code"] == "HI_POWER"
    assert alarm["state"] == "ACTIVE_UNACKED"
    assert db_row(engine, alarm_id).state == "ACTIVE_UNACKED"


def test_ack_active_alarm(client: TestClient, engine: Engine) -> None:
    alarm_id = raise_hi_power(client)

    response = client.post(f"/api/alarms/{alarm_id}/ack")

    assert response.status_code == 200
    assert response.json()["state"] == "ACTIVE_ACKED"
    assert response.json()["acknowledged_at"] == "2026-11-18T12:00:00Z"
    row = db_row(engine, alarm_id)
    assert (row.state, row.acknowledged_at) == ("ACTIVE_ACKED", FROZEN_NOW)


def test_ack_cleared_alarm_returns_it_to_normal(client: TestClient, engine: Engine) -> None:
    alarm_id = raise_hi_power(client)
    feed(client, NORMAL_STATE)
    assert client.get("/api/alarms").json()[0]["state"] == "CLEARED_UNACKED"

    response = client.post(f"/api/alarms/{alarm_id}/ack")

    assert response.json()["state"] == "NORMAL"
    assert client.get("/api/alarms").json() == []
    assert db_row(engine, alarm_id).closed_at == FROZEN_NOW


def test_ack_twice_is_conflict(client: TestClient) -> None:
    alarm_id = raise_hi_power(client)
    client.post(f"/api/alarms/{alarm_id}/ack")

    response = client.post(f"/api/alarms/{alarm_id}/ack")

    assert response.status_code == 409
    assert "ACTIVE_ACKED" in response.json()["detail"]


def test_ack_alarm_already_back_to_normal_is_conflict(client: TestClient) -> None:
    alarm_id = raise_hi_power(client)
    client.post(f"/api/alarms/{alarm_id}/ack")
    feed(client, NORMAL_STATE)  # acked + cleared -> NORMAL

    response = client.post(f"/api/alarms/{alarm_id}/ack")

    assert response.status_code == 409
    assert "NORMAL" in response.json()["detail"]


def test_ack_unknown_alarm_is_404(client: TestClient) -> None:
    assert client.post(f"/api/alarms/{uuid.uuid4()}/ack").status_code == 404


def test_ack_malformed_id_is_422(client: TestClient) -> None:
    assert client.post("/api/alarms/not-a-uuid/ack").status_code == 422


def test_alarm_changes_are_broadcast_over_websocket(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
        assert ws.receive_json() == {"type": "alarm_snapshot", "data": []}

        feed(client, HIGH_POWER_STATE)
        raised: dict[str, Any] = ws.receive_json()
        client.post(f"/api/alarms/{raised['data']['id']}/ack")
        acked: dict[str, Any] = ws.receive_json()

    assert raised["type"] == "alarm"
    assert raised["data"]["code"] == "HI_POWER"
    assert (raised["data"]["previous_state"], raised["data"]["state"]) == (
        "NORMAL",
        "ACTIVE_UNACKED",
    )
    assert raised["data"]["event"] == "CONDITION_ACTIVE"
    assert (acked["data"]["previous_state"], acked["data"]["state"]) == (
        "ACTIVE_UNACKED",
        "ACTIVE_ACKED",
    )
    assert acked["data"]["event"] == "ACK"


def test_websocket_snapshot_lists_open_alarms(client: TestClient) -> None:
    alarm_id = raise_hi_power(client)
    token = client.headers["Authorization"].removeprefix("Bearer ")

    with client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
        snapshot = ws.receive_json()

    assert snapshot["type"] == "alarm_snapshot"
    assert [a["id"] for a in snapshot["data"]] == [alarm_id]


def test_open_alarms_survive_a_restart(client: TestClient, settings: Settings) -> None:
    alarm_id = raise_hi_power(client)

    restarted = create_app(settings, clock=lambda: FROZEN_NOW)
    with TestClient(restarted) as new_client:
        new_client.headers.update(login(new_client, "operator"))
        (alarm,) = new_client.get("/api/alarms").json()
        assert (alarm["id"], alarm["state"]) == (alarm_id, AlarmState.ACTIVE_UNACKED)

        feed(new_client, NORMAL_STATE)
        assert new_client.get("/api/alarms").json()[0]["state"] == "CLEARED_UNACKED"
        assert new_client.post(f"/api/alarms/{alarm_id}/ack").json()["state"] == "NORMAL"


def test_alarm_limits_come_from_settings(settings: Settings, users: object) -> None:
    custom = settings.model_copy(update={"alarm_hi_power_percent": 100.5})

    with TestClient(create_app(custom, clock=lambda: FROZEN_NOW)) as client:
        client.headers.update(login(client, "viewer"))
        feed(client, make_state(power=101.0))
        (alarm,) = client.get("/api/alarms").json()

    assert (alarm["code"], alarm["limit"]) == ("HI_POWER", 100.5)
