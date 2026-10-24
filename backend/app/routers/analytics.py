from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from datetime import timedelta

from app.config import settings
from app.database import get_db
from app.models import Incident, User, Vehicle, Ward, WorkOrder
from app.schemas import AnalyticsSummary, WardSummary
from app.services.auth import require_roles
from app.services.spatial import utcnow

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def summary(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    rows = db.execute(
        select(
            func.count(Incident.id),
            func.coalesce(func.sum(case((Incident.severity == "critical", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.severity == "moderate", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.severity == "clear", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.status == "open", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.status == "dispatched", 1), else_=0)), 0),
            func.coalesce(func.avg(Incident.depth_mm), 0),
        ).where(Incident.merged_into_id.is_(None))
    ).one()
    wo = db.execute(select(func.count(WorkOrder.id))).scalar_one()
    online_cutoff = utcnow() - timedelta(minutes=settings.device_offline_minutes)
    online = db.execute(select(func.count(Vehicle.id)).where(Vehicle.last_seen_at >= online_cutoff)).scalar_one()
    return AnalyticsSummary(
        incidents=int(rows[0] or 0),
        critical=int(rows[1] or 0),
        moderate=int(rows[2] or 0),
        clear=int(rows[3] or 0),
        open=int(rows[4] or 0),
        dispatched=int(rows[5] or 0),
        work_orders=int(wo or 0),
        fleet_online=int(online),
        avg_depth_mm=round(float(rows[6] or 0), 2),
    )


@router.get("/wards", response_model=list[WardSummary])
def wards(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    stmt = (
        select(
            Ward.code,
            Ward.name,
            func.count(Incident.id),
            func.coalesce(func.sum(case((Incident.severity == "critical", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.severity == "moderate", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.severity == "clear", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Incident.status.in_(["open", "reviewing"]), 1), else_=0)), 0),
            func.coalesce(func.avg(Incident.depth_mm), 0),
        )
        .outerjoin(Incident, (Incident.ward_id == Ward.id) & Incident.merged_into_id.is_(None))
        .group_by(Ward.code, Ward.name)
        .order_by(Ward.code)
    )
    out = []
    for row in db.execute(stmt):
        out.append(
            WardSummary(
                ward_code=row[0],
                ward_name=row[1],
                total=int(row[2] or 0),
                critical=int(row[3] or 0),
                moderate=int(row[4] or 0),
                clear=int(row[5] or 0),
                open_tickets=int(row[6] or 0),
                avg_depth_mm=round(float(row[7] or 0), 2),
            )
        )
    return out


@router.get("/heatmap")
def heatmap(db: Session = Depends(get_db), _: User = Depends(require_roles("engineer"))):
    rows = db.execute(select(Incident).where(Incident.merged_into_id.is_(None))).scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row.lon, row.lat]},
                "properties": {
                    "id": str(row.id),
                    "severity": row.severity,
                    "status": row.status,
                    "depth_mm": row.depth_mm,
                    "route_id": row.route_id,
                    "hit_count": row.hit_count,
                    "weight": {"critical": 3, "moderate": 2, "clear": 0.6}.get(row.severity, 1),
                },
            }
            for row in rows
        ],
    }
