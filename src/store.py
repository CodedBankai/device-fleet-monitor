"""Thread-safe in-memory device storage."""
import threading
from dataclasses import replace
from datetime import datetime
from typing import Any

from src.models import Device


class DeviceAlreadyExistsError(Exception):
    pass


class DeviceNotFoundError(Exception):
    pass


class DeviceStore:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _copy(device: Device) -> Device:
        # Callers get a copy so they can never modify stored data without the lock.
        return replace(device, metrics=dict(device.metrics))

    def add(self, device_id: str, name: str, registered_at: datetime) -> Device:
        with self._lock:
            if device_id in self._devices:
                raise DeviceAlreadyExistsError(device_id)
            device = Device(id=device_id, name=name, registered_at=registered_at)
            self._devices[device_id] = device
            return self._copy(device)

    def get(self, device_id: str) -> Device:
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise DeviceNotFoundError(device_id)
            return self._copy(device)

    def list_all(self) -> list[Device]:
        with self._lock:
            return [self._copy(d) for d in self._devices.values()]

    def record_heartbeat(
        self,
        device_id: str,
        event_timestamp: datetime,
        payload_status: str,
        metrics: dict[str, Any],
        received_at: datetime,
    ) -> tuple[Device, bool]:
        """Store a heartbeat. Returns (device, payload_applied)."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise DeviceNotFoundError(device_id)

            # Hearing from the device at all means it is alive, even if the
            # payload turns out to be stale, so this is always updated.
            device.last_seen_server_time = received_at

            # Only accept the payload if it is not older than what we already have.
            is_stale = (
                device.latest_event_timestamp is not None
                and event_timestamp < device.latest_event_timestamp
            )
            if is_stale:
                return self._copy(device), False

            device.latest_event_timestamp = event_timestamp
            device.payload_status = payload_status
            device.metrics = dict(metrics)
            return self._copy(device), True