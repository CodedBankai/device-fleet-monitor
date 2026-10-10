"""Shared fixtures: an isolated app per test and a controllable fake clock."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.dependencies import get_now, get_store
from src.main import app
from src.store import DeviceStore

START = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def client(clock):
    # A brand-new empty store per test, so tests can never affect each other.
    store = DeviceStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_now] = clock.now
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def register(client):
    def _register(device_id: str = "device-01", name: str = "Lab Device 01"):
        return client.post("/devices", json={"id": device_id, "name": name})

    return _register


@pytest.fixture
def send_heartbeat(client, clock):
    def _send(device_id: str = "device-01", status: str = "OK", timestamp=None, **extra):
        payload = {
            "timestamp": (timestamp or clock.now()).isoformat(),
            "status": status,
            **extra,
        }
        return client.post(f"/devices/{device_id}/heartbeat", json=payload)

    return _send