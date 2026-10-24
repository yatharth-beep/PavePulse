import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.geo import parse_box_wkt, point_in_bounds
from app.models import Incident, Ward
from app.services.audit import canonical_incident_payload, compute_audit_hash, incident_integrity_fields


SEVERITY_RADIUS_M = {"critical": 0.45, "moderate": 0.25, "clear": 0.08}


def estimate_volume_m3(depth_mm: float, severity: str) -> float:
    radius = SEVERITY_RADIUS_M.get(severity, 0.2)
    depth_m = max(depth_mm, 0) / 1000.0
    return round(math.pi * radius * radius * depth_m, 5)


def infer_severity(depth_mm: float, surface_class: str | None) -> str:
    if surface_class in {"critical", "moderate", "clear"}:
        return surface_class
    if depth_mm >= 40:
        return "critical"
    if depth_mm >= 18:
        return "moderate"
    return "clear"


def point_wkt(lon: float, lat: float) -> str:
    return f"POINT({lon} {lat})"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlamb / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def find_duplicate(db: Session, lon: float, lat: float, severity: str, observed_at: datetime) -> Incident | None:
    cutoff = observed_at - timedelta(hours=settings.spatial_dedup_hours)
    if settings.use_postgis:
        stmt = text(
            """
            SELECT id FROM incidents
            WHERE severity = :severity
              AND merged_into_id IS NULL
              AND observed_at >= :cutoff
              AND observed_at <= :upper_bound
              AND ST_DWithin(
                    geography(ST_SetSRID(ST_MakePoint(lon, lat), 4326)),
                    geography(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)),
                    :meters
                  )
            ORDER BY ST_Distance(
                geography(ST_SetSRID(ST_MakePoint(lon, lat), 4326)),
                geography(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
              ) ASC, observed_at DESC
            LIMIT 1
            """
        )
        row = db.execute(
            stmt,
            {
                "severity": severity,
                "cutoff": cutoff,
                "upper_bound": observed_at + timedelta(hours=settings.spatial_dedup_hours),
                "lon": lon,
                "lat": lat,
                "meters": settings.spatial_dedup_meters,
            },
        ).first()
        if not row:
            return None
        return db.get(Incident, row[0])

    upper_bound = observed_at + timedelta(hours=settings.spatial_dedup_hours)
    candidates = db.execute(
        select(Incident).where(
            Incident.severity == severity,
            Incident.observed_at >= cutoff,
            Incident.observed_at <= upper_bound,
            Incident.merged_into_id.is_(None),
        )
    ).scalars()
    best: Incident | None = None
    best_d = settings.spatial_dedup_meters
    for incident in candidates:
        dist = haversine_m(lon, lat, incident.lon, incident.lat)
        if dist <= best_d:
            best = incident
            best_d = dist
    return best


def find_ward(db: Session, lon: float, lat: float, ward_code: str | None) -> Ward | None:
    if ward_code:
        ward = db.execute(select(Ward).where(Ward.code == ward_code)).scalar_one_or_none()
        if ward:
            return ward
    if settings.use_postgis:
        stmt = text(
            """
            SELECT id FROM wards
            WHERE ST_Covers(ST_GeomFromText(geom_wkt, 4326), ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            LIMIT 1
            """
        )
        row = db.execute(stmt, {"lon": lon, "lat": lat}).first()
        if row:
            return db.get(Ward, row[0])
    for ward in db.execute(select(Ward)).scalars():
        if point_in_bounds(lon, lat, parse_box_wkt(ward.geom_wkt)):
            return ward
    return None


def stamp_hash(incident: Incident, extra: dict | None = None) -> None:
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
        extra=extra or incident_integrity_fields(incident),
    )
    incident.audit_hash = compute_audit_hash(payload)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
