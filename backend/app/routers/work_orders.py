from uuid import UUID, uuid4
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Incident, User, WorkOrder, WorkOrderEvidence
from app.schemas import WorkOrderEvidenceOut, WorkOrderOut, WorkOrderUpdateIn
from app.services.auth import require_roles
from app.services.audit import record_audit
from app.services.incidents import update_work_order

router = APIRouter(prefix="/api/v1/work-orders", tags=["work-orders"])


def serialize_order(row: WorkOrder) -> WorkOrderOut:
    return WorkOrderOut(
        id=row.id,
        ticket_no=row.ticket_no,
        incident_id=row.incident_id,
        status=row.status,
        crew=row.crew,
        notes=row.notes,
        evidence_url=row.evidence_url,
        completion_notes=row.completion_notes,
        dispatched_at=row.dispatched_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        assigned_to_id=row.assigned_to_id,
        assigned_to_username=row.assigned_to_user.username if row.assigned_to_user else None,
        severity=row.incident.severity if row.incident else None,
        ward_name=row.incident.ward.name if row.incident and row.incident.ward else None,
        incident_route=row.incident.route_id if row.incident else None,
        incident_status=row.incident.status if row.incident else None,
        verification_status=row.incident.verification_status if row.incident else None,
        verification_passes=row.incident.verification_passes if row.incident else 0,
        verification_required=settings.verification_required_buses,
        verified_at=row.incident.verified_at if row.incident else None,
        evidence_files=[
            WorkOrderEvidenceOut(
                id=item.id, original_filename=item.original_filename, content_type=item.content_type,
                size_bytes=item.size_bytes, created_at=item.created_at,
                download_url=f"/api/v1/work-orders/{row.id}/evidence/{item.id}",
            ) for item in row.evidence_files
        ],
    )


@router.get("", response_model=list[WorkOrderOut])
def list_work_orders(db: Session = Depends(get_db), actor: User = Depends(require_roles("engineer", "worker"))):
    stmt = (
        select(WorkOrder)
        .options(joinedload(WorkOrder.incident).joinedload(Incident.ward), joinedload(WorkOrder.assigned_to_user))
        .order_by(WorkOrder.dispatched_at.desc())
    )
    if actor.role == "worker":
        stmt = stmt.where(WorkOrder.assigned_to_id == actor.id)
    rows = db.execute(stmt).unique().scalars().all()
    return [serialize_order(row) for row in rows]


@router.patch("/{work_order_id}", response_model=WorkOrderOut)
def patch_work_order(
    work_order_id: UUID,
    payload: WorkOrderUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer", "worker")),
):
    row = db.execute(
        select(WorkOrder).options(joinedload(WorkOrder.incident).joinedload(Incident.ward), joinedload(WorkOrder.assigned_to_user))
        .where(WorkOrder.id == work_order_id)
    ).unique().scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Work order not found")
    if actor.role == "worker":
        if row.assigned_to_id != actor.id:
            raise HTTPException(403, "This work order is not assigned to your account")
        if row.status in {"resolved", "cancelled"}:
            raise HTTPException(409, "Closed work orders cannot be changed by a worker")
        if any(field in payload.model_fields_set for field in ("crew", "notes", "assigned_to_id")):
            raise HTTPException(403, "Workers can only update status and close-out evidence")
        if payload.status not in {None, "in_progress", "resolved"}:
            raise HTTPException(403, "Workers can only start or complete assigned repair work")
    updated = update_work_order(db, row, payload, actor)
    refreshed = db.execute(
        select(WorkOrder).options(joinedload(WorkOrder.incident).joinedload(Incident.ward), joinedload(WorkOrder.assigned_to_user))
        .where(WorkOrder.id == updated.id)
    ).unique().scalar_one()
    return serialize_order(refreshed)



MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
_ALLOWED_SIGNATURES = (
    ("image/png", ".png", lambda raw: raw.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", ".jpg", lambda raw: raw.startswith(b"\xff\xd8\xff")),
    ("application/pdf", ".pdf", lambda raw: raw.startswith(b"%PDF-")),
)


def _get_accessible_order(db: Session, work_order_id: UUID, actor: User) -> WorkOrder | None:
    row = db.execute(
        select(WorkOrder)
        .options(joinedload(WorkOrder.incident).joinedload(Incident.ward), joinedload(WorkOrder.assigned_to_user))
        .where(WorkOrder.id == work_order_id)
    ).unique().scalar_one_or_none()
    if not row or (actor.role == "worker" and row.assigned_to_id != actor.id):
        return None
    return row


@router.post("/{work_order_id}/evidence", response_model=WorkOrderOut, status_code=201)
async def upload_evidence(
    work_order_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer", "worker")),
):
    order = _get_accessible_order(db, work_order_id, actor)
    if not order:
        raise HTTPException(404, "Work order not found")
    if actor.role == "worker" and order.status in {"resolved", "cancelled"}:
        raise HTTPException(409, "Closed work orders cannot accept new evidence")

    content = await file.read(MAX_EVIDENCE_BYTES + 1)
    if not content:
        raise HTTPException(422, "Evidence file is empty")
    if len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(413, "Evidence files must be 5 MB or smaller")
    signature = next((item for item in _ALLOWED_SIGNATURES if item[2](content)), None)
    if not signature:
        raise HTTPException(415, "Only PNG, JPEG, and PDF evidence files are accepted")
    content_type, extension, _ = signature
    raw_name = (file.filename or "evidence").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_name).strip(" .")[:240] or f"evidence{extension}"
    storage_key = f"{uuid4().hex}{extension}"
    storage_dir = Path(settings.evidence_storage_dir).expanduser().resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / storage_key
    stored_path.write_bytes(content)
    row = WorkOrderEvidence(
        work_order_id=order.id, uploaded_by_id=actor.id, storage_key=storage_key,
        original_filename=safe_name, content_type=content_type, size_bytes=len(content),
    )
    try:
        db.add(row)
        db.flush()
        record_audit(
            db, actor=actor, action="work_order.evidence_uploaded", entity_type="work_order", entity_id=str(order.id),
            details={"evidence_id": str(row.id), "filename": safe_name, "content_type": content_type, "size_bytes": len(content)},
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise
    refreshed = _get_accessible_order(db, order.id, actor)
    return serialize_order(refreshed)


@router.get("/{work_order_id}/evidence/{evidence_id}")
def download_evidence(
    work_order_id: UUID,
    evidence_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("engineer", "worker")),
):
    order = _get_accessible_order(db, work_order_id, actor)
    if not order:
        raise HTTPException(404, "Work order not found")
    evidence = db.execute(
        select(WorkOrderEvidence).where(WorkOrderEvidence.id == evidence_id, WorkOrderEvidence.work_order_id == order.id)
    ).scalar_one_or_none()
    if not evidence:
        raise HTTPException(404, "Evidence not found")
    storage_dir = Path(settings.evidence_storage_dir).expanduser().resolve()
    path = (storage_dir / evidence.storage_key).resolve()
    if path.parent != storage_dir or not path.is_file():
        raise HTTPException(404, "Evidence file is unavailable")
    return FileResponse(
        path, media_type=evidence.content_type, filename=evidence.original_filename,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
