import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Settings


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "reactor-monitor",
        "version": __version__,
        "environment": "test",
    }


def test_health_allows_configured_cors_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://test"})

    assert response.headers["access-control-allow-origin"] == "http://test"


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example")

    assert Settings(_env_file=None).cors_origins == ["http://a.example", "http://b.example"]
