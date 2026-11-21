"""Role matrix: every endpoint x every role (and no login).

"Allowed" means the request got past authorization: not 401 and not 403. The business
result can still be an error (e.g. acking an unknown alarm is 404, resetting a reactor
that isn't scrammed is 409). That's deliberate: it shows the role check passed, without
each case needing setup.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.roles import Role
from tests.conftest import access_token, login

VALID_LIMITS = {
    "hi_power_percent": 106.0,
    "hi_power_deadband": 2.0,
    "hi_temp_c": 314.0,
    "hi_temp_deadband": 1.0,
    "short_period_s": 15.0,
    "short_period_deadband": 5.0,
}

# (method, path, json body, minimum role; None = public)
ENDPOINTS: list[tuple[str, str, dict[str, Any] | None, Role | None]] = [
    ("GET", "/api/health", None, None),
    ("GET", "/api/auth/me", None, Role.VIEWER),
    ("GET", "/api/history", None, Role.VIEWER),
    ("GET", "/api/alarms", None, Role.VIEWER),
    ("GET", "/api/alarms/limits", None, Role.VIEWER),
    ("POST", f"/api/alarms/{uuid.uuid4()}/ack", None, Role.OPERATOR),
    ("POST", "/api/reactor/rods", {"target_percent": 22.0}, Role.OPERATOR),
    ("POST", "/api/reactor/scram", None, Role.OPERATOR),
    ("POST", "/api/reactor/reset-scram", None, Role.SUPERVISOR),
    ("PUT", "/api/alarms/limits", VALID_LIMITS, Role.SUPERVISOR),
    ("GET", "/api/audit", None, Role.SUPERVISOR),
]

CALLERS: list[Role | None] = [None, Role.VIEWER, Role.OPERATOR, Role.SUPERVISOR]


def expected_status_class(caller: Role | None, required: Role | None) -> str:
    if required is None:
        return "allowed"
    if caller is None:
        return "unauthenticated"
    return "allowed" if caller.allows(required) else "forbidden"


@pytest.mark.parametrize(
    ("method", "path", "body", "required"),
    ENDPOINTS,
    ids=[
        f"{m} {p.split('/api/')[1].split('/')[0]}:{p.rsplit('/', 1)[-1]}"
        for m, p, _, _ in ENDPOINTS
    ],
)
@pytest.mark.parametrize("caller", CALLERS, ids=lambda c: c.value if c else "anonymous")
def test_role_matrix(
    client: TestClient,
    users: dict[Role, int],
    caller: Role | None,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    required: Role | None,
) -> None:
    headers = login(client, caller.value) if caller else {}

    response = client.request(method, path, json=body, headers=headers)

    match expected_status_class(caller, required):
        case "unauthenticated":
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
        case "forbidden":
            assert response.status_code == 403
            assert required is not None
            assert required.value in response.json()["detail"]
        case _:
            assert response.status_code not in (401, 403), response.text


def test_forbidden_requests_change_nothing(client: TestClient, users: dict[Role, int]) -> None:
    viewer = login(client, "viewer")
    reactor = client.app.state.runner.reactor  # type: ignore[attr-defined]
    before = reactor.state

    assert client.post("/api/reactor/scram", headers=viewer).status_code == 403
    assert (
        client.post("/api/reactor/rods", json={"target_percent": 15}, headers=viewer).status_code
        == 403
    )
    assert client.put("/api/alarms/limits", json=VALID_LIMITS, headers=viewer).status_code == 403

    assert reactor.state == before
    limits = client.get("/api/alarms/limits", headers=viewer).json()
    assert limits["hi_power_percent"] == 105.0


@pytest.mark.parametrize("role", list(Role))
def test_websocket_accepts_every_role(
    client: TestClient, users: dict[Role, int], role: Role
) -> None:
    token = access_token(login(client, role.value))

    with client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
        assert ws.receive_json()["type"] == "alarm_snapshot"


@pytest.mark.parametrize("query", ["", "?token=", "?token=not-a-jwt"])
def test_websocket_rejects_missing_or_invalid_token(
    client: TestClient, users: dict[Role, int], query: str
) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(f"/ws/telemetry{query}"),
    ):
        pass

    assert excinfo.value.code == 1008


def test_audit_log_has_no_write_routes(client: TestClient, users: dict[Role, int]) -> None:
    supervisor = login(client, "supervisor")

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/audit", headers=supervisor).status_code == 405
