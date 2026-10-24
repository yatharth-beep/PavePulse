import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Vehicle
from sqlalchemy import select
from app.schemas import EdgeEventIn, IncidentOut
from app.services.incidents import get_incident, ingest_event, serialize_incident

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def require_device_key(
    x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    db: Session = Depends(get_db),
) -> str:
    if not x_device_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Valid X-Device-Key required")
    if not settings.is_production and hmac.compare_digest(x_device_key, settings.device_api_key):
        return "*"  # Local-only shared key; production uses per-device credentials.
    key_hash = hashlib.sha256(x_device_key.encode("utf-8")).hexdigest()
    vehicle = db.execute(select(Vehicle).where(Vehicle.device_key_hash == key_hash)).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Valid X-Device-Key required")
    return vehicle.label


@router.post("", response_model=IncidentOut)
def ingest(
    payload: EdgeEventIn,
    db: Session = Depends(get_db),
    device_label: str = Depends(require_device_key),
):
    if device_label != "*" and device_label != payload.vehicle_label:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device key does not match payload vehicle_label")
    incident, _deduped = ingest_event(db, payload, actor_label=f"device:{payload.vehicle_label}")
    incident = get_incident(db, incident.id)
    return serialize_incident(incident)
