"""Domain model for the fleet monitor (no web or storage concerns here)."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ConnectivityStatus(str, Enum):
    """Whether we have recently heard from the device (NOT whether it is healthy)."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


@dataclass
class Device:
    id: str
    name: str
    registered_at: datetime
    # Server clock time of the most recent heartbeat receipt. Drives ONLINE/OFFLINE.
    last_seen_server_time: Optional[datetime] = None
    # Device-reported timestamp of the newest accepted heartbeat (used to ignore stale ones).
    latest_event_timestamp: Optional[datetime] = None
    # Health status reported by the device payload (e.g. "OK", "ERROR"). Metadata only.
    payload_status: Optional[str] = None
    # Extra optional metrics from the latest accepted heartbeat (cpu_usage, ...).
    metrics: dict[str, Any] = field(default_factory=dict)