"""Shared objects injected into the routes (easy to swap out in tests)."""
from datetime import datetime, timezone

from src.store import DeviceStore

_store = DeviceStore()


def get_store() -> DeviceStore:
    return _store


def get_now() -> datetime:
    return datetime.now(timezone.utc)