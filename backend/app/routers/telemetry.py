import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.geo import ROUTES
from app.models import TelemetryPing, User, Vehicle
from app.schemas import CreateVehicleIn, DeviceHealthOut, TelemetryOut
from app.services.auth import require_roles
from app.services.audit import record_audit
from app.services.hub import hub
from app.services.spatial import utcnow

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.get("/latest", response_model=list[TelemetryOut])
def latest(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    if hub.latest:
        return hub.latest[-20:]
    stmt = (
        select(TelemetryPing)
        .options(joinedload(TelemetryPing.vehicle))
        .order_by(TelemetryPing.observed_at.desc())
        .limit(20)
    )
    rows = db.execute(stmt).unique().scalars().all()
    return [
        TelemetryOut(
            vehicle_label=row.vehicle.label,
            route_id=row.vehicle.route_id,
            lon=row.lon,
            lat=row.lat,
            speed_kmh=row.speed_kmh,
            engine_status=row.engine_status,
            sensor_log=row.sensor_log or {},
            observed_at=row.observed_at,
        )
        for row in rows
    ]


@router.get("/devices", response_model=list[DeviceHealthOut])
def devices(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("engineer")),
):
    vehicles = db.execute(select(Vehicle).order_by(Vehicle.label)).scalars().all()
    now = utcnow()
    out = []
    for vehicle in vehicles:
        last_seen = vehicle.last_seen_at
        online = bool(last_seen and (now - last_seen.replace(tzinfo=last_seen.tzinfo or now.tzinfo)) <= timedelta(minutes=settings.device_offline_minutes))
        out.append(
            DeviceHealthOut(
                vehicle_label=vehicle.label,
                fleet_id=vehicle.fleet_id,
                route_id=vehicle.route_id,
                power_status=vehicle.power_status,
                connectivity_status=vehicle.connectivity_status if online else "offline",
                last_seen_at=vehicle.last_seen_at,
                software_version=vehicle.software_version,
                last_error=vehicle.last_error,
                credential_configured=bool(vehicle.device_key_hash),
            )
        )
    return out


@router.post("/devices", response_model=DeviceHealthOut, status_code=201)
def register_device(
    payload: CreateVehicleIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    if payload.route_id not in ROUTES:
        raise HTTPException(422, f"route_id must be one of: {', '.join(ROUTES)}")
    exists = db.execute(select(Vehicle).where(Vehicle.label == payload.vehicle_label)).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"Vehicle '{payload.vehicle_label}' is already registered")
    vehicle = Vehicle(
        fleet_id=payload.fleet_id,
        label=payload.vehicle_label,
        route_id=payload.route_id,
        power_status="unknown",
        connectivity_status="offline",
        software_version=payload.software_version,
    )
    db.add(vehicle)
    db.flush()
    record_audit(
        db, actor=actor, action="device.registered", entity_type="vehicle", entity_id=str(vehicle.id),
        details={"vehicle_label": vehicle.label, "fleet_id": vehicle.fleet_id, "route_id": vehicle.route_id},
        commit=False,
    )
    db.commit()
    return DeviceHealthOut(
        vehicle_label=vehicle.label, fleet_id=vehicle.fleet_id, route_id=vehicle.route_id,
        power_status=vehicle.power_status, connectivity_status=vehicle.connectivity_status,
        last_seen_at=vehicle.last_seen_at, software_version=vehicle.software_version,
        last_error=vehicle.last_error, credential_configured=False,
    )


@router.post("/devices/{vehicle_label}/credentials")
def rotate_device_credential(
    vehicle_label: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    vehicle = db.execute(select(Vehicle).where(Vehicle.label == vehicle_label.upper())).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    raw_key = secrets.token_urlsafe(32)
    vehicle.device_key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    db.add(vehicle)
    record_audit(
        db, actor=actor, action="device.credential_rotated", entity_type="vehicle", entity_id=str(vehicle.id),
        details={"vehicle_label": vehicle.label}, commit=False,
    )
    db.commit()
    return {"vehicle_label": vehicle.label, "device_key": raw_key, "warning": "Copy this key now; it cannot be retrieved again."}


@router.get("/stream")
async def stream(_: User = Depends(require_roles("engineer"))):
    return StreamingResponse(
        hub.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
