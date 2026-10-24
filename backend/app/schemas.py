from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Severity = Literal["critical", "moderate", "clear"]
IncidentStatus = Literal["open", "reviewing", "dispatched", "in_progress", "awaiting_verification", "verified_fixed", "resolved"]
WorkOrderStatus = Literal["dispatched", "in_progress", "resolved", "cancelled"]
UserRole = Literal["engineer", "worker"]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=14, max_length=256)


class CreateUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=14, max_length=256)
    role: UserRole


class SensorLog(BaseModel):
    accel_z: float | None = Field(default=None, ge=-100, le=100)
    rms_vibration: float | None = Field(default=None, ge=0, le=1000)
    ir_reflectance: float | None = Field(default=None, ge=0, le=1)
    depth_mm: float | None = Field(default=None, ge=0, le=1000)
    surface_class: str | None = Field(default=None, max_length=64)

    model_config = ConfigDict(extra="forbid")


class EdgeEventIn(BaseModel):
    event_id: str = Field(min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    vehicle_label: str = Field(min_length=1, max_length=64)
    route_id: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    timestamp: datetime
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    speed_kmh: float = Field(default=0, ge=0, le=250)
    engine_status: str = Field(default="ok", max_length=32)
    sensors: SensorLog = Field(default_factory=SensorLog)
    severity: Severity | None = None
    ward_code: str | None = Field(default=None, max_length=32)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_vehicle_and_route(self):
        self.vehicle_label = self.vehicle_label.strip().upper()
        self.route_id = self.route_id.strip().upper()
        if not self.vehicle_label:
            raise ValueError("vehicle_label cannot be blank")
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude outside valid range")
        return self


class IncidentOut(BaseModel):
    id: UUID
    source_event_id: str
    vehicle_label: str | None = None
    ward_code: str | None = None
    ward_name: str | None = None
    route_id: str
    severity: str
    status: str
    lon: float
    lat: float
    depth_mm: float
    estimated_volume_m3: float
    hit_count: int
    observed_at: datetime
    audit_hash: str
    previous_hash: str | None = None
    sensor_log: dict[str, Any]
    work_order_ticket: str | None = None
    hash_valid: bool = True
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    merged_into_id: UUID | None = None
    verification_passes: int = 0
    verification_required: int = 2
    verification_last_at: datetime | None = None
    verified_at: datetime | None = None
    verification_status: str = "not_required"
    verification_cycle: int = 0

    model_config = ConfigDict(from_attributes=True)


class WorkOrderEvidenceOut(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    download_url: str

    model_config = ConfigDict(from_attributes=True)


class WorkOrderOut(BaseModel):
    id: UUID
    ticket_no: str
    incident_id: UUID
    status: str
    crew: str
    notes: str
    evidence_url: str | None = None
    completion_notes: str = ""
    dispatched_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    assigned_to_id: UUID | None = None
    assigned_to_username: str | None = None
    severity: str | None = None
    ward_name: str | None = None
    incident_route: str | None = None
    incident_status: str | None = None
    verification_status: str | None = None
    verification_passes: int = 0
    verification_required: int = 2
    verified_at: datetime | None = None
    evidence_files: list[WorkOrderEvidenceOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WorkOrderUpdateIn(BaseModel):
    status: WorkOrderStatus | None = None
    crew: str | None = Field(default=None, min_length=2, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    completion_notes: str | None = Field(default=None, max_length=4000)
    evidence_url: str | None = Field(default=None, max_length=2048)
    assigned_to_id: UUID | None = None

    @field_validator("evidence_url")
    @classmethod
    def evidence_url_must_be_http(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("evidence_url must be an absolute HTTP(S) URL")
        return value


class IncidentStatusUpdateIn(BaseModel):
    status: Literal["reviewing"]
    note: str = Field(default="", max_length=2000)


class IncidentQuickStatusIn(BaseModel):
    status: Literal["in_progress", "resolved"]
    note: str = Field(default="", max_length=2000)


class MergeIncidentIn(BaseModel):
    duplicate_id: UUID
    note: str = Field(default="Manual duplicate merge", max_length=500)


class UserOut(BaseModel):
    id: UUID
    username: str
    role: str
    is_active: bool


class CreateVehicleIn(BaseModel):
    vehicle_label: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    fleet_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    route_id: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    software_version: str = Field(default="edge-0.1.0", min_length=1, max_length=64)

    @field_validator("vehicle_label", "fleet_id", "route_id")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class DeviceHealthOut(BaseModel):
    vehicle_label: str
    fleet_id: str
    route_id: str
    power_status: str
    connectivity_status: str
    last_seen_at: datetime | None
    software_version: str
    last_error: str | None
    credential_configured: bool = False


class AuditLogOut(BaseModel):
    id: int
    actor_label: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    created_at: datetime
    previous_hash: str | None
    audit_hash: str

    model_config = ConfigDict(from_attributes=True)


class TelemetryOut(BaseModel):
    vehicle_label: str
    route_id: str
    lon: float
    lat: float
    speed_kmh: float
    engine_status: str
    sensor_log: dict[str, Any]
    observed_at: datetime


class WardSummary(BaseModel):
    ward_code: str
    ward_name: str
    total: int
    critical: int
    moderate: int
    clear: int
    open_tickets: int
    avg_depth_mm: float


class AnalyticsSummary(BaseModel):
    incidents: int
    critical: int
    moderate: int
    clear: int
    open: int
    dispatched: int
    work_orders: int
    fleet_online: int
    avg_depth_mm: float


class DispatchResponse(BaseModel):
    incident: IncidentOut
    work_order: WorkOrderOut
