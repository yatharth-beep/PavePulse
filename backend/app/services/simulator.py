import asyncio
import random
import uuid
from datetime import timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.geo import ROUTES, interpolate_route
from app.models import Incident, IncidentVerification, TelemetryPing, Vehicle
from app.schemas import EdgeEventIn, SensorLog
from app.services.hub import hub
from app.services.incidents import ingest_event
from app.services.spatial import haversine_m, utcnow


class FleetSimulator:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._progress: dict[str, float] = {}
        self._tick_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        await asyncio.sleep(1.5)
        while True:
            db = SessionLocal()
            try:
                self.tick(db)
            except Exception:
                db.rollback()
            finally:
                db.close()
            await asyncio.sleep(1.15)

    def tick(self, db: Session) -> None:
        vehicles = db.query(Vehicle).all()
        if not vehicles:
            return
        now = utcnow()
        self._tick_count += 1
        persist_telemetry = self._tick_count % 10 == 0  # Sample history; publish live pings every tick.
        if self._tick_count % 300 == 0:
            db.execute(delete(TelemetryPing).where(TelemetryPing.observed_at < now - timedelta(hours=24)))
        for vehicle in vehicles:
            t = self._progress.get(vehicle.label, random.random())
            t = (t + random.uniform(0.004, 0.012)) % 1.0
            self._progress[vehicle.label] = t
            lon, lat = interpolate_route(vehicle.route_id, t)
            lon += random.uniform(-0.0004, 0.0004)
            lat += random.uniform(-0.0004, 0.0004)
            speed = max(0, random.gauss(28, 8))
            engine = random.choices(["ok", "derate", "idle"], weights=[86, 8, 6])[0]
            sensors = {
                "accel_z": round(random.uniform(-0.6, 0.8), 3),
                "rms_vibration": round(abs(random.gauss(0.7, 0.4)), 3),
                "cabin_temp_c": round(random.uniform(24, 34), 1),
                "fuel_pct": round(random.uniform(28, 96), 1),
            }
            vehicle.last_seen_at = now
            vehicle.power_status = "on"
            vehicle.connectivity_status = "connected"
            vehicle.software_version = "edge-0.1.0"
            vehicle.last_error = None
            db.add(vehicle)
            if persist_telemetry:
                ping = TelemetryPing(
                    vehicle_id=vehicle.id,
                    lon=lon,
                    lat=lat,
                    speed_kmh=round(speed, 1),
                    engine_status=engine,
                    sensor_log=sensors,
                    observed_at=now,
                )
                db.add(ping)
            payload = {
                "vehicle_label": vehicle.label,
                "route_id": vehicle.route_id,
                "lon": lon,
                "lat": lat,
                "speed_kmh": round(speed, 1),
                "engine_status": engine,
                "sensor_log": sensors,
                "observed_at": now.astimezone(timezone.utc).isoformat(),
            }
            hub.publish(payload)

            # In development only, simulate a clean visual pass when a different bus actually
            # traverses a repaired location. Raw GPS proximity alone never counts as a verification;
            # this simulator emits an explicit edge classification, matching the production contract.
            if settings.simulator_enabled and vehicle.id:
                pending = db.execute(
                    select(Incident).where(Incident.status == "awaiting_verification", Incident.merged_into_id.is_(None))
                ).scalars().all()
                for repaired in pending:
                    if repaired.vehicle_id == vehicle.id:
                        continue
                    if haversine_m(lon, lat, repaired.lon, repaired.lat) > settings.verification_radius_meters:
                        continue
                    prior_check = db.execute(
                        select(IncidentVerification.id).where(
                            IncidentVerification.incident_id == repaired.id,
                            IncidentVerification.cycle == repaired.verification_cycle,
                            IncidentVerification.vehicle_id == vehicle.id,
                            IncidentVerification.result == "clear",
                        ).limit(1)
                    ).first()
                    if prior_check:
                        continue
                    clear_pass = EdgeEventIn(
                        event_id=f"sim-verify-{uuid.uuid4().hex[:16]}",
                        vehicle_label=vehicle.label,
                        route_id=vehicle.route_id,
                        timestamp=now,
                        lon=lon,
                        lat=lat,
                        speed_kmh=round(speed, 1),
                        engine_status=engine,
                        sensors=SensorLog(
                            accel_z=sensors["accel_z"],
                            rms_vibration=sensors["rms_vibration"],
                            ir_reflectance=0.62,
                            depth_mm=round(random.uniform(1, 5), 2),
                            surface_class="clear",
                        ),
                        severity="clear",
                    )
                    checked, _ = ingest_event(db, clear_pass, actor_label=f"simulator:{vehicle.label}")
                    hub.publish({**payload, "incident": True, "verification": True, "verification_incident_id": str(checked.id), "result": "clear"})
                    break

            if random.random() < 0.035:
                depth = random.choice([random.uniform(8, 16), random.uniform(20, 38), random.uniform(45, 80)])
                surface = "critical" if depth >= 40 else "moderate" if depth >= 18 else "clear"
                event = EdgeEventIn(
                    event_id=f"sim-{uuid.uuid4().hex[:10]}",
                    vehicle_label=vehicle.label,
                    route_id=vehicle.route_id,
                    timestamp=now,
                    lon=lon,
                    lat=lat,
                    speed_kmh=round(speed, 1),
                    engine_status=engine,
                    sensors=SensorLog(
                        accel_z=sensors["accel_z"],
                        rms_vibration=sensors["rms_vibration"],
                        ir_reflectance=round(random.uniform(0.15, 0.85), 3),
                        depth_mm=round(depth, 2),
                        surface_class=surface,
                    ),
                    severity=surface,
                )
                ingest_event(db, event)
                hub.publish({**payload, "incident": True, "severity": surface, "depth_mm": round(depth, 2)})

        db.commit()


simulator = FleetSimulator()
