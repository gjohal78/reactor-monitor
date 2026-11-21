"""Audit log: login entries, querying, and append-only enforcement in the database."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.audit.log import AuditAction, write_audit
from app.auth.roles import Role
from app.db.models import AuditLog
from tests.conftest import PASSWORD, Headers, login


def test_successful_and_failed_logins_are_audited(
    client: TestClient, users: dict[Role, int]
) -> None:
    client.post("/api/auth/login", data={"username": "operator", "password": "nope"})
    client.post("/api/auth/login", data={"username": "ghost", "password": PASSWORD})
    supervisor = login(client, "supervisor")

    entries = client.get("/api/audit", params={"action": "LOGIN"}, headers=supervisor).json()

    assert [(e["username"], e["success"], e["detail"]) for e in entries] == [
        ("supervisor", True, None),  # newest first
        ("ghost", False, "unknown user"),
        ("operator", False, "wrong password"),
    ]
    assert entries[0]["user_id"] == users[Role.SUPERVISOR]
    assert entries[0]["role"] == "supervisor"
    assert entries[1]["user_id"] is None  # unknown user has no id
    assert all(e["client_ip"] == "testclient" for e in entries)


def test_audit_filters_and_paging(client: TestClient, as_supervisor: Headers) -> None:
    for name in ("viewer", "operator", "viewer"):
        login(client, name)

    by_user = client.get("/api/audit", params={"username": "viewer"}, headers=as_supervisor).json()
    page = client.get("/api/audit", params={"limit": 2, "offset": 1}, headers=as_supervisor).json()
    everything = client.get("/api/audit", headers=as_supervisor).json()

    assert len(by_user) == 2
    assert all(e["username"] == "viewer" for e in by_user)
    assert [e["id"] for e in page] == [e["id"] for e in everything[1:3]]
    assert [e["id"] for e in everything] == sorted((e["id"] for e in everything), reverse=True)


def test_audit_rejects_unknown_action_filter(client: TestClient, as_supervisor: Headers) -> None:
    response = client.get("/api/audit", params={"action": "HACK"}, headers=as_supervisor)

    assert response.status_code == 422


def add_entry(engine: Engine) -> int:
    with Session(engine) as session, session.begin():
        entry = write_audit(
            session,
            timestamp=datetime.now(UTC),
            action=AuditAction.SCRAM,
            user=None,
            username="someone",
        )
        session.flush()
        return entry.id


def test_database_rejects_updating_audit_entries(engine: Engine) -> None:
    entry_id = add_entry(engine)

    with pytest.raises(DBAPIError, match="append-only"), Session(engine) as session:
        session.execute(update(AuditLog).where(AuditLog.id == entry_id).values(username="x"))
        session.commit()


def test_database_rejects_deleting_audit_entries(engine: Engine) -> None:
    entry_id = add_entry(engine)

    with pytest.raises(DBAPIError, match="append-only"), Session(engine) as session:
        session.execute(delete(AuditLog).where(AuditLog.id == entry_id))
        session.commit()

    with Session(engine) as session:
        assert session.get(AuditLog, entry_id) is not None


def test_database_rejects_truncate_on_postgres(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("TRUNCATE is Postgres-only")
    add_entry(engine)

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("TRUNCATE audit_log"))
