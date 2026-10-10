"""Device simulator: sends heartbeats for several fake devices to the monitor API.

Run (with the API server already running, or start it later - we keep retrying):
    python simulator/simulator.py
    python simulator/simulator.py --base-url http://127.0.0.1:8000 --devices 5 --interval 5
"""
import argparse
import logging
import random
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger("simulator")


class SimulatedDevice:
    """One fake device that sends a heartbeat on its own thread."""

    def __init__(
        self,
        device_id: str,
        name: str,
        base_url: str,
        interval: float,
        timeout: float,
    ) -> None:
        self.device_id = device_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.interval = interval
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start sending heartbeats. Returns False if it was already running."""
        if self.running:
            return False
        self._stop_event.clear()
        # A finished thread cannot be restarted, so every start makes a new one.
        self._thread = threading.Thread(target=self._run, name=self.device_id, daemon=True)
        self._thread.start()
        return True

    def stop(self, wait: bool = True) -> bool:
        """Stop sending heartbeats. Returns False if it was not running."""
        if not self.running:
            return False
        self._stop_event.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=self.timeout + 2)
        return True

    def _run(self) -> None:
        registered = False
        # timeout=... applies to connecting, sending and reading, so a hung
        # server can never block this thread for longer than a few seconds.
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            while not self._stop_event.is_set():
                try:
                    if not registered:
                        registered = self._register(client)
                    if registered:
                        registered = self._send_heartbeat(client)
                except httpx.TransportError as exc:
                    # Covers timeouts, refused connections, DNS errors, etc.
                    log.warning(
                        "%s: server unreachable (%s); retrying in %ss",
                        self.device_id,
                        type(exc).__name__,
                        self.interval,
                    )
                self._stop_event.wait(self.interval)
        log.info("%s: stopped", self.device_id)

    def _register(self, client: httpx.Client) -> bool:
        response = client.post("/devices", json={"id": self.device_id, "name": self.name})
        if response.status_code == 201:
            log.info("%s: registered", self.device_id)
            return True
        if response.status_code == 409:
            log.info("%s: already registered", self.device_id)
            return True
        log.error(
            "%s: registration rejected (%s): %s",
            self.device_id,
            response.status_code,
            response.text,
        )
        return False

    def _send_heartbeat(self, client: httpx.Client) -> bool:
        """Send one heartbeat. Returns False if the server no longer knows us."""
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Roughly 1 in 10 heartbeats reports ERROR to show that a device
            # reporting a problem is still ONLINE.
            "status": random.choices(["OK", "ERROR"], weights=[9, 1])[0],
            "cpu_usage": random.randint(10, 90),
            "signal_strength": random.randint(-90, -50),
        }
        response = client.post(f"/devices/{self.device_id}/heartbeat", json=payload)
        if response.status_code == 200:
            log.info("%s: heartbeat sent (status=%s)", self.device_id, payload["status"])
            return True
        if response.status_code == 404:
            log.warning("%s: server does not know this device; re-registering", self.device_id)
            return False
        log.error(
            "%s: heartbeat rejected (%s): %s",
            self.device_id,
            response.status_code,
            response.text,
        )
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate a fleet of devices sending heartbeats.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API address")
    parser.add_argument("--devices", type=int, default=5, help="number of simulated devices")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between heartbeats")
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds")
    args = parser.parse_args()
    if args.devices < 1:
        parser.error("--devices must be at least 1")
    return args


def build_devices(args: argparse.Namespace) -> dict[str, SimulatedDevice]:
    devices = {}
    for number in range(1, args.devices + 1):
        device_id = f"device-{number:02d}"
        devices[device_id] = SimulatedDevice(
            device_id,
            f"Simulated Device {number:02d}",
            args.base_url,
            args.interval,
            args.timeout,
        )
    return devices


HELP = """Commands:
  status             show which devices are running
  stop <id|n|all>    stop a device, e.g. 'stop device-03', 'stop 3' or 'stop all'
  start <id|n|all>   resume a device, e.g. 'start 3'
  help               show this message
  quit               stop everything and exit"""


def resolve(devices: dict[str, SimulatedDevice], token: str) -> list[SimulatedDevice]:
    """Turn 'all', 'device-03' or '3' into a list of devices (empty if unknown)."""
    if token == "all":
        return list(devices.values())
    if token in devices:
        return [devices[token]]
    if token.isdigit():
        key = f"device-{int(token):02d}"
        if key in devices:
            return [devices[key]]
    return []


def handle_command(devices: dict[str, SimulatedDevice], line: str) -> bool:
    """Run one command. Returns False when the user asked to quit."""
    parts = line.split()
    if not parts:
        return True
    command = parts[0].lower()

    if command in ("quit", "exit", "q"):
        return False
    if command == "help":
        print(HELP)
    elif command == "status":
        for device in devices.values():
            print(f"  {device.device_id}: {'RUNNING' if device.running else 'STOPPED'}")
    elif command in ("stop", "start"):
        if len(parts) != 2:
            print(f"Usage: {command} <id|n|all>")
            return True
        targets = resolve(devices, parts[1])
        if not targets:
            print(f"Unknown device '{parts[1]}'. Type 'status' to see the list.")
            return True
        for device in targets:
            changed = device.stop() if command == "stop" else device.start()
            if not changed:
                state = "already stopped" if command == "stop" else "already running"
                print(f"  {device.device_id} is {state}")
    else:
        print(f"Unknown command '{command}'. Type 'help'.")
    return True

def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    devices = build_devices(args)
    for device in devices.values():
        device.start()
    log.info("Simulating %d devices against %s", len(devices), args.base_url)
    print(HELP)

    try:
        while True:
            try:
                line = input("> ")
            except EOFError:  # input stream closed (e.g. piped input ended)
                break
            if not handle_command(devices, line):
                break
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Shutting down...")
        for device in devices.values():
            device.stop(wait=False)


if __name__ == "__main__":
    main()