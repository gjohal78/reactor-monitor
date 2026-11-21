"""What each role can actually do, and the audit trail each action leaves."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.roles import Role
from app.sim.reactor import Reactor
from tests.alarm_helpers import HIGH_POWER_STATE, make_state
from tests.conftest import FROZEN_NOW, Headers
from tests.test_roles import VALID_LIMITS


def reactor_of(client: TestClient) -> Reactor:
    reactor: Reactor = client.app.state.runner.reactor  # type: ignore[attr-defined]
    return reactor


def audit(client: TestClient, as_supervisor: Headers, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/audit", params=params, headers=as_supervisor)
    assert response.status_code == 200
    entries: list[dict[str, Any]] = response.json()
    return entries


def raise_alarm(client: TestClient, state: Any = HIGH_POWER_STATE) -> str:
    service = client.app.state.alarms  # type: ignore[attr-defined]
    assert client.portal is not None
    client.portal.call(service.evaluate, state, FROZEN_NOW)
    client.portal.call(service.drain)
    return str(service.manager.open_alarms[0].id)


# --- Operator: rods -----------------------------------------------------------------------


def test_operator_moves_rods_within_envelope_and_it_is_audited(
    client: TestClient, as_operator: Headers, as_supervisor: Headers
) -> None:
    response = client.post("/api/reactor/rods", json={"target_percent": 17.5}, headers=as_operator)

    assert response.status_code == 200
    assert response.json()["rod_target_percent"] == 17.5
    assert reactor_of(client).state.rod_target_percent == 17.5
    (entry,) = audit(client, as_supervisor, action="ROD_MOVE")
    assert entry["username"] == "operator"
    assert entry["role"] == "operator"
    assert entry["success"] is True
    assert entry["old_value"]["rod_target_percent"] == 20.0
    assert entry["new_value"] == {"rod_target_percent": 17.5}
    assert entry["timestamp"] == "2026-11-18T12:00:00Z"
    assert entry["client_ip"] == "testclient"


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (14.0, "withdraw rods at most 5.0 %"),  # 6 % withdrawal in one command
        (9.0, "minimum insertion of 10.0 %"),  # below the envelope
    ],
)
def test_rod_commands_outside_envelope_are_rejected_and_audited(
    client: TestClient, as_operator: Headers, as_supervisor: Headers, target: float, reason: str
) -> None:
    if target == 9.0:  # walk the target down to 12 % first, within the step limit
        for step in (15.0, 12.0):
            client.post("/api/reactor/rods", json={"target_percent": step}, headers=as_operator)

    response = client.post(
        "/api/reactor/rods", json={"target_percent": target}, headers=as_operator
    )

    assert response.status_code == 422
    assert reason in response.json()["detail"]
    assert reactor_of(client).state.rod_target_percent != target
    failed = [e for e in audit(client, as_supervisor, action="ROD_MOVE") if not e["success"]]
    assert failed[0]["new_value"] == {"rod_target_percent": target}
    assert reason in failed[0]["detail"]


def test_inserting_rods_is_never_step_limited(client: TestClient, as_operator: Headers) -> None:
    response = client.post("/api/reactor/rods", json={"target_percent": 90.0}, headers=as_operator)

    assert response.status_code == 200


def test_supervisor_is_held_to_the_same_rod_envelope(
    client: TestClient, as_supervisor: Headers
) -> None:
    response = client.post(
        "/api/reactor/rods", json={"target_percent": 10.0}, headers=as_supervisor
    )

    assert response.status_code == 422


@pytest.mark.parametrize("target", [-1, 100.5, "abc"])
def test_rod_target_must_be_a_percentage(
    client: TestClient, as_operator: Headers, target: object
) -> None:
    response = client.post(
        "/api/reactor/rods", json={"target_percent": target}, headers=as_operator
    )

    assert response.status_code == 422


# --- Scram and reset ------------------------------------------------------------------------


def test_scram_and_reset_lifecycle(
    client: TestClient, as_operator: Headers, as_supervisor: Headers
) -> None:
    reactor = reactor_of(client)

    # Operator scrams.
    response = client.post("/api/reactor/scram", headers=as_operator)
    assert response.status_code == 200
    assert response.json()["scrammed"] is True
    # Second scram is a conflict, and rods can't be moved while scrammed.
    assert client.post("/api/reactor/scram", headers=as_operator).status_code == 409
    rods = client.post("/api/reactor/rods", json={"target_percent": 95}, headers=as_operator)
    assert rods.status_code == 409
    # Operator may not reset.
    assert client.post("/api/reactor/reset-scram", headers=as_operator).status_code == 403
    # Supervisor may, but only once the rods are fully in.
    early = client.post("/api/reactor/reset-scram", headers=as_supervisor)
    assert early.status_code == 409
    assert "still inserting" in early.json()["detail"]
    reactor.step(3.0)  # rods reach 100 % (scram speed 50 %/s)
    reset = client.post("/api/reactor/reset-scram", headers=as_supervisor)
    assert reset.status_code == 200
    assert reset.json() == {
        "rod_target_percent": 100.0,
        "rod_position_percent": 100.0,
        "scrammed": False,
    }
    # After reset the operator can move rods again.
    assert (
        client.post(
            "/api/reactor/rods", json={"target_percent": 96}, headers=as_operator
        ).status_code
        == 200
    )

    scrams = audit(client, as_supervisor, action="SCRAM")
    assert [(e["username"], e["success"]) for e in scrams] == [
        ("operator", False),  # newest first: the rejected second scram
        ("operator", True),
    ]
    assert scrams[1]["old_value"]["scrammed"] is False
    assert scrams[1]["new_value"] == {"scrammed": True, "rod_target_percent": 100.0}
    resets = audit(client, as_supervisor, action="SCRAM_RESET")
    assert [(e["username"], e["success"]) for e in resets] == [
        ("supervisor", True),
        ("supervisor", False),
    ]
    assert resets[0]["old_value"]["scrammed"] is True
    assert resets[0]["new_value"] == {"scrammed": False}


def test_reset_without_scram_is_conflict(client: TestClient, as_supervisor: Headers) -> None:
    response = client.post("/api/reactor/reset-scram", headers=as_supervisor)

    assert response.status_code == 409


# --- Alarms ---------------------------------------------------------------------------------


def test_operator_ack_is_audited_with_old_and_new_state(
    client: TestClient, as_operator: Headers, as_supervisor: Headers
) -> None:
    alarm_id = raise_alarm(client)

    assert client.post(f"/api/alarms/{alarm_id}/ack", headers=as_operator).status_code == 200
    assert client.post(f"/api/alarms/{alarm_id}/ack", headers=as_operator).status_code == 409

    entries = audit(client, as_supervisor, action="ALARM_ACK")
    assert entries[1]["target"] == alarm_id
    assert entries[1]["old_value"] == {"state": "ACTIVE_UNACKED"}
    assert entries[1]["new_value"] == {"state": "ACTIVE_ACKED"}
    assert entries[1]["detail"] == "HI_POWER"
    assert entries[0]["success"] is False  # the second, conflicting ack


def test_viewer_cannot_acknowledge(client: TestClient, as_viewer: Headers) -> None:
    alarm_id = raise_alarm(client)

    assert client.post(f"/api/alarms/{alarm_id}/ack", headers=as_viewer).status_code == 403
    assert client.get("/api/alarms", headers=as_viewer).json()[0]["state"] == "ACTIVE_UNACKED"


def test_supervisor_changes_alarm_limits_and_they_take_effect(
    client: TestClient, as_supervisor: Headers, as_viewer: Headers
) -> None:
    new_limits = {**VALID_LIMITS, "hi_power_percent": 100.5}

    response = client.put("/api/alarms/limits", json=new_limits, headers=as_supervisor)

    assert response.status_code == 200
    assert client.get("/api/alarms/limits", headers=as_viewer).json() == new_limits
    raise_alarm(client, make_state(power=101.0))  # would not alarm at the old 105 %
    (alarm,) = client.get("/api/alarms", headers=as_viewer).json()
    assert (alarm["code"], alarm["limit"]) == ("HI_POWER", 100.5)

    (entry,) = audit(client, as_supervisor, action="ALARM_LIMITS_CHANGE")
    assert entry["old_value"]["hi_power_percent"] == 105.0
    assert entry["new_value"]["hi_power_percent"] == 100.5
    assert entry["username"] == "supervisor"


def test_operator_cannot_change_alarm_limits(
    client: TestClient, as_operator: Headers, as_supervisor: Headers
) -> None:
    response = client.put("/api/alarms/limits", json=VALID_LIMITS, headers=as_operator)

    assert response.status_code == 403
    # The attempt is on record, as ACCESS_DENIED rather than a limits change...
    (denied,) = audit(client, as_supervisor, action="ACCESS_DENIED")
    assert denied["username"] == "operator"
    assert denied["role"] == "operator"
    assert denied["success"] is False
    assert denied["target"] == "PUT /api/alarms/limits"
    assert denied["detail"] == "Requires the supervisor role or higher"
    assert denied["timestamp"] == "2026-11-18T12:00:00Z"
    assert denied["client_ip"] == "testclient"
    # ...and the limits did not change.
    assert audit(client, as_supervisor, action="ALARM_LIMITS_CHANGE") == []
    limits = client.get("/api/alarms/limits", headers=as_operator).json()
    assert limits["hi_power_percent"] == 105.0


@pytest.mark.parametrize(
    "change", [{"hi_power_deadband": -1}, {"short_period_s": 0}, {"hi_temp_c": "hot"}]
)
def test_invalid_alarm_limits_are_rejected(
    client: TestClient, as_supervisor: Headers, change: dict[str, Any]
) -> None:
    response = client.put(
        "/api/alarms/limits", json={**VALID_LIMITS, **change}, headers=as_supervisor
    )

    assert response.status_code == 422


def test_users_fixture_has_one_user_per_role(users: dict[Role, int]) -> None:
    assert set(users) == set(Role)
