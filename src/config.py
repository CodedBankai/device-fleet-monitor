"""Application configuration (overridable via environment variables)."""
import os

# A device is ONLINE if its last heartbeat was received within this many seconds.
ONLINE_TIMEOUT_SECONDS: float = float(os.getenv("ONLINE_TIMEOUT_SECONDS", "30"))