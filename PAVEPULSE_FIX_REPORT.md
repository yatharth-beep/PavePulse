# PavePulse Vercel + Supabase Repair Report

## Findings from the uploaded archive and screenshot

The browser console showed `TypeError: De.forEach is not a function`. This was a consequence of the deployed frontend failing to get API JSON, not a Supabase Table Editor rendering problem.

1. `frontend/src/api.js` had stubbed dashboard calls: `summary()` returned zero values and `wards()` / `incidents()` returned empty arrays. This guarantees no incident markers from the dashboard API.
2. Other pages called `/api/v1/...`, but the frontend did not have a configured API base URL by default. On Vercel, the catch-all SPA rewrite can return `index.html` for those paths with HTTP 200. A list component then receives a string instead of a list and calls `.forEach()`, matching the screenshot.
3. In this architecture, Supabase is the identity provider; operational incidents, work orders, device health, audit records and user shadows are managed by the FastAPI backend using SQLAlchemy/PostgreSQL. The uploaded source did not have browser-side Supabase queries or migration SQL for those operational records. An empty Supabase Table Editor is expected until the FastAPI backend starts with `DATABASE_URL` pointing to that same Supabase project's PostgreSQL database.

## Code changes

- Replaced the hard-coded dashboard summary/ward/incident stubs with FastAPI API calls.
- Added strict JSON and array validation. HTML returned by Vercel rewrites or an incorrect backend URL now produces an actionable error instead of reaching a component's `.forEach()`.
- Made API configuration fail clearly when a production Vercel build lacks `VITE_API_BASE`.
- Kept Supabase sign-in but made the FastAPI server validate Supabase access tokens and apply server-side Engineer/Worker authorization. Server-configured role mappings are the authority; untrusted user-editable role metadata is ignored.
- Kept incident/map rendering connected to the real incident endpoint and added clear map-empty/error states.
- Removed the Live Buses panel, hook, and map bus layer from the frontend; the Devices page remains for device health/registration.
- Added a React error boundary so a remaining unexpected render exception shows a visible recovery screen instead of a blank application.
- Added `docs/VERCEL_SUPABASE_DEPLOYMENT.md` with deployment settings, missing-table troubleshooting, data/demo guidance, and validation steps.

## Validation performed

- Backend Python compilation: passed.
- Backend automated tests: **18 passed**.
- Static JSX/JavaScript syntax parsing: **17 source files passed**.
- Relative frontend import check: no missing relative imports.
- A Vite production build was **not verified**. `npm ci` did not complete in this execution environment, and `vite` was unavailable afterward. The live Vercel/Supabase project was not modified directly because deployment credentials and repository access were not provided.

## Required deployment configuration

### Backend service (e.g. Render)

- Root directory: `backend`
- Build command: `pip install -r requirements.txt -r requirements-postgres.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `APP_ENV=production`
- `DATABASE_URL`: PostgreSQL connection URL from the same Supabase project (not an API key); use TLS and URL-encode reserved password characters.
- `SUPABASE_URL`: same Supabase project URL.
- `SUPABASE_ENGINEER_EMAILS=engineer@pavepulse.local`
- `SUPABASE_WORKER_EMAILS=worker@pavepulse.local`
- `SUPABASE_JWT_SECRET`: blank for asymmetric Supabase JWT signing (JWKS verification); set the Supabase JWT signing secret only if the project uses legacy HS256 signing.
- `CORS_ORIGINS=https://pave-pulse.vercel.app`
- `JWT_SECRET`: unique random value, at least 32 characters.
- `SIMULATOR_ENABLED=false`
- `SEED_ON_STARTUP=false`
- `DEMO_DATA_ENABLED=true` only for an isolated demo database when sample markers are wanted; set false for actual operations.
- `DEVICE_API_KEY`: unique random secret.
- `VERIFICATION_REQUIRED_BUSES=2`
- `VERIFICATION_RADIUS_METERS=35`

At API startup, `init_db()` creates operational tables from `backend/app/models.py` and applies additive schema migrations. If tables do not appear after a successful deployment, inspect backend startup logs and make sure `DATABASE_URL` points to the same Supabase project. The backend also enables PostgreSQL RLS on operational tables without browser-facing policies; normal app access goes through FastAPI.

### Vercel frontend

Set these Production environment variables (and Preview too, if needed):

- `VITE_SUPABASE_URL`: the same Supabase project URL.
- `VITE_SUPABASE_ANON_KEY`: the public anon/publishable key; never use the service-role key here.
- `VITE_API_BASE`: the deployed FastAPI service root, for example `https://pavepulse-api.onrender.com`, without a trailing slash.

Redeploy the frontend after changing Vite environment variables; they are embedded at build time.

## Post-deployment verification

1. `https://<api-host>/api/v1/health` returns JSON with `status: ok` and `database: ok`.
2. `https://<api-host>/api/v1/meta` returns JSON, not the frontend HTML.
3. Sign in on `https://pave-pulse.vercel.app/`; the Engineer dashboard reports that it is connected.
4. If a new database is empty and this is a demo, enable `DEMO_DATA_ENABLED=true` on the API. The application creates illustrative incidents only if the incidents table is empty and labels them as demo. With demo mode off and no ingested events, no incident markers is the correct result.
5. Work Orders, Audit, Devices, and Team Access show data, empty states, or an explicit API error rather than blanking.
6. Verify the Worker can only view assigned orders and cannot call Engineer-only endpoints.

## Limits

This source patch cannot change the currently deployed Vercel project without access to its Git repository/deployment settings. The updated source must be committed/uploaded and redeployed, and the backend must be deployed/configured as above. Real road markers require real ingested detections; demo markers are illustrative, not real road-condition claims. Evidence files on an ephemeral API host need durable storage before relying on them for actual municipal records.


## Follow-up: Pune demo dataset

The city viewport, ward-zone rectangles, and illustrative routes now centre on Pune, Maharashtra. Production demo seeding is activated explicitly with `DEMO_DATA_ENABLED=true`; it seeds `demo-pune-edge-` sample records and refreshes legacy synthetic Bengaluru rows only. The old Live Buses page/layer is not present; Engineer-only device health remains. These sample locations are for demonstration only, not official PMC boundaries or confirmed potholes.
