"""Request/response shapes (validation lives here, not in the routes)."""
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from src.models import ConnectivityStatus


class DeviceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)

    @field_validator("id", "name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class HeartbeatIn(BaseModel):
    timestamp: datetime
    status: str = Field(min_length=1, max_length=32)
    # Optional extra metrics
    cpu_usage: Optional[float] = Field(default=None, ge=0, le=100)
    signal_strength: Optional[float] = None

    @field_validator("timestamp")
    @classmethod
    def normalize_to_utc(cls, value: datetime) -> datetime:
        # A timestamp without a timezone is assumed to be UTC.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DeviceOut(BaseModel):
    id: str
    name: str
    status: ConnectivityStatus
    last_heartbeat: Optional[datetime]  # server time we last heard from it
    registered_at: datetime
    last_event_timestamp: Optional[datetime]  # newest timestamp the device itself reported
    payload_status: Optional[str]  # device-reported health ("OK", "ERROR", ...)
    metrics: dict[str, Any]


class HeartbeatAck(BaseModel):
    device_id: str
    status: ConnectivityStatus
    payload_applied: bool  # False if the heartbeat was older than one we already have


class SummaryOut(BaseModel):
    total: int
    online: int
    offline: int