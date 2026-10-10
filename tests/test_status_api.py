from datetime import datetime, timedelta

import pytest


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def get_summary(client) -> dict:
    """Fetch /summary and check the core invariant on every single call."""
    body = client.get("/summary").json()
    assert body["total"] == body["online"] + body["offline"]
    return body


@pytest.mark.parametrize(
    "age_seconds, expected",
    [
        (29, "ONLINE"),
        (30, "ONLINE"),  # exactly 30s is still ONLINE (inclusive)
        (31, "OFFLINE"),
    ],
)
def test_timeout_boundary(client, clock, register, send_heartbeat, age_seconds, expected):
    register()
    send_heartbeat()
    clock.advance(age_seconds)

    assert client.get("/devices/device-01").json()["status"] == expected
    assert client.get("/devices").json()[0]["status"] == expected
    assert get_summary(client)["online"] == (1 if expected == "ONLINE" else 0)


def test_device_with_no_heartbeats_is_offline(client, register):
    register()

    device = client.get("/devices/device-01").json()

    assert device["status"] == "OFFLINE"
    assert device["last_heartbeat"] is None
    assert get_summary(client) == {"total": 1, "online": 0, "offline": 1}


def test_summary_invariant_as_devices_go_offline(client, clock, register, send_heartbeat):
    for i in range(5):
        register(f"d{i}", f"Device {i}")

    send_heartbeat("d0")  # t=0
    send_heartbeat("d1")  # t=0
    clock.advance(10)
    send_heartbeat("d2")  # t=10
    clock.advance(10)
    send_heartbeat("d3")  # t=20, d4 never reports

    assert get_summary(client) == {"total": 5, "online": 4, "offline": 1}

    clock.advance(10)  # t=30: d0 and d1 are exactly at the boundary
    assert get_summary(client) == {"total": 5, "online": 4, "offline": 1}

    clock.advance(1)  # t=31: d0 and d1 drop off
    assert get_summary(client) == {"total": 5, "online": 2, "offline": 3}

    clock.advance(10)  # t=41: d2 drops off
    assert get_summary(client) == {"total": 5, "online": 1, "offline": 4}

    clock.advance(10)  # t=51: d3 drops off
    assert get_summary(client) == {"total": 5, "online": 0, "offline": 5}

    send_heartbeat("d0")  # a device coming back
    assert get_summary(client) == {"total": 5, "online": 1, "offline": 4}


def test_error_payload_keeps_device_online(client, register, send_heartbeat):
    register()

    ack = send_heartbeat(status="ERROR")

    assert ack.status_code == 200
    assert ack.json()["status"] == "ONLINE"
    device = client.get("/devices/device-01").json()
    assert device["status"] == "ONLINE"  # connectivity
    assert device["payload_status"] == "ERROR"  # health, reported separately
    assert get_summary(client)["online"] == 1


def test_out_of_order_heartbeat_does_not_overwrite_newer_payload(
    client, clock, register, send_heartbeat
):
    register()
    base = clock.now()
    send_heartbeat(timestamp=base + timedelta(seconds=10), status="OK")
    clock.advance(5)

    # An older heartbeat arrives late.
    ack = send_heartbeat(timestamp=base, status="ERROR")

    assert ack.json()["payload_applied"] is False
    device = client.get("/devices/device-01").json()
    assert device["payload_status"] == "OK"  # newer payload kept
    assert parse(device["last_event_timestamp"]) == base + timedelta(seconds=10)
    # ...but we did hear from the device just now, so last_heartbeat moved forward.
    assert parse(device["last_heartbeat"]) == base + timedelta(seconds=5)


def test_wrong_device_clock_does_not_affect_status(client, clock, register, send_heartbeat):
    register()

    # The device's own clock is a year behind. Only server receipt time matters.
    send_heartbeat(timestamp=clock.now() - timedelta(days=365))

    assert client.get("/devices/device-01").json()["status"] == "ONLINE"