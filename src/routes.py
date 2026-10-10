"""HTTP layer: translates requests into store/status calls and back."""
from fastapi import APIRouter, Depends, HTTPException

from src.dependencies import get_now, get_store
from src.models import ConnectivityStatus, Device
from src.schemas import (
    DeviceCreate,
    DeviceOut,
    HeartbeatAck,
    HeartbeatIn,
    SummaryOut,
)
from src.status import calculate_status
from src.store import DeviceAlreadyExistsError, DeviceNotFoundError, DeviceStore

router = APIRouter()


def _to_out(device: Device, now) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        status=calculate_status(device, now),
        last_heartbeat=device.last_seen_server_time,
        registered_at=device.registered_at,
        last_event_timestamp=device.latest_event_timestamp,
        payload_status=device.payload_status,
        metrics=device.metrics,
    )


@router.post("/devices", response_model=DeviceOut, status_code=201)
def register_device(
    body: DeviceCreate,
    store: DeviceStore = Depends(get_store),
    now=Depends(get_now),
):
    try:
        device = store.add(body.id, body.name, registered_at=now)
    except DeviceAlreadyExistsError:
        raise HTTPException(status_code=409, detail=f"Device '{body.id}' already exists")
    return _to_out(device, now)


@router.post("/devices/{device_id}/heartbeat", response_model=HeartbeatAck)
def receive_heartbeat(
    device_id: str,
    body: HeartbeatIn,
    store: DeviceStore = Depends(get_store),
    now=Depends(get_now),
):
    metrics = body.model_dump(exclude={"timestamp", "status"}, exclude_none=True)
    try:
        device, applied = store.record_heartbeat(
            device_id,
            event_timestamp=body.timestamp,
            payload_status=body.status,
            metrics=metrics,
            received_at=now,
        )
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return HeartbeatAck(
        device_id=device.id,
        status=calculate_status(device, now),
        payload_applied=applied,
    )


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    store: DeviceStore = Depends(get_store),
    now=Depends(get_now),
):
    return [_to_out(d, now) for d in store.list_all()]


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: str,
    store: DeviceStore = Depends(get_store),
    now=Depends(get_now),
):
    try:
        device = store.get(device_id)
    except DeviceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return _to_out(device, now)


@router.get("/summary", response_model=SummaryOut)
def fleet_summary(
    store: DeviceStore = Depends(get_store),
    now=Depends(get_now),
):
    devices = store.list_all()
    online = offline = 0
    for device in devices:
        if calculate_status(device, now) == ConnectivityStatus.ONLINE:
            online += 1
        else:
            offline += 1
    return SummaryOut(total=len(devices), online=online, offline=offline)