from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_additive_columns() -> bool:
    """Add fields introduced after the first MVP schema without destroying existing data."""
    dialect = engine.dialect.name
    uuid_type = "UUID" if dialect == "postgresql" else "CHAR(32)"
    columns = {
        "users": {"token_version": "INTEGER NOT NULL DEFAULT 0"},
        "vehicles": {
            "last_seen_at": "TIMESTAMP NULL",
            "power_status": "VARCHAR(24) NOT NULL DEFAULT 'unknown'",
            "connectivity_status": "VARCHAR(24) NOT NULL DEFAULT 'offline'",
            "software_version": "VARCHAR(64) NOT NULL DEFAULT 'edge-0.1.0'",
            "last_error": "VARCHAR(256) NULL",
            "device_key_hash": "VARCHAR(64) NULL",
        },
        "incidents": {
            "verification_passes": "INTEGER NOT NULL DEFAULT 0",
            "verification_last_at": "TIMESTAMP NULL",
            "verified_at": "TIMESTAMP NULL",
            "verification_status": "VARCHAR(32) NOT NULL DEFAULT 'not_required'",
            "verification_cycle": "INTEGER NOT NULL DEFAULT 0",
            "reviewed_by": f"{uuid_type} NULL",
            "reviewed_at": "TIMESTAMP NULL",
            "merged_into_id": f"{uuid_type} NULL",
        },
        "event_receipts": {"payload_hash": "VARCHAR(64) NULL"},
        "work_orders": {
            "evidence_url": "VARCHAR(2048) NULL",
            "completion_notes": "TEXT NOT NULL DEFAULT ''",
            "created_by": f"{uuid_type} NULL",
            "assigned_to_id": f"{uuid_type} NULL",
            "updated_at": "TIMESTAMP NULL",
            "completed_at": "TIMESTAMP NULL",
        },
    }
    inspector = inspect(engine)
    altered = False
    for table, desired in columns.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, definition in desired.items():
            if name not in existing:
                with engine.begin() as connection:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
                altered = True
    return altered



def _migrate_two_roles(db: Session) -> None:
    """Normalize legacy roles and remove deprecated accounts without losing audit/work history."""
    from sqlalchemy import select, update
    from app.models import AuditLog, Incident, User, WorkOrder, WorkOrderEvidence
    from app.services.audit import record_audit

    legacy_engineers = db.execute(select(User).where(User.role == "municipal_engineer")).scalars().all()
    for user in legacy_engineers:
        user.role = "engineer"
        user.token_version += 1
        db.add(user)
    db.flush()

    # Remove both deprecated roles and well-known legacy/demo accounts, even if an old
    # account happened to be manually relabeled as Engineer or Worker.
    legacy_names = {"admin", "administrator", "fleet", "fleetmanager", "fleet_manager", "fleet-manager", "contractor", "contractor1"}
    candidates = db.execute(select(User)).scalars().all()
    legacy_users = [
        user for user in candidates
        if user.role not in {"engineer", "worker"}
        or user.username.strip().lower().replace(" ", "_") in legacy_names
    ]
    removed_ids = [user.id for user in legacy_users]
    if removed_ids:
        db.execute(update(WorkOrder).where(WorkOrder.assigned_to_id.in_(removed_ids)).values(assigned_to_id=None))
        db.execute(update(WorkOrder).where(WorkOrder.created_by.in_(removed_ids)).values(created_by=None))
        db.execute(update(Incident).where(Incident.reviewed_by.in_(removed_ids)).values(reviewed_by=None))
        db.execute(update(AuditLog).where(AuditLog.actor_id.in_(removed_ids)).values(actor_id=None))
        db.execute(update(WorkOrderEvidence).where(WorkOrderEvidence.uploaded_by_id.in_(removed_ids)).values(uploaded_by_id=None))
        for user in legacy_users:
            db.delete(user)

    changed = bool(legacy_engineers or legacy_users)
    if changed:
        record_audit(
            db, actor=None, actor_label="system-role-migration", action="auth.legacy_roles_removed",
            entity_type="user", entity_id="role-migration",
            details={"renamed_to_engineer": len(legacy_engineers), "deprecated_accounts_removed": len(legacy_users),
                     "work_order_assignments_cleared": len(removed_ids)}, commit=False,
        )
        db.commit()


def init_db() -> None:
    if settings.use_postgis:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Operational data is only accessed through the FastAPI service. Turn on RLS with no
    # anon/authenticated policies so the browser's Supabase public key cannot read tables
    # directly. The trusted backend uses the database owner connection and continues to work.
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for table_name in Base.metadata.tables.keys():
                safe_name = table_name.replace('"', '""')
                conn.execute(text(f'ALTER TABLE public."{safe_name}" ENABLE ROW LEVEL SECURITY'))
    altered = _migrate_additive_columns()
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_merged_into_id ON incidents (merged_into_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_work_orders_assigned_to_id ON work_orders (assigned_to_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vehicles_last_seen_at ON vehicles (last_seen_at)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicles_device_key_hash ON vehicles (device_key_hash)"))
    if settings.use_postgis:
        # This functional GiST index keeps geography-based radius queries viable as the fleet grows.
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_incidents_geography_location "
                "ON incidents USING GIST ((geography(ST_SetSRID(ST_MakePoint(lon, lat), 4326))))"
            ))

    from app.models import Incident
    from app.services.audit import verify_incident
    from app.services.spatial import stamp_hash

    with SessionLocal() as db:
        if altered:
            rows = db.query(Incident).all()
            rehashed = 0
            for row in rows:
                if not verify_incident(row):
                    row.previous_hash = row.audit_hash
                    stamp_hash(row)
                    rehashed += 1
            if rehashed:
                db.commit()
                record_audit(
                    db, actor=None, actor_label="schema-migration", action="schema.incident_hash_upgraded",
                    entity_type="database", entity_id="incidents", details={"records_rehashed": rehashed},
                )
        _migrate_two_roles(db)
