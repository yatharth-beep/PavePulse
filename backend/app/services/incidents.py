import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import EventReceipt, Incident, IncidentVerification, User, Vehicle, WorkOrder
from app.schemas import EdgeEventIn, WorkOrderUpdateIn
from app.services.audit import record_audit, verify_incident
from app.services.spatial import (
    estimate_volume_m3,
    find_duplicate,
    find_ward,
    haversine_m,
    infer_severity,
    point_wkt,
    stamp_hash,
    utcnow,
)


def _vehicle_by_label(db: Session, label: str) -> Vehicle | None:
    return db.execute(select(Vehicle).where(Vehicle.label == label)).scalar_one_or_none()


def serialize_incident(incident: Incident) -> dict:
    latest_wo = None
    if incident.work_orders:
        latest_wo = max(incident.work_orders, key=lambda w: w.dispatched_at).ticket_no
    return {
        "id": incident.id,
        "source_event_id": incident.source_event_id,
        "vehicle_label": incident.vehicle.label if incident.vehicle else None,
        "ward_code": incident.ward.code if incident.ward else None,
        "ward_name": incident.ward.name if incident.ward else None,
        "route_id": incident.route_id,
        "severity": incident.severity,
        "status": incident.status,
        "lon": incident.lon,
        "lat": incident.lat,
        "depth_mm": incident.depth_mm,
        "estimated_volume_m3": incident.estimated_volume_m3,
        "hit_count": incident.hit_count,
        "observed_at": incident.observed_at,
        "audit_hash": incident.audit_hash,
        "previous_hash": incident.previous_hash,
        "sensor_log": incident.sensor_log or {},
        "work_order_ticket": latest_wo,
        "hash_valid": verify_incident(incident),
        "reviewed_by": str(incident.reviewed_by) if incident.reviewed_by else None,
        "reviewed_at": incident.reviewed_at,
        "merged_into_id": incident.merged_into_id,
        "verification_passes": int(incident.verification_passes or 0),
        "verification_required": settings.verification_required_buses,
        "verification_last_at": incident.verification_last_at,
        "verified_at": incident.verified_at,
        "verification_status": incident.verification_status or "not_required",
        "verification_cycle": int(incident.verification_cycle or 0),
    }


def _event_payload_hash(payload: EdgeEventIn) -> str:
    data = payload.model_dump(mode="json")
    data["timestamp"] = payload.timestamp.astimezone(timezone.utc).isoformat()
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _recover_event_retry(db: Session, payload: EdgeEventIn, payload_hash: str) -> tuple[Incident, bool] | None:
    db.rollback()
    receipt = db.get(EventReceipt, payload.event_id)
    if not receipt:
        return None
    if receipt.payload_hash and receipt.payload_hash != payload_hash:
        raise HTTPException(409, "event_id was already accepted with a different payload")
    existing = get_incident(db, receipt.incident_id)
    return (existing, True) if existing else None


def _commit_ingested_event(db: Session, payload: EdgeEventIn, payload_hash: str, incident_id: UUID) -> tuple[Incident | None, bool]:
    """Commit an event and its unique receipt; recover cleanly from concurrent retries."""
    try:
        db.commit()
        return None, False
    except IntegrityError:
        recovered = _recover_event_retry(db, payload, payload_hash)
        if recovered is None:
            raise
        return recovered


def _find_pending_verification(db: Session, lon: float, lat: float, observed_at: datetime) -> Incident | None:
    """Find the nearest repaired location waiting for independent fleet verification."""
    candidates = db.execute(
        select(Incident).options(joinedload(Incident.vehicle), joinedload(Incident.ward), joinedload(Incident.work_orders))
        .where(Incident.status == "awaiting_verification", Incident.merged_into_id.is_(None))
    ).unique().scalars().all()
    best = None
    best_distance = settings.verification_radius_meters
    for candidate in candidates:
        latest_order = max(candidate.work_orders, key=lambda order: order.dispatched_at, default=None)
        completed_at = latest_order.completed_at if latest_order else None
        if completed_at:
            # Do not accept buffered/pre-repair detections as proof of a repair.
            normalized_completed = completed_at.replace(tzinfo=completed_at.tzinfo or timezone.utc)
            if observed_at < normalized_completed:
                continue
        distance = haversine_m(lon, lat, candidate.lon, candidate.lat)
        if distance <= best_distance:
            best, best_distance = candidate, distance
    return best


def _verification_result(payload: EdgeEventIn, depth: float, severity: str) -> str | None:
    """Only count explicit clean classifications or sufficiently clear defect detections."""
    surface = (payload.sensors.surface_class or "").strip().lower().replace(" ", "_").replace("-", "_")
    clean_classes = {"clear", "no_defect", "normal", "good", "repaired", "healthy", "smooth"}
    defect_classes = {"critical", "moderate", "pothole", "crack", "damaged", "defect", "road_damage"}
    if severity in {"critical", "moderate"} or surface in defect_classes or depth >= 18:
        return "defect_found"
    if (payload.severity == "clear" or surface in clean_classes) and depth < 18:
        return "clear"
    return None


def _ingest_verification_pass(
    db: Session, payload: EdgeEventIn, payload_hash: str, incident: Incident, vehicle: Vehicle,
    *, depth: float, severity: str, event_time: datetime, result: str, actor_label: str,
) -> tuple[Incident, bool]:
    """Record a post-repair bus pass; two distinct buses verify a fix by default."""
    previous_status = incident.status
    observation = IncidentVerification(
        incident_id=incident.id, vehicle_id=vehicle.id, event_id=payload.event_id,
        cycle=incident.verification_cycle, result=result, observed_at=event_time,
        depth_mm=depth, severity=severity, details={"route_id": payload.route_id, "speed_kmh": payload.speed_kmh},
    )
    db.add(observation)
    db.add(EventReceipt(event_id=payload.event_id, incident_id=incident.id, payload_hash=payload_hash))
    incident.verification_last_at = event_time

    if result == "defect_found":
        old_severity = incident.severity
        incident.previous_hash = incident.audit_hash
        incident.status = "open"
        incident.verification_status = "failed"
        detected_surface = (payload.sensors.surface_class or "").strip().lower().replace(" ", "_").replace("-", "_")
        if severity in {"critical", "moderate"}:
            incident.severity = severity
        elif depth >= 40:
            incident.severity = "critical"
        elif depth >= 18 or detected_surface in {"pothole", "crack", "damaged", "defect", "road_damage"}:
            incident.severity = "moderate"
        else:
            incident.severity = "moderate"
        incident.depth_mm = depth
        incident.estimated_volume_m3 = estimate_volume_m3(depth, incident.severity)
        incident.hit_count += 1
        incident.observed_at = event_time
        incident.vehicle_id = vehicle.id
        incident.route_id = payload.route_id
        incident.sensor_log = payload.sensors.model_dump()
        detected_ward = find_ward(db, payload.lon, payload.lat, payload.ward_code)
        incident.ward_id = detected_ward.id if detected_ward else incident.ward_id
        stamp_hash(incident)
        record_audit(
            db, actor=None, actor_label=actor_label, action="incident.verification_failed",
            entity_type="incident", entity_id=str(incident.id),
            details={"event_id": payload.event_id, "vehicle_label": vehicle.label, "cycle": incident.verification_cycle,
                     "distance_m": round(haversine_m(payload.lon, payload.lat, incident.lon, incident.lat), 2),
                     "previous_status": previous_status, "reopened_as": incident.status,
                     "previous_severity": old_severity, "detected_severity": incident.severity}, commit=False,
        )
        record_audit(
            db, actor=None, actor_label=actor_label, action="incident.status_changed",
            entity_type="incident", entity_id=str(incident.id),
            details={"from": previous_status, "to": "open", "reason": "defect detected during post-repair verification",
                     "event_id": payload.event_id}, commit=False,
        )
    else:
        db.flush()
        # A pass only counts once per distinct bus, and never counts the original reporting bus.
        clear_vehicle_ids = db.execute(
            select(IncidentVerification.vehicle_id).where(
                IncidentVerification.incident_id == incident.id,
                IncidentVerification.cycle == incident.verification_cycle,
                IncidentVerification.result == "clear",
                IncidentVerification.vehicle_id != incident.vehicle_id,
            ).distinct()
        ).scalars().all()
        incident.verification_passes = len(clear_vehicle_ids)
        record_audit(
            db, actor=None, actor_label=actor_label, action="incident.verification_passed",
            entity_type="incident", entity_id=str(incident.id),
            details={"event_id": payload.event_id, "vehicle_label": vehicle.label, "cycle": incident.verification_cycle,
                     "distinct_bus_passes": incident.verification_passes,
                     "required_bus_passes": settings.verification_required_buses,
                     "counted": vehicle.id != incident.vehicle_id and vehicle.id in clear_vehicle_ids}, commit=False,
        )
        if incident.verification_passes >= settings.verification_required_buses:
            incident.previous_hash = incident.audit_hash
            incident.status = "verified_fixed"
            incident.verification_status = "verified"
            incident.verified_at = event_time
            stamp_hash(incident)
            record_audit(
                db, actor=None, actor_label=actor_label, action="incident.status_changed",
                entity_type="incident", entity_id=str(incident.id),
                details={"from": previous_status, "to": "verified_fixed", "cycle": incident.verification_cycle,
                         "distinct_bus_passes": incident.verification_passes}, commit=False,
            )
        else:
            incident.verification_status = "pending"
        db.add(incident)

    try:
        db.commit()
    except IntegrityError:
        recovered = _recover_event_retry(db, payload, payload_hash)
        if recovered is None:
            raise
        return recovered
    return get_incident(db, incident.id) or incident, False


def ingest_event(db: Session, payload: EdgeEventIn, *, actor_label: str = "edge-device") -> tuple[Incident, bool]:
    # Idempotency: a retry of the same edge packet must not inflate a cluster.
    payload_hash = _event_payload_hash(payload)
    receipt = db.get(EventReceipt, payload.event_id)
    if receipt:
        if receipt.payload_hash and receipt.payload_hash != payload_hash:
            raise HTTPException(409, "event_id was already accepted with a different payload")
        existing = get_incident(db, receipt.incident_id)
        if existing:
            return existing, True

    event_time = payload.timestamp.astimezone(timezone.utc)
    depth = payload.sensors.depth_mm or 0.0
    severity = payload.severity or infer_severity(depth, payload.sensors.surface_class)
    volume = estimate_volume_m3(depth, severity)
    vehicle = _vehicle_by_label(db, payload.vehicle_label)
    if not vehicle:
        raise HTTPException(422, f"Unknown vehicle '{payload.vehicle_label}'")
    if vehicle.route_id != payload.route_id:
        raise HTTPException(422, f"Vehicle {vehicle.label} is registered on route {vehicle.route_id}")
    last_seen = vehicle.last_seen_at
    if last_seen is None or event_time >= last_seen.replace(tzinfo=last_seen.tzinfo or timezone.utc):
        vehicle.last_seen_at = event_time
        vehicle.power_status = "on"
        vehicle.connectivity_status = "connected"
        vehicle.last_error = None
        db.add(vehicle)
    ward = find_ward(db, payload.lon, payload.lat, payload.ward_code)
    pending_verification = _find_pending_verification(db, payload.lon, payload.lat, event_time)
    verification_result = _verification_result(payload, depth, severity) if pending_verification else None
    if pending_verification and verification_result:
        return _ingest_verification_pass(
            db, payload, payload_hash, pending_verification, vehicle,
            depth=depth, severity=severity, event_time=event_time,
            result=verification_result, actor_label=actor_label,
        )

    duplicate = find_duplicate(db, payload.lon, payload.lat, severity, event_time)

    if duplicate:
        duplicate.previous_hash = duplicate.audit_hash
        duplicate.hit_count += 1
        duplicate.depth_mm = max(duplicate.depth_mm, depth)
        duplicate.estimated_volume_m3 = estimate_volume_m3(duplicate.depth_mm, duplicate.severity)
        if event_time >= duplicate.observed_at.replace(tzinfo=duplicate.observed_at.tzinfo or timezone.utc):
            duplicate.observed_at = event_time
        duplicate.sensor_log = payload.sensors.model_dump()
        if vehicle:
            duplicate.vehicle_id = vehicle.id
        if ward:
            duplicate.ward_id = ward.id
        stamp_hash(duplicate)
        db.add(duplicate)
        db.flush()
        db.add(EventReceipt(event_id=payload.event_id, incident_id=duplicate.id, payload_hash=payload_hash))
        try:
            record_audit(
                db, actor=None, actor_label=actor_label, action="event.clustered",
                entity_type="incident", entity_id=str(duplicate.id),
                details={"event_id": payload.event_id, "hit_count": duplicate.hit_count, "deduplicated": True},
                commit=False,
            )
            replayed, already_processed = _commit_ingested_event(db, payload, payload_hash, duplicate.id)
        except IntegrityError:
            recovered = _recover_event_retry(db, payload, payload_hash)
            if recovered is None:
                raise
            return recovered
        if already_processed and replayed is not None:
            return replayed, True
        db.refresh(duplicate)
        return duplicate, True

    incident = Incident(
        source_event_id=payload.event_id,
        vehicle_id=vehicle.id if vehicle else None,
        ward_id=ward.id if ward else None,
        route_id=payload.route_id,
        severity=severity,
        status="open",
        lon=payload.lon,
        lat=payload.lat,
        geom_wkt=point_wkt(payload.lon, payload.lat),
        depth_mm=depth,
        estimated_volume_m3=volume,
        hit_count=1,
        observed_at=event_time,
        previous_hash=None,
        sensor_log=payload.sensors.model_dump(),
    )
    stamp_hash(incident)
    db.add(incident)
    db.flush()
    db.add(EventReceipt(event_id=payload.event_id, incident_id=incident.id, payload_hash=payload_hash))
    try:
        record_audit(
            db, actor=None, actor_label=actor_label, action="event.ingested",
            entity_type="incident", entity_id=str(incident.id),
            details={"event_id": payload.event_id, "severity": severity, "deduplicated": False},
            commit=False,
        )
        replayed, already_processed = _commit_ingested_event(db, payload, payload_hash, incident.id)
    except IntegrityError:
        recovered = _recover_event_retry(db, payload, payload_hash)
        if recovered is None:
            raise
        return recovered
    if already_processed and replayed is not None:
        return replayed, True
    db.refresh(incident)
    return incident, False


def list_incidents(
    db: Session,
    *,
    ward: str | None = None,
    route: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[Incident]:
    stmt = select(Incident).options(
        joinedload(Incident.vehicle),
        joinedload(Incident.ward),
        joinedload(Incident.work_orders),
    ).where(Incident.merged_into_id.is_(None))
    if ward:
        from app.models import Ward

        stmt = stmt.join(Ward, Incident.ward_id == Ward.id).where(Ward.code == ward)
    if route:
        stmt = stmt.where(Incident.route_id == route)
    if status:
        stmt = stmt.where(Incident.status == status)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    if date_from:
        stmt = stmt.where(Incident.observed_at >= date_from)
    if date_to:
        stmt = stmt.where(Incident.observed_at <= date_to)
    stmt = stmt.order_by(Incident.observed_at.desc())
    return list(db.execute(stmt).unique().scalars().all())


def get_incident(db: Session, incident_id: UUID) -> Incident | None:
    stmt = (
        select(Incident)
        .options(joinedload(Incident.vehicle), joinedload(Incident.ward), joinedload(Incident.work_orders))
        .where(Incident.id == incident_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def review_incident(db: Session, incident: Incident, actor: User, note: str = "") -> Incident:
    if incident.merged_into_id:
        raise HTTPException(409, "Merged reports cannot be reviewed")
    if incident.status not in {"open", "reviewing"}:
        raise HTTPException(409, f"Incident cannot be reviewed from status '{incident.status}'")
    if incident.status != "reviewing":
        incident.previous_hash = incident.audit_hash
        incident.status = "reviewing"
        incident.reviewed_by = actor.id
        incident.reviewed_at = utcnow()
        stamp_hash(incident)
        db.add(incident)
        record_audit(
            db, actor=actor, action="incident.reviewed", entity_type="incident", entity_id=str(incident.id),
            details={"note": note[:2000], "status": "reviewing"}, commit=False,
        )
        record_audit(
            db, actor=actor, action="incident.status_changed", entity_type="incident", entity_id=str(incident.id),
            details={"from": "open", "to": "reviewing", "note": note[:2000]}, commit=False,
        )
        db.commit()
        db.refresh(incident)
    return incident


CREWS = [
    "Night Patch Unit A",
    "Night Patch Unit B",
    "Milling Crew 3",
    "Emergency Pothole Response",
]


def next_ticket_no(db: Session) -> str:
    # Random suffix avoids count-based collisions under concurrent dispatches.
    return f"WO-{utcnow().year}-{uuid4().hex[:8].upper()}"


def auto_dispatch(db: Session, incident: Incident, actor: User) -> WorkOrder:
    existing = db.execute(
        select(WorkOrder).where(WorkOrder.incident_id == incident.id).order_by(WorkOrder.dispatched_at.desc())
    ).scalars().first()
    if existing and incident.status in {"dispatched", "in_progress", "resolved"}:
        return existing
    if incident.status != "reviewing":
        raise HTTPException(409, "Review the defect before creating a repair work order")
    if incident.merged_into_id:
        raise HTTPException(409, "Merged reports cannot be dispatched")

    incident.previous_hash = incident.audit_hash
    incident.status = "dispatched"
    stamp_hash(incident)
    crew = CREWS[incident.hit_count % len(CREWS)]
    order = WorkOrder(
        ticket_no=next_ticket_no(db),
        incident_id=incident.id,
        status="dispatched",
        crew=crew,
        created_by=actor.id,
        notes=f"Auto-routed from {incident.severity} defect at {incident.lat:.5f},{incident.lon:.5f}. "
        f"Depth {incident.depth_mm:.1f} mm; estimated volume {incident.estimated_volume_m3:.4f} m3.",
    )
    db.add(order)
    db.add(incident)
    db.flush()
    record_audit(
        db, actor=actor, action="work_order.dispatched", entity_type="work_order", entity_id=str(order.id),
        details={"ticket_no": order.ticket_no, "incident_id": str(incident.id), "crew": crew}, commit=False,
    )
    record_audit(
        db, actor=actor, action="incident.status_changed", entity_type="incident", entity_id=str(incident.id),
        details={"from": "reviewing", "to": "dispatched", "work_order_id": str(order.id)}, commit=False,
    )
    db.commit()
    db.refresh(order)
    db.refresh(incident)
    return order


def update_work_order(db: Session, order: WorkOrder, payload: WorkOrderUpdateIn, actor: User) -> WorkOrder:
    allowed_transitions = {
        "dispatched": {"dispatched", "in_progress", "cancelled"},
        "in_progress": {"in_progress", "resolved", "cancelled"},
        "resolved": {"resolved"},
        "cancelled": {"cancelled"},
    }
    # Engineers may use the audited quick-action to close out a dispatched ticket directly.
    if actor.role == "engineer":
        allowed_transitions["dispatched"].add("resolved")
    changes: dict[str, dict[str, object]] = {}
    previous_incident_status = order.incident.status if order.incident else None
    for field in ("crew", "notes", "completion_notes", "evidence_url"):
        value = getattr(payload, field)
        if value is not None and value != getattr(order, field):
            changes[field] = {"from": getattr(order, field), "to": value}
            setattr(order, field, value)
    if "assigned_to_id" in payload.model_fields_set:
        assigned = db.get(User, payload.assigned_to_id) if payload.assigned_to_id else None
        if payload.assigned_to_id and (not assigned or assigned.role != "worker" or not assigned.is_active):
            raise HTTPException(422, "assigned_to_id must identify an active worker account")
        if order.assigned_to_id != payload.assigned_to_id:
            changes["assigned_to_id"] = {"from": str(order.assigned_to_id or ""), "to": str(payload.assigned_to_id or "")}
            order.assigned_to_id = payload.assigned_to_id
    now = utcnow()
    if payload.status is not None and payload.status != order.status:
        if payload.status not in allowed_transitions[order.status]:
            raise HTTPException(409, f"Invalid work-order transition: {order.status} -> {payload.status}")
        if payload.status == "resolved" and not (order.evidence_url or order.completion_notes.strip() or order.evidence_files):
            raise HTTPException(422, "Repair close-out requires completion notes or an evidence URL")
        changes["status"] = {"from": order.status, "to": payload.status}
        order.status = payload.status
        if payload.status == "resolved":
            order.completed_at = now
            order.incident.previous_hash = order.incident.audit_hash
            order.incident.status = "awaiting_verification"
            order.incident.verification_status = "pending"
            order.incident.verification_passes = 0
            order.incident.verification_last_at = None
            order.incident.verified_at = None
            order.incident.verification_cycle = (order.incident.verification_cycle or 0) + 1
            stamp_hash(order.incident)
        elif payload.status == "in_progress":
            order.incident.previous_hash = order.incident.audit_hash
            order.incident.status = "in_progress"
            stamp_hash(order.incident)
        elif payload.status == "cancelled":
            order.incident.previous_hash = order.incident.audit_hash
            order.incident.status = "open"
            order.incident.verification_status = "not_required"
            order.incident.verification_passes = 0
            order.incident.verification_last_at = None
            order.incident.verified_at = None
            stamp_hash(order.incident)
    if not changes:
        return order
    order.updated_at = now
    db.add(order)
    db.add(order.incident)
    record_audit(
        db, actor=actor, action="work_order.updated", entity_type="work_order", entity_id=str(order.id),
        details={"ticket_no": order.ticket_no, "changes": changes}, commit=False,
    )
    if "status" in changes:
        record_audit(
            db, actor=actor, action="work_order.status_changed", entity_type="work_order", entity_id=str(order.id),
            details={"ticket_no": order.ticket_no, **changes["status"]}, commit=False,
        )
    if order.incident and order.incident.status != previous_incident_status:
        record_audit(
            db, actor=actor, action="incident.status_changed", entity_type="incident", entity_id=str(order.incident.id),
            details={"from": previous_incident_status, "to": order.incident.status, "work_order_id": str(order.id)}, commit=False,
        )
    db.commit()
    db.refresh(order)
    return order


def merge_incidents(db: Session, primary: Incident, duplicate: Incident, actor: User, note: str) -> Incident:
    if primary.id == duplicate.id:
        raise HTTPException(422, "A report cannot be merged into itself")
    if primary.merged_into_id or duplicate.merged_into_id:
        raise HTTPException(409, "An already-merged report cannot be merged again")
    if primary.status not in {"open", "reviewing"} or duplicate.status not in {"open", "reviewing"}:
        raise HTTPException(409, "Only un-dispatched reports can be merged")
    if primary.severity != duplicate.severity:
        raise HTTPException(409, "Reports must have the same severity to merge")
    distance = haversine_m(primary.lon, primary.lat, duplicate.lon, duplicate.lat)
    if distance > settings.manual_merge_max_meters:
        raise HTTPException(422, f"Reports are {distance:.1f} m apart; the manual merge limit is {settings.manual_merge_max_meters:.0f} m")
    if primary.work_orders or duplicate.work_orders:
        raise HTTPException(409, "Reports with existing work orders cannot be merged")

    previous_primary = primary.audit_hash
    previous_duplicate = duplicate.audit_hash
    primary.previous_hash = previous_primary
    primary.hit_count += duplicate.hit_count
    primary.depth_mm = max(primary.depth_mm, duplicate.depth_mm)
    primary.estimated_volume_m3 = estimate_volume_m3(primary.depth_mm, primary.severity)
    if duplicate.observed_at > primary.observed_at:
        primary.observed_at = duplicate.observed_at
    duplicate.previous_hash = previous_duplicate
    duplicate.merged_into_id = primary.id
    duplicate.status = "resolved"
    # Replays of any absorbed event should resolve to the canonical incident.
    db.execute(update(EventReceipt).where(EventReceipt.incident_id == duplicate.id).values(incident_id=primary.id))
    stamp_hash(primary)
    stamp_hash(duplicate)
    db.add_all([primary, duplicate])
    record_audit(
        db, actor=actor, action="incident.merged", entity_type="incident", entity_id=str(primary.id),
        details={"merged_incident_id": str(duplicate.id), "distance_m": round(distance, 2), "note": note}, commit=False,
    )
    record_audit(
        db, actor=actor, action="incident.status_changed", entity_type="incident", entity_id=str(duplicate.id),
        details={"from": "open_or_reviewing", "to": "resolved", "merged_into_id": str(primary.id)}, commit=False,
    )
    db.commit()
    db.refresh(primary)
    return primary
