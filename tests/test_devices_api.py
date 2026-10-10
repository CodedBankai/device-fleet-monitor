import pytest


def test_register_device_success(client, register):
    response = register()

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "device-01"
    assert body["name"] == "Lab Device 01"
    assert body["status"] == "OFFLINE"  # no heartbeat yet
    assert body["last_heartbeat"] is None


def test_register_duplicate_returns_409_and_keeps_original(client, register):
    register(name="Original Name")

    response = register(name="Different Name")

    assert response.status_code == 409
    assert client.get("/devices/device-01").json()["name"] == "Original Name"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "device-01"},
        {"name": "No Id"},
        {"id": "", "name": "Empty id"},
        {"id": "   ", "name": "Blank id"},
    ],
)
def test_register_missing_or_blank_fields_returns_422(client, payload):
    response = client.post("/devices", json=payload)

    assert response.status_code == 422
    assert client.get("/devices").json() == []  # nothing got registered


def test_register_malformed_json_returns_400(client):
    response = client.post(
        "/devices",
        content='{"id": "device-01", ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_get_unknown_device_returns_404(client):
    assert client.get("/devices/does-not-exist").status_code == 404