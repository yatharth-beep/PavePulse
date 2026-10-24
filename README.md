# PavePulse — Road Defect Detection & Maintenance Platform

PavePulse is a municipal road-condition monitoring MVP. It accepts compact edge-detection events, clusters repeat sightings by location and time, gives municipal staff a review-before-dispatch workflow, and tracks repair work orders with user/device authentication and incident status and repair-verification history.

**Current deployment scope:** a functional web/API pilot platform. The bundled seed geography/routes and optional development simulator are for an illustrative Pune demo. The repository does not contain a trained YOLO model, vehicle firmware, actual accelerometer/camera integration, or a municipal procurement/approval-system connector; edge devices must send already-classified event records to the ingestion API.

## Features

- **GIS dashboard:** interactive Pune road-defect heatmap, individual incident markers, demo-zone summaries, severity/status/route/date filters. No live bus-location layer is included.
- **Incident review:** location, timestamp, severity, sensor record, depth estimate, cluster hit count and integrity status; duplicate candidates can be merged when location and severity constraints are satisfied.
- **Review-before-dispatch:** only a reviewed defect can create a work order. Dispatch generates a unique ticket, timestamps it, and automatically moves the parent incident from `reviewing` to `dispatched`.
- **Quick status actions:** Engineers can start or resolve repairs directly from the incident drawer or work-order card; status changes keep the parent incident and work order synchronized.
- **Work orders:** assign active Worker accounts, assign a crew, record progress, completion notes, and an evidence URL or private file upload, and track dispatch/update/completion times. Worker close-out requires completion notes or evidence.
- **Fleet device health:** power/connectivity, last message, software version and reported error; engineers can register vehicles and issue or rotate per-device credentials. Raw device secrets are shown once and only their hashes are stored.
- **Role-based access:** `engineer` and `worker`, with API-enforced permissions and assigned-order isolation for workers.
- **Security and integrity:** expiring signed bearer tokens, salted PBKDF2 password hashes, login throttling, per-device event keys, request/schema validation, security response headers, password-change session invalidation, and internal incident-integrity hashes. The Audit screen, both audit-log API surfaces, and new audit-log writes have been removed from this prototype.
- **Spatial deduplication:** same-severity reports within 30 metres and 24 hours are clustered. Manual merge is restricted to eligible, same-severity reports within 100 metres and with no work orders.
- **Reliable ingestion:** unique event IDs make retries idempotent. Device route assignment and timestamps are validated; no raw video upload field is accepted. PostgreSQL/PostGIS uses a functional GiST location index; SQLite provides a local fallback.
- **Developer simulator:** local development can generate example road events and device telemetry. Production deployments must keep `SIMULATOR_ENABLED=false`; the frontend intentionally has no Live Buses page or moving-bus map layer.

## Run with Docker Compose

Requirements: Docker Engine and the Docker Compose plugin. From the project root:

```bash
docker compose up --build
```

Open the dashboard at **http://localhost:5173**. The API health check is available at **http://localhost:5173/api/v1/health**. In the default development configuration, the API seeds demo incidents and starts the simulator.

### Development demo accounts

| Role | Username | Password |
|---|---|---|
| Engineer | `engineer` | `engineer123` |
| Worker | `worker` | `worker123` |

These credentials are intentionally shared for the public prototype reviewer experience only. They are weak by design and must not protect real data or be reused elsewhere. Run `python scripts/set_demo_passwords.py` once with a temporary Supabase service-role key in your local shell before sharing the deployed reviewer build. Never commit a service-role key or any other secret.

A reviewer quick-start guide with illustrated interface screenshots is published at `/reviewer-guide.pdf` and linked from the login page. The Audit screen, public audit-log APIs, and new audit-log writes are removed. Internal incident-integrity hashes remain to protect duplicate and repair-verification consistency. Previously stored log rows are not automatically deleted.

The PDF guide is served by Vercel from `frontend/public/reviewer-guide.pdf`, so the login link works without a separate Drive account. If you replace the PDF, keep the same filename or update both login links.

The dashboard uses MapLibre GL JS with keyless OpenStreetMap standard raster tiles, a separate OSM-derived fallback, and an offline canvas fallback. No Mapbox or CARTO API key is required. The basemap preserves visible OpenStreetMap attribution. Public community tile servers are best-effort and not an SLA-backed production basemap; for high-volume or commercial municipal deployments, use a hosted/self-managed OSM-derived tile provider that matches your traffic and service requirements. See https://operations.osmfoundation.org/policies/tiles/ for the standard OSM tile policy.

To stop the services:

```bash
docker compose down
```

To also delete the local PostGIS volume and its data (destructive):

```bash
docker compose down -v
```

## Production configuration

Do not run the development defaults on a public network. Start from `.env.production.example`, save it as `.env`, replace every placeholder and set the actual public frontend origin. Use URL-safe characters in `POSTGRES_PASSWORD` because Compose embeds it in the database connection URL.

Production must have all of the following:

```dotenv
APP_ENV=production
POSTGRES_PASSWORD=<strong-url-safe-secret>
JWT_SECRET=<unique-random-secret-at-least-32-characters>
BOOTSTRAP_ENGINEER_PASSWORD=<unique-password-at-least-14-characters>
CORS_ORIGINS=https://your-real-dashboard-domain.example
SIMULATOR_ENABLED=false
SEED_ON_STARTUP=false
```

Also replace the example ward bounds/routes in `backend/app/geo.py` for the target municipality before deployment. Production startup seeds only configured ward reference records and the configured Engineer/Worker operational profiles—not synthetic incidents, unless `DEMO_DATA_ENABLED=true` is explicitly enabled for an isolated demonstration database. Supabase Auth accounts must first exist in Supabase Authentication and be authorized by `SUPABASE_ENGINEER_EMAILS` / `SUPABASE_WORKER_EMAILS`, or by server-managed `app_metadata.role`; a row in the local operational `users` table is not by itself a Supabase login. Use **Devices → Register edge device**, then issue its per-device key and provision it securely to the vehicle. Do not enable the shared development key in production. Terminate HTTPS at a trusted reverse proxy/load balancer; the application does not provision TLS certificates. Restrict DB network access, rotate database/JWT/device secrets, and back up PostgreSQL.

`docker-compose.yml` is a convenient single-host deployment starting point, not a substitute for an operational production environment. It includes a development default profile and a PostGIS database; replace all development secrets, run with the production values above, and use managed database backups, TLS, secret management, monitoring, and a deployment-specific scaling plan for real traffic.

## Run locally without Docker

### Backend (Python 3.11+)

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux instead: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # Windows: copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

Local API docs are at **http://localhost:8000/docs**. The local `.env.example` uses SQLite and enables demo seeding/simulation.

### Frontend (Node.js 20+)

In a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. The Vite development server proxies `/api` to `http://localhost:8000`. For a production frontend bundle, run `npm run build`; use `npm run preview` to inspect the generated bundle locally. For the Vercel + Supabase Auth + Supabase PostgreSQL deployment, follow [`docs/VERCEL_SUPABASE_DEPLOYMENT.md`](docs/VERCEL_SUPABASE_DEPLOYMENT.md). The FastAPI backend must be deployed separately from the Vercel static frontend, and Vercel must have `VITE_API_BASE` set to that API URL.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

The API regression suite uses a separate temporary SQLite database and does not depend on a running PostGIS instance. It covers auth/RBAC and rejection of legacy roles, event validation and retry idempotency, spatial clustering, review-before-dispatch and synchronized statuses, worker isolation and work-order lifecycle, private evidence uploads, device registration/key scoping, duplicate merge integrity, password session invalidation, and the absence of the retired Audit UI/API.

## API overview

All paths below are under `/api/v1`.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/health` | Public | Database health check |
| `GET` | `/meta` | Public | Ward/route/status metadata |
| `POST` | `/auth/login` | Public | Sign in and issue bearer token |
| `GET` | `/auth/me` | Signed in | Current account/role |
| `POST` | `/auth/change-password` | Signed in | Change password and rotate session token |
| `POST` | `/events` | Device key | Ingest compact edge event |
| `GET` | `/incidents` | Engineer | Filter incidents |
| `POST` | `/incidents/{id}/review` | Engineer | Review and record reviewer/time |
| `POST` | `/incidents/{id}/merge` | Engineer | Merge an eligible duplicate |
| `POST` | `/incidents/{id}/dispatch` | Engineer | Create repair work order after review and mark incident dispatched |
| `PATCH` | `/incidents/{id}/status` | Engineer | Quick `in_progress`/`resolved` action synchronizing the parent incident and work order |
| `GET/PATCH` | `/work-orders` | Engineer / assigned Worker | List and update repairs |
| `POST/GET` | `/work-orders/{id}/evidence` | Engineer / assigned Worker | Upload or download private PNG/JPEG/PDF evidence (5 MB limit) |
| `GET/POST` | `/telemetry/devices` | Engineer only | Device health and enrollment |
| `POST` | `/telemetry/devices/{label}/credentials` | Engineer | Issue/rotate a one-time device secret |
| `GET` | `/telemetry/latest`, `/telemetry/stream` | Engineer | Latest telemetry and SSE stream |
| `GET` | `/analytics/summary`, `/analytics/wards`, `/analytics/heatmap` | Engineer | KPIs, ward roll-up, GeoJSON heatmap |

### Edge event example

Device requests must use `X-Device-Key`. In development only, the shared key in `.env` is accepted; production requires a rotated per-device credential.

```http
POST /api/v1/events
Content-Type: application/json
X-Device-Key: <per-device-secret>
```

```json
{
  "event_id": "edge-vehicle701-000042",
  "vehicle_label": "BUS-701",
  "route_id": "R12",
  "timestamp": "2026-10-21T10:32:00Z",
  "lon": 73.8567,
  "lat": 18.5204,
  "speed_kmh": 26.4,
  "engine_status": "ok",
  "severity": "critical",
  "sensors": {
    "accel_z": 1.2,
    "rms_vibration": 2.4,
    "ir_reflectance": 0.42,
    "depth_mm": 58,
    "surface_class": "critical"
  }
}
```

`vehicle_label` must be registered and must match the assigned `route_id`; `timestamp` must include a timezone. A device should upload compact detections, not continuous raw video. `depth_mm` is an estimate provided by the edge pipeline, **not** a calibrated physical measurement until validated against manually measured defects.

## Operational limits / next work

- The dashboard consumes already-classified events; model training/inference, camera capture, accelerometer drivers, GPS buffering/retry firmware, and sensor-fusion calibration have to be implemented and validated on actual edge hardware.
- The bundled city, route and ward geometries are illustrative Pune demo data centred around Baner, Aundh, Shivajinagar, Deccan, Kothrud, Koregaon Park, Viman Nagar, Kharadi and Hadapsar. They are not official PMC ward boundaries or actual defect detections. Replace them with authoritative municipal GIS records before operational use.
- Evidence may be referenced by a validated HTTP(S) URL or uploaded as a PNG/JPEG/PDF file up to 5 MB. Uploaded evidence is private and served only through authenticated, assignment-scoped endpoints. Docker Compose persists files in a dedicated volume; a production rollout should migrate this storage to managed object storage, define retention/deletion rules, and test backup/restore procedures.
- KPI values such as detection precision/recall, false-positive rate, depth-estimation error, kilometres mapped, cost per kilometre, and repair-lifecycle savings are not fabricated by the app. Add a ground-truth evaluation dataset and collect field measurements before publishing those results or claiming cost savings.
- Schema changes currently use additive startup migration logic; larger deployments should adopt a versioned migration tool and a tested backup/restore procedure.
- This sandbox validation passed backend compilation/API tests, but frontend dependency installation and `vite build` could not be verified here because npm registry DNS resolution failed. Run `npm ci && npm run build` in an environment that can reach the npm registry before public release.


## Show illustrative Pune demo data on Render

For a public showcase only, open Render → the `pavepulse-backend` service → Environment and set `DEMO_DATA_ENABLED=true`. Keep `SIMULATOR_ENABLED=false` and `SEED_ON_STARTUP=false` in production, then save/redeploy the service. At startup, the backend updates the eight illustrative Pune demo zones, replaces any legacy rows whose source event IDs use the old `demo-edge-` seed prefix, and creates Pune samples with IDs prefixed `demo-pune-edge-` if no Pune sample set exists. It also seeds a small reviewed/dispatched/in-progress/completed work-order flow and sample work-order status states so the main screens are demonstrable. Genuine events with other source IDs are retained. The dashboard displays **PUNE DEMO · ILLUSTRATIVE ONLY**. Set the flag to `false` for a real municipal deployment; turning it off stops future seeding but does not automatically remove already-seeded sample rows.

The sample locations are illustrative map pins near Pune-area localities, not evidence that a pothole exists at a real address. The former Live Buses map/page is not included; the Devices page is retained for device health and registration.


## Post-repair verification (Awaiting verification)

When a Worker or Engineer closes a work order, the work order becomes resolved but its parent road incident moves to `awaiting_verification`. The dashboard shows it in the **Awaiting verification** queue. By default, two distinct buses other than the original reporting bus must send an explicit clear classification within `VERIFICATION_RADIUS_METERS` of the repaired point. Repeat detections from the same bus are recorded but do not increase the independent-bus count. After the threshold is reached, the incident becomes `verified_fixed`. If another event detects a moderate/critical defect (or a depth of at least 18 mm) at the location, the incident reopens to `open` and the incident returns to `open`. Each inspection is stored in `incident_verifications`.

Tune the independent vehicle threshold with `VERIFICATION_REQUIRED_BUSES` (default `2`) and the inspection matching radius with `VERIFICATION_RADIUS_METERS` (default `35`). Edge devices must report a positive clear classification (`severity: "clear"` or `sensors.surface_class: "clear"`) to count a clean pass; silence or an unclassified event does not prove that a repair is fixed.

## Map tile troubleshooting

The application uses keyless OpenStreetMap raster tiles and a fallback source. To ensure the changed frontend is deployed, rebuild the web image instead of reusing an old cached container: `docker compose build --no-cache web && docker compose up -d --force-recreate web`. Then hard-refresh the browser. OpenStreetMap tiles need browser network access. When both public tile sources are unavailable, incident overlays remain on an offline canvas but no street labels appear. The Live Buses page/map layer is intentionally not part of the frontend. The Engineer-only Devices page remains for device registration and health diagnostics.


## Current Vercel/Supabase setup

The latest frontend/API integration fixes and host configuration are documented in [`docs/VERCEL_SUPABASE_DEPLOYMENT.md`](docs/VERCEL_SUPABASE_DEPLOYMENT.md). The app previously had empty dashboard data stubs and was missing a configured API base URL, which caused static Vercel rewrites to return HTML to API requests.
