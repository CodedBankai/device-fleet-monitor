import pytest


def test_heartbeat_on_registered_device(client, register, send_heartbeat):
    register()

    response = send_heartbeat()

    assert response.status_code == 200
    assert response.json() == {
        "device_id": "device-01",
        "status": "ONLINE",
        "payload_applied": True,
    }
    device = client.get("/devices/device-01").json()
    assert device["status"] == "ONLINE"
    assert device["last_heartbeat"] is not None
    assert device["payload_status"] == "OK"


def test_heartbeat_on_unknown_device_returns_404(send_heartbeat):
    response = send_heartbeat(device_id="ghost")

    assert response.status_code == 404


def test_heartbeat_malformed_json_returns_400(client, register):
    register()

    response = client.post(
        "/devices/device-01/heartbeat",
        content='{"timestamp": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"timestamp": "not-a-date", "status": "OK"},
        {"timestamp": "2026-10-10T12:00:00Z"},
        {"timestamp": "2026-10-10T12:00:00Z", "status": ""},
    ],
)
def test_heartbeat_invalid_payload_returns_422(client, register, payload):
    register()

    response = client.post("/devices/device-01/heartbeat", json=payload)

    assert response.status_code == 422
    # A rejected heartbeat must not make the device look alive.
    assert client.get("/devices/device-01").json()["status"] == "OFFLINE"


def test_heartbeat_extra_metrics_are_stored(client, register, send_heartbeat):
    register()

    send_heartbeat(cpu_usage=42, signal_strength=-71)

    metrics = client.get("/devices/device-01").json()["metrics"]
    assert metrics == {"cpu_usage": 42, "signal_strength": -71}