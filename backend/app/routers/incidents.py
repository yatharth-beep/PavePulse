from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    DispatchResponse, IncidentOut, IncidentQuickStatusIn, IncidentStatusUpdateIn, MergeIncidentIn, WorkOrderOut, WorkOrderUpdateIn,
)
from app.services.auth import require_roles
from app.services.incidents import (
    auto_dispatch, get_incident, list_incidents, merge_incidents, review_incident, serialize_incident, update_work_order,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def incidents(
    ward: str | None = Query(None, max_length=32),
    route: str | None = Query(None, max_length=32),
    status: str | None = Query(None, pattern=r"^(open|reviewing|dispatched|in_progress|awaiting_verification|verified_fixed|resolved)$"),
    severity: str | None = Query(None, pattern=r"^(critical|moderate|clear)$"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("engineer")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    rows = list_incidents(
        db, ward=ward or None, route=route or None, status=status or None, severity=severity or None,
        date_from=date_from, date_to=date_to,
    )
    return [serialize_incident(row) for row in rows]


@router.get("/{incident_id}", response_model=IncidentOut)
def incident_detail(incident_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    row = get_incident(db, incident_id)
    if not row or row.merged_into_id:
        raise HTTPException(404, "Incident not found")
    return serialize_incident(row)


@router.post("/{incident_id}/review", response_model=IncidentOut)
def review(
    incident_id: UUID,
    payload: IncidentStatusUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    row = get_incident(db, incident_id)
    if not row:
        raise HTTPException(404, "Incident not found")
    if payload.status != "reviewing":
        raise HTTPException(422, "Review action must set status to 'reviewing'")
    row = review_incident(db, row, actor, payload.note)
    row = get_incident(db, row.id)
    return serialize_incident(row)


@router.post("/{incident_id}/merge", response_model=IncidentOut)
def merge(
    incident_id: UUID,
    payload: MergeIncidentIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    primary = get_incident(db, incident_id)
    duplicate = get_incident(db, payload.duplicate_id)
    if not primary or not duplicate:
        raise HTTPException(404, "Incident not found")
    row = merge_incidents(db, primary, duplicate, actor, payload.note)
    return serialize_incident(get_incident(db, row.id))


@router.post("/{incident_id}/dispatch", response_model=DispatchResponse)
def dispatch(
    incident_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    row = get_incident(db, incident_id)
    if not row or row.merged_into_id:
        raise HTTPException(404, "Incident not found")
    order = auto_dispatch(db, row, actor)
    row = get_incident(db, incident_id)
    return {
        "incident": serialize_incident(row),
        "work_order": WorkOrderOut(
            id=order.id,
            ticket_no=order.ticket_no,
            incident_id=order.incident_id,
            status=order.status,
            crew=order.crew,
            notes=order.notes,
            evidence_url=order.evidence_url,
            completion_notes=order.completion_notes,
            dispatched_at=order.dispatched_at,
            updated_at=order.updated_at,
            completed_at=order.completed_at,
            severity=row.severity,
            ward_name=row.ward.name if row.ward else None,
            incident_route=row.route_id,
        ),
    }


@router.patch("/{incident_id}/status", response_model=IncidentOut)
def quick_status(
    incident_id: UUID,
    payload: IncidentQuickStatusIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer")),
):
    """Engineer one-click action that updates both the work order and its parent incident."""
    incident = get_incident(db, incident_id)
    if not incident or incident.merged_into_id:
        raise HTTPException(404, "Incident not found")
    active_orders = [item for item in incident.work_orders if item.status != "cancelled"]
    order = max(active_orders, key=lambda item: item.dispatched_at, default=None)
    if not order:
        raise HTTPException(409, "Dispatch a work order before changing repair status")

    previous_status = incident.status
    note = payload.note.strip()
    if payload.status == "in_progress":
        if order.status not in {"dispatched", "in_progress"}:
            raise HTTPException(409, f"Cannot start a work order in status '{order.status}'")
        update_work_order(db, order, WorkOrderUpdateIn(status="in_progress"), actor)
    else:
        if order.status not in {"dispatched", "in_progress", "resolved"}:
            raise HTTPException(409, f"Cannot resolve a work order in status '{order.status}'")
        # A one-click engineer override remains explicit in the permanent history when field evidence is absent.
        closeout = note or "Engineer quick action: marked resolved; field evidence was not submitted through this action."
        update_work_order(
            db, order,
            WorkOrderUpdateIn(status="resolved", completion_notes=closeout), actor,
        )
    refreshed = get_incident(db, incident_id)
    record_audit(
        db, actor=actor, action="incident.quick_status_action", entity_type="incident", entity_id=str(incident_id),
        details={"from": previous_status, "to": refreshed.status, "note": note, "work_order_id": str(order.id)},
    )
    return serialize_incident(get_incident(db, incident_id))
