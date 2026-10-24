import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('engineer', 'worker')", name="ck_users_role_allowed"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    geom_wkt: Mapped[str] = mapped_column(Text)

    incidents: Mapped[list["Incident"]] = relationship(back_populates="ward")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fleet_id: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(64), unique=True)
    route_id: Mapped[str] = mapped_column(String(32), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    power_status: Mapped[str] = mapped_column(String(24), default="unknown")
    connectivity_status: Mapped[str] = mapped_column(String(24), default="offline")
    software_version: Mapped[str] = mapped_column(String(64), default="edge-0.1.0")
    last_error: Mapped[str | None] = mapped_column(String(256), nullable=True)
    device_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    incidents: Mapped[list["Incident"]] = relationship(back_populates="vehicle")
    telemetry: Mapped[list["TelemetryPing"]] = relationship(back_populates="vehicle")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("vehicles.id"))
    ward_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("wards.id"))
    route_id: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="open")
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    geom_wkt: Mapped[str] = mapped_column(Text)
    depth_mm: Mapped[float] = mapped_column(Float)
    estimated_volume_m3: Mapped[float] = mapped_column(Float)
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    audit_hash: Mapped[str] = mapped_column(String(64), index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sensor_log: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    vehicle: Mapped[Vehicle | None] = relationship(back_populates="incidents")
    ward: Mapped[Ward | None] = relationship(back_populates="incidents")
    verification_passes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification_last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="not_required", nullable=False)
    verification_cycle: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="incident")
    verifications: Mapped[list["IncidentVerification"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentVerification.observed_at.desc()"
    )


class IncidentVerification(Base):
    """A durable record of a distinct bus inspecting a repaired road location."""
    __tablename__ = "incident_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("vehicles.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cycle: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    result: Mapped[str] = mapped_column(String(24), index=True)  # clear | defect_found
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    depth_mm: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="clear", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    incident: Mapped[Incident] = relationship(back_populates="verifications")
    vehicle: Mapped[Vehicle] = relationship()


class EventReceipt(Base):
    __tablename__ = "event_receipts"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidents.id"), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("incidents.id"))
    status: Mapped[str] = mapped_column(String(32), index=True, default="dispatched")
    crew: Mapped[str] = mapped_column(String(64), default="Night Patch Unit")
    notes: Mapped[str] = mapped_column(Text, default="")
    evidence_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    completion_notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_user: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id])
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[Incident] = relationship(back_populates="work_orders")
    evidence_files: Mapped[list["WorkOrderEvidence"]] = relationship(back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderEvidence.created_at.desc()")


class WorkOrderEvidence(Base):
    __tablename__ = "work_order_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    work_order: Mapped[WorkOrder] = relationship(back_populates="evidence_files")


class TelemetryPing(Base):
    __tablename__ = "telemetry_pings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("vehicles.id"))
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    engine_status: Mapped[str] = mapped_column(String(32))
    sensor_log: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    vehicle: Mapped[Vehicle] = relationship(back_populates="telemetry")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(96))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_hash: Mapped[str] = mapped_column(String(64), index=True)


class AuditHead(Base):
    __tablename__ = "audit_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
