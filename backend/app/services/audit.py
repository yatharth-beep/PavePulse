import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Incident, User


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def canonical_incident_payload(
    *,
    source_event_id: str,
    lon: float,
    lat: float,
    severity: str,
    depth_mm: float,
    estimated_volume_m3: float,
    observed_at: datetime,
    hit_count: int,
    previous_hash: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_event_id": source_event_id,
        "lon": round(float(lon), 7),
        "lat": round(float(lat), 7),
        "severity": severity,
        "depth_mm": round(float(depth_mm), 3),
        "estimated_volume_m3": round(float(estimated_volume_m3), 5),
        "observed_at": iso_utc(observed_at),
        "hit_count": hit_count,
        "previous_hash": previous_hash or "",
        "extra": extra or {},
    }


def compute_audit_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def incident_integrity_fields(incident: Incident) -> dict[str, Any]:
    return {
        "status": incident.status,
        "route_id": incident.route_id,
        "ward_id": str(incident.ward_id or ""),
        "vehicle_id": str(incident.vehicle_id or ""),
        "sensor_log": incident.sensor_log or {},
        "reviewed_by": str(incident.reviewed_by or ""),
        "reviewed_at": iso_utc(incident.reviewed_at) if incident.reviewed_at else "",
        "merged_into_id": str(incident.merged_into_id or ""),
    }


def verify_incident(incident: Incident) -> bool:
    payload = canonical_incident_payload(
        source_event_id=incident.source_event_id,
        lon=incident.lon,
        lat=incident.lat,
        severity=incident.severity,
        depth_mm=incident.depth_mm,
        estimated_volume_m3=incident.estimated_volume_m3,
        observed_at=incident.observed_at,
        hit_count=incident.hit_count,
        previous_hash=incident.previous_hash,
        extra=incident_integrity_fields(incident),
    )
    return compute_audit_hash(payload) == incident.audit_hash


def record_audit(
    db: Session,
    *,
    actor: User | None = None,
    actor_label: str | None = None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
    commit: bool = True,
) -> None:
    """Retired log writer retained as a compatibility no-op for existing workflows.

    The public Audit screen/API and audit-log writes are disabled for the final prototype.
    Incident integrity hashes remain enabled independently of this hook.
    """
    return None
