"""Single, centralized status calculation used by every endpoint."""
from datetime import datetime

from src.config import ONLINE_TIMEOUT_SECONDS
from src.models import ConnectivityStatus, Device


def calculate_status(
    device: Device,
    reference_now: datetime,
    timeout_seconds: float = ONLINE_TIMEOUT_SECONDS,
) -> ConnectivityStatus:
    """Return ONLINE/OFFLINE for a device at `reference_now`.

    Rules:
      No heartbeat ever received -> OFFLINE.
      Age of last server-side receipt <= timeout (inclusive) -> ONLINE.
      Otherwise -> OFFLINE.

    Only `last_seen_server_time` is used, so a skewed or wrong device clock
    cannot affect connectivity, and the payload status (e.g. "ERROR") is ignored.
    A negative age (heartbeat landed just after `reference_now` was taken)
    counts as ONLINE.
    """
    if device.last_seen_server_time is None:
        return ConnectivityStatus.OFFLINE

    age = (reference_now - device.last_seen_server_time).total_seconds()
    if age <= timeout_seconds:
        return ConnectivityStatus.ONLINE
    return ConnectivityStatus.OFFLINE