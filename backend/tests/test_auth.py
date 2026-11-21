"""Login, refresh, token validation and revocation."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from app.auth.passwords import PasswordPolicyError, hash_password, verify_password
from app.auth.roles import Role
from app.auth.tokens import create_token
from app.auth.users import UserExistsError, create_user
from app.cli import main as cli_main
from app.core.config import Settings
from app.db.models import User
from tests.conftest import PASSWORD, TEST_JWT_SECRET, login


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post_login(client: TestClient, username: str, password: str) -> dict[str, object]:
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    return {"status": response.status_code, **response.json()}


# --- Login --------------------------------------------------------------------------------


def test_login_returns_working_token_pair(client: TestClient, users: dict[Role, int]) -> None:
    response = client.post("/api/auth/login", data={"username": "operator", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    me = client.get("/api/auth/me", headers=bearer(body["access_token"])).json()
    assert me == {"id": users[Role.OPERATOR], "username": "operator", "role": "operator"}


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("operator", "wrong-password"),  # wrong password
        ("nobody", PASSWORD),  # unknown user
        ("operator", "x" * 100),  # longer than bcrypt's 72-byte limit: no 500
        ("operator", ""),
    ],
)
def test_bad_credentials_get_the_same_401(
    client: TestClient, users: dict[Role, int], username: str, password: str
) -> None:
    result = post_login(client, username, password)

    assert result["status"] in (401, 422)  # 422 only for the empty form field
    if result["status"] == 401:
        assert result["detail"] == "Incorrect username or password"


def test_disabled_user_cannot_log_in(
    client: TestClient, users: dict[Role, int], engine: Engine
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(update(User).where(User.username == "operator").values(is_active=False))

    result = post_login(client, "operator", PASSWORD)

    assert result["status"] == 401
    assert result["detail"] == "Incorrect username or password"


# --- Refresh ------------------------------------------------------------------------------


def test_refresh_returns_a_new_working_pair(client: TestClient, users: dict[Role, int]) -> None:
    tokens = client.post(
        "/api/auth/login", data={"username": "viewer", "password": PASSWORD}
    ).json()

    response = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    new = response.json()
    assert new["access_token"] != tokens["access_token"]
    assert client.get("/api/auth/me", headers=bearer(new["access_token"])).status_code == 200


def test_access_token_is_not_accepted_as_refresh_token(
    client: TestClient, users: dict[Role, int]
) -> None:
    tokens = client.post(
        "/api/auth/login", data={"username": "viewer", "password": PASSWORD}
    ).json()

    response = client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})

    assert response.status_code == 401


def test_refresh_token_is_not_accepted_as_access_token(
    client: TestClient, users: dict[Role, int]
) -> None:
    tokens = client.post(
        "/api/auth/login", data={"username": "viewer", "password": PASSWORD}
    ).json()

    assert client.get("/api/auth/me", headers=bearer(tokens["refresh_token"])).status_code == 401


# --- Token validation ---------------------------------------------------------------------


def test_expired_token_is_rejected(
    client: TestClient, users: dict[Role, int], settings: Settings
) -> None:
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    token = create_token(
        settings,
        user_id=users[Role.SUPERVISOR],
        token_version=0,
        token_type="access",
        now=an_hour_ago,
    )

    response = client.get("/api/auth/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_token_signed_with_another_secret_is_rejected(
    client: TestClient, users: dict[Role, int], settings: Settings
) -> None:
    forged_settings = settings.model_copy(update={"jwt_secret": "attacker-" + "y" * 40})
    token = create_token(
        forged_settings, user_id=users[Role.SUPERVISOR], token_version=0, token_type="access"
    )

    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_unsigned_alg_none_token_is_rejected(client: TestClient, users: dict[Role, int]) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(users[Role.SUPERVISOR]),
            "ver": 0,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        key=None,
        algorithm="none",
    )

    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_token_for_deleted_user_id_is_rejected(client: TestClient, settings: Settings) -> None:
    token = create_token(settings, user_id=9999, token_version=0, token_type="access")

    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


# --- Revocation and live role changes ------------------------------------------------------


def test_bumping_token_version_revokes_existing_tokens(
    client: TestClient, users: dict[Role, int], engine: Engine
) -> None:
    headers = login(client, "operator")
    with Session(engine) as session, session.begin():
        session.execute(update(User).where(User.username == "operator").values(token_version=1))

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/auth/me", headers=login(client, "operator")).status_code == 200


def test_deactivation_takes_effect_on_the_next_request(
    client: TestClient, users: dict[Role, int], engine: Engine
) -> None:
    headers = login(client, "operator")
    with Session(engine) as session, session.begin():
        session.execute(update(User).where(User.username == "operator").values(is_active=False))

    assert client.get("/api/alarms", headers=headers).status_code == 401


def test_role_comes_from_the_database_not_the_token(
    client: TestClient, users: dict[Role, int], engine: Engine
) -> None:
    headers = login(client, "operator")
    assert client.post("/api/reactor/scram", headers=headers).status_code != 403
    client.app.state.runner.reactor.reset_scram()  # type: ignore[attr-defined]

    with Session(engine) as session, session.begin():
        session.execute(update(User).where(User.username == "operator").values(role="viewer"))

    # Same token, but the user is now a viewer: denied immediately.
    assert client.post("/api/reactor/scram", headers=headers).status_code == 403


# --- Passwords, user creation, CLI and settings --------------------------------------------


def test_passwords_are_hashed_with_bcrypt(engine: Engine, users: dict[Role, int]) -> None:
    with Session(engine) as session:
        user = session.get(User, users[Role.VIEWER])
        assert user is not None
        assert user.password_hash.startswith("$2b$")
        assert PASSWORD not in user.password_hash
        assert verify_password(PASSWORD, user.password_hash)


@pytest.mark.parametrize("password", ["short", "é" * 37])  # too short; 74 bytes
def test_password_policy(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        hash_password(password, rounds=4)


def test_usernames_are_unique(engine: Engine, users: dict[Role, int]) -> None:
    with Session(engine) as session, pytest.raises(UserExistsError):
        create_user(session, "viewer", PASSWORD, Role.VIEWER, rounds=4)


def test_cli_creates_a_user_that_can_log_in(
    client: TestClient,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import io

    from app.core import config

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    monkeypatch.setattr("sys.stdin", io.StringIO("cli-password-123\n"))
    config.get_settings.cache_clear()
    try:
        code = cli_main(
            ["create-user", "--username", "alice", "--role", "supervisor", "--password-stdin"]
        )
    finally:
        config.get_settings.cache_clear()

    assert code == 0
    assert "Created supervisor 'alice'" in capsys.readouterr().out
    assert login(client, "alice", "cli-password-123")


def test_production_refuses_the_default_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret="change-me")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production")  # built-in dev secret

    Settings(_env_file=None, environment="production", jwt_secret=TEST_JWT_SECRET)


def run_seed(monkeypatch: pytest.MonkeyPatch, database_url: str, **env: str) -> int:
    from app.core import config

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    try:
        return cli_main(["seed-demo"])
    finally:
        config.get_settings.cache_clear()


def test_seed_demo_creates_one_user_per_role_and_is_idempotent(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {"SEED_DEMO_USERS": "true", "ENVIRONMENT": "development"}

    assert run_seed(monkeypatch, database_url, **env) == 0
    assert run_seed(monkeypatch, database_url, **env) == 0  # second start: no duplicates

    for role in Role:
        headers = login(client, role.value, f"{role.value}-demo")
        assert client.get("/api/auth/me", headers=headers).json()["role"] == role.value


def test_seed_demo_does_nothing_unless_enabled(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_seed(monkeypatch, database_url, ENVIRONMENT="development") == 0

    response = client.post(
        "/api/auth/login", data={"username": "operator", "password": "operator-demo"}
    )
    assert response.status_code == 401


def test_seed_demo_refuses_outside_development(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = run_seed(
        monkeypatch,
        database_url,
        SEED_DEMO_USERS="true",
        ENVIRONMENT="production",
        JWT_SECRET=TEST_JWT_SECRET,
    )

    assert code == 1
    response = client.post(
        "/api/auth/login", data={"username": "operator", "password": "operator-demo"}
    )
    assert response.status_code == 401
