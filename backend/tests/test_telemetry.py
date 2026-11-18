import time

from fastapi.testclient import TestClient


def test_websocket_streams_live_telemetry(live_client: TestClient) -> None:
    with live_client.websocket_connect("/ws/telemetry") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert set(first) == {
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
    # Steady full-power start, and the stream is live: each message is one 0.1 s step.
    assert first["power_percent"] == 100.0
    assert first["scrammed"] is False
    assert round(second["sim_time_s"] - first["sim_time_s"], 6) == 0.1


def test_disconnected_clients_are_unsubscribed(live_client: TestClient) -> None:
    hub = live_client.app.state.hub  # type: ignore[attr-defined]

    with live_client.websocket_connect("/ws/telemetry") as ws:
        ws.receive_json()
        assert hub.subscriber_count == 1

    deadline = time.monotonic() + 2.0
    while hub.subscriber_count and time.monotonic() < deadline:
        time.sleep(0.01)
    assert hub.subscriber_count == 0
