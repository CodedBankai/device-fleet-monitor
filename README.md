# Device Fleet Monitor

A small FastAPI service that tracks heartbeats from a fleet of devices and reports which ones are currently `ONLINE` or `OFFLINE`, plus a simulator that fakes a fleet so the whole system can be demonstrated end to end.

## What it does

- Devices are registered via the API and then send periodic heartbeats.
- The service remembers the latest heartbeat of every device.
- A device is **ONLINE** if the server received a heartbeat from it within the last **30 seconds** (inclusive), otherwise **OFFLINE**. A device that has never sent a heartbeat is OFFLINE.
- Operators can list devices, inspect one device, or get a fleet summary.
- A simulator script runs 5 fake devices (heartbeat every 5 seconds) and lets you stop and restart any one of them to watch it go OFFLINE and come back.

## Project structure

```text
device-fleet-monitor/
├── README.md
├── requirements.txt
├── pytest.ini
├── src/
│   ├── main.py          # app creation, malformed-JSON (400) handling
│   ├── routes.py        # HTTP layer (endpoints only, no business rules)
│   ├── schemas.py       # request/response validation (Pydantic)
│   ├── models.py        # Device dataclass and ConnectivityStatus enum
│   ├── status.py        # calculate_status(): the single status rule
│   ├── store.py         # thread-safe in-memory storage
│   ├── dependencies.py  # injectable store and clock
│   └── config.py        # ONLINE_TIMEOUT_SECONDS (env-configurable)
├── tests/
│   ├── conftest.py      # fake clock + isolated store fixtures
│   ├── test_status.py           # unit tests for the status rule
│   ├── test_devices_api.py      # registration and lookup
│   ├── test_heartbeat_api.py    # heartbeat handling
│   └── test_status_api.py       # timeout boundaries, invariants, edge cases
└── simulator/
    └── simulator.py     # multi-device heartbeat simulator
```

## Design / architecture

The code is split into layers so each file has one job:

| Layer | File(s) | Responsibility |
|---|---|---|
| Model | `models.py` | What a device is. No web or storage code. |
| Logic | `status.py`, `store.py` | The ONLINE/OFFLINE rule and thread-safe storage. |
| Schema | `schemas.py` | Validates incoming JSON and shapes responses. |
| Route | `routes.py`, `main.py` | Translates HTTP requests into logic calls and back. |

Key design decisions:

1. **Connectivity vs. health are separate.** ONLINE/OFFLINE depends only on when the *server* last received a heartbeat (`last_seen_server_time`). The `status` inside the heartbeat (e.g. `OK`, `ERROR`) is stored as `payload_status` and never affects connectivity. A device reporting `ERROR` is still talking to us, so it is still ONLINE.
2. **Server clock, not device clock.** Device clocks can be wrong, so they are never used for the 30-second rule. The device-reported timestamp is only used to ignore out-of-order payloads.
3. **One status function.** `calculate_status(device, reference_now)` is the only place the rule exists. `GET /devices`, `GET /devices/{id}` and `GET /summary` all use it, so they cannot disagree.
4. **One `now` per request.** `/summary` evaluates every device against a single reference time, so `total == online + offline` always holds.
5. **Out-of-order safety.** A heartbeat with an older device timestamp than the one already stored does not overwrite the stored payload, but it still counts as proof the device is alive.
6. **Thread-safe storage.** FastAPI runs sync endpoints in a thread pool, so all store access is guarded by a lock, and callers receive copies of devices rather than live objects.
7. **Injectable clock.** The current time comes from a dependency (`get_now`), so tests can move time forward instantly instead of sleeping for 30 seconds.

## Prerequisites

- Python 3.10 or newer
- Git
- Internet access for `pip install` (first setup only)

## Build / setup

```bash
git clone https://github.com/<your-username>/device-fleet-monitor.git
cd device-fleet-monitor

python -m venv .venv
# Activate the virtual environment:
#   Windows (PowerShell): .venv\Scripts\Activate.ps1
#   Windows (cmd):        .venv\Scripts\activate.bat
#   macOS / Linux:        source .venv/bin/activate

pip install -r requirements.txt
```

There is no separate compile step.

## Run the application

```bash
uvicorn src.main:app --reload
```

The API is now at http://127.0.0.1:8000. Interactive API documentation (try every endpoint from the browser) is at http://127.0.0.1:8000/docs.

Optional configuration: set the environment variable `ONLINE_TIMEOUT_SECONDS` (default `30`) before starting the server to change the timeout.

## Run the simulator

Start the API first (the simulator also keeps retrying if the API is not up yet). In a second terminal, with the virtual environment active:

```bash
python simulator/simulator.py
```

This starts 5 devices (`device-01` ... `device-05`), each sending a heartbeat every 5 seconds. About 1 in 10 heartbeats reports `ERROR` to show that such devices stay ONLINE.

Options:

```text
--base-url   API address              (default http://127.0.0.1:8000)
--devices    number of devices        (default 5)
--interval   seconds between beats    (default 5)
--timeout    HTTP timeout in seconds  (default 3)
```

Interactive commands (type at the `>` prompt while it runs):

```text
status             show which devices are running
stop <id|n|all>    e.g. stop device-03, stop 3, stop all
start <id|n|all>   e.g. start 3
help               list commands
quit               stop everything and exit
```

Try it: type `stop 3`, wait about 30 seconds, then open http://127.0.0.1:8000/summary. You should see 4 online and 1 offline. Type `start 3` and it returns to ONLINE.

## Run the tests

```bash
pytest -v
```

The tests use a fake clock, so they finish in well under a second and never wait in real time.

## Example API requests

The examples use `curl` (macOS, Linux, or Git Bash on Windows). You can also run all of them from http://127.0.0.1:8000/docs.

**Register a device** (`201 Created`)

```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id": "device-01", "name": "Lab Device 01"}'
```

```json
{
  "id": "device-01",
  "name": "Lab Device 01",
  "status": "OFFLINE",
  "last_heartbeat": null,
  "registered_at": "2026-10-10T10:00:00Z",
  "last_event_timestamp": null,
  "payload_status": null,
  "metrics": {}
}
```

**Send a heartbeat** (`200 OK`)

```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-10-10T10:00:05Z", "status": "OK", "cpu_usage": 42, "signal_strength": -71}'
```

```json
{ "device_id": "device-01", "status": "ONLINE", "payload_applied": true }
```

**List devices, get one device, get the summary**

```bash
curl http://127.0.0.1:8000/devices
curl http://127.0.0.1:8000/devices/device-01
curl http://127.0.0.1:8000/summary
```

```json
{ "total": 1, "online": 1, "offline": 0 }
```

**Error responses**

| Situation | Response |
|---|---|
| Registering an ID that already exists | `409 Conflict` |
| Heartbeat or lookup for an unknown device | `404 Not Found` |
| Request body is not valid JSON | `400 Bad Request` |
| Valid JSON but missing/invalid fields (blank id, bad timestamp, missing status) | `422 Unprocessable Entity` |

Windows PowerShell users: use the `/docs` page, or `Invoke-RestMethod`, since PowerShell handles quotes in `curl` differently.

## Edge case handling

| Edge case | Behaviour |
|---|---|
| Device never sent a heartbeat | OFFLINE, `last_heartbeat` is `null` |
| Heartbeat exactly 30 s ago | ONLINE (the limit is inclusive); 30.001 s is OFFLINE |
| Heartbeat with `"status": "ERROR"` | Device stays ONLINE; `payload_status` shows `ERROR` |
| Device clock is wrong (e.g. a year behind) | No effect on ONLINE/OFFLINE, which uses server receipt time |
| Heartbeat arrives out of order (older device timestamp) | Payload and metrics are not overwritten (`payload_applied: false`), but the device is still marked as seen |
| Timestamp without a timezone | Assumed to be UTC |
| Summary consistency | Every device is evaluated against one shared `now`, so `total == online + offline` |
| Re-registering an existing ID | `409`; the original device is left unchanged |
| Simulator cannot reach the server | Logs a warning and retries every interval; requests time out after 3 s so threads never hang |
| Server restarts and forgets devices | Simulator gets a `404`, re-registers, and carries on |

## Assumptions

- Duplicate registration is rejected with `409` (rather than silently updating), so one client cannot overwrite another's device by accident.
- Device IDs are case-sensitive; IDs and names are trimmed of surrounding spaces, and IDs are at most 64 characters.
- The 30-second timeout is measured from the server's receipt time, with the 30.0 s boundary counted as ONLINE.
- Heartbeat `status` is free text (`OK`, `ERROR`, ...); the service does not restrict its values.
- `cpu_usage` must be between 0 and 100 when provided.
- All times are handled and returned in UTC.

## Known limitations

- **No persistence.** Data lives in memory and is lost when the server restarts.
- **Single process only.** The lock protects threads within one process. Running several uvicorn workers would give each its own separate data.
- **No authentication.** Anyone who can reach the API can register devices or send heartbeats.
- **Future timestamps.** A device that sends a timestamp far in the future would cause its later (correct) payloads to be treated as stale. Connectivity status is unaffected.
- **No device deletion or update endpoint**, and no pagination of `GET /devices`.
- **The simulator is verified manually**, not by automated tests.

## What I would improve with one more day

1. Persist devices and heartbeats in SQLite so data survives restarts and several workers can share it.
2. Reject or clamp timestamps that are far in the future.
3. Add `GET /devices?status=ONLINE|OFFLINE` filtering, pagination, and a delete endpoint.
4. Add API-key authentication for the heartbeat endpoint.
5. Add structured (JSON) logging and a Dockerfile.
6. Add a concurrency test (many threads sending heartbeats at once) and automated tests for the simulator.
7. Set up GitHub Actions to run the tests on every push.