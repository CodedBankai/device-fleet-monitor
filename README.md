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