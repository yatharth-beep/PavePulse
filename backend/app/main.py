from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, engine, init_db
from app.geo import ROUTES, WARDS
from app.routers import analytics, auth, events, incidents, telemetry, work_orders
from app.seed import seed_demo_data_if_empty, seed_if_empty, seed_reference_data, seed_users
from app.services.simulator import simulator


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        if settings.demo_data_enabled:
            seed_demo_data_if_empty(db)
        elif settings.seed_on_startup:
            seed_if_empty(db)
        else:
            seed_reference_data(db, include_demo_fleet=False)
            seed_users(db)
    finally:
        db.close()
    if settings.simulator_enabled:
        simulator.start()
    try:
        yield
    finally:
        simulator.stop()


app = FastAPI(
    title="PavePulse API",
    description="Pune road-condition monitoring, incident review, repair work orders, device health, and independent repair verification.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(auth.router)
app.include_router(events.router)
app.include_router(incidents.router)
app.include_router(work_orders.router)
app.include_router(telemetry.router)
app.include_router(analytics.router)


@app.get("/api/v1/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "service": "pavepulse", "database": "unavailable"})
    return {"status": "ok", "service": "pavepulse", "database": "ok"}


@app.head("/api/v1/health")
def health_head():
    """Lightweight health check for monitors that use HTTP HEAD by default."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return Response(status_code=503)
    return Response(status_code=200)


@app.get("/api/v1/meta")
def meta():
    return {
        "name": "PavePulse",
        "city": "Pune, Maharashtra, India",
        "demo_dataset_label": "Illustrative Pune road-condition samples" if settings.demo_data_enabled else None,
        "modules": ["gis-heatmap", "incidents", "work-orders", "device-health", "team-access", "repair-verification"],
        "spatial_dedup_meters": settings.spatial_dedup_meters,
        "wards": [{"code": w["code"], "name": w["name"]} for w in WARDS],
        "routes": list(ROUTES.keys()),
        "statuses": ["open", "reviewing", "dispatched", "in_progress", "awaiting_verification", "verified_fixed", "resolved"],
        "verification_required_buses": settings.verification_required_buses,
        "verification_radius_meters": settings.verification_radius_meters,
        "severities": ["critical", "moderate", "clear"],
        "auth_roles": ["engineer", "worker"],
        "simulator_enabled": settings.simulator_enabled,
        "demo_data_enabled": settings.demo_data_enabled,
    }
