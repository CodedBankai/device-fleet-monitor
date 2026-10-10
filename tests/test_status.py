from datetime import datetime, timedelta, timezone

import pytest

from src.models import ConnectivityStatus, Device
from src.status import calculate_status

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


def make_device(age_seconds=None, payload_status=None) -> Device:
    device = Device(id="d1", name="Device 1", registered_at=NOW - timedelta(hours=1))
    if age_seconds is not None:
        device.last_seen_server_time = NOW - timedelta(seconds=age_seconds)
    device.payload_status = payload_status
    return device


def test_device_with_no_heartbeats_is_offline():
    assert calculate_status(make_device(), NOW) == ConnectivityStatus.OFFLINE


@pytest.mark.parametrize(
    "age, expected",
    [
        (0, ConnectivityStatus.ONLINE),
        (29, ConnectivityStatus.ONLINE),
        (30, ConnectivityStatus.ONLINE),  # boundary is inclusive
        (30.001, ConnectivityStatus.OFFLINE),
        (31, ConnectivityStatus.OFFLINE),
        (3600, ConnectivityStatus.OFFLINE),
    ],
)
def test_timeout_boundaries(age, expected):
    assert calculate_status(make_device(age), NOW) == expected


def test_error_payload_status_does_not_affect_connectivity():
    device = make_device(age_seconds=5, payload_status="ERROR")
    assert calculate_status(device, NOW) == ConnectivityStatus.ONLINE


def test_heartbeat_slightly_in_the_future_counts_as_online():
    # A heartbeat can land right after reference_now was captured.
    assert calculate_status(make_device(age_seconds=-0.5), NOW) == ConnectivityStatus.ONLINE


def test_custom_timeout_is_respected():
    assert calculate_status(make_device(10), NOW, timeout_seconds=5) == ConnectivityStatus.OFFLINE