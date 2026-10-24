# PavePulse on Vercel + Supabase: fix the current deployment

This repository is a React/Vite frontend plus a FastAPI API. Supabase currently supplies **Auth** and PostgreSQL; it is not a frontend-only Supabase application. A Vercel static deployment cannot execute `backend/app/main.py` by itself.

## Why the current version goes blank

- `frontend/src/api.js` had `summary()`, `wards()` and `incidents()` returning hard-coded empty data, so the dashboard map had no markers.
- Work Orders, Devices and Team Access call `/api/v1/...`. On Vercel those paths were rewritten to `index.html` if the API URL was not configured. The request returned HTML with HTTP 200 and a component later called `.forEach()` on that string.
- `supabase-js` was only used for login. This source did not contain Supabase migrations or direct Supabase queries for incident/work-order tables, so an empty Supabase Table Editor was consistent with the architecture.

The frontend shows Pune-centred incident overlays and rejects non-JSON API responses with an actionable message, data methods point at the real FastAPI routes, and the backend verifies Supabase access tokens before applying Engineer/Worker authorization.

## Deploy the API (one time)

Use a Python host such as Render. Connect this GitHub repository and create a Web Service:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt -r requirements-postgres.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/v1/health`

Create the database connection string in Supabase Dashboard → Connect → choose a PostgreSQL connection method appropriate for the host. Use the **PostgreSQL database URL**, not the anon/publishable key or service-role API key. URL-encode special characters in the password if necessary, and require TLS (`sslmode=require`).

Set these environment variables on the API host:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Supabase PostgreSQL connection URL |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ENGINEER_EMAILS` | `engineer@pavepulse.local` |
| `SUPABASE_WORKER_EMAILS` | `worker@pavepulse.local` |
| `SUPABASE_JWT_SECRET` | Leave blank for asymmetric/JWKS signing. For legacy HS256 projects, use the JWT signing secret from Supabase Auth settings (never the anon key). |
| `CORS_ORIGINS` | `https://pave-pulse.vercel.app` |
| `JWT_SECRET` | New random secret, 32+ characters; not the Supabase key |
| `SIMULATOR_ENABLED` | `false` |
| `SEED_ON_STARTUP` | `false` |
| `DEMO_DATA_ENABLED` | `true` only if this is an isolated demo project and synthetic example incidents are wanted; otherwise `false` |
| `DEVICE_API_KEY` | A separate new random device-ingestion secret |
| `VERIFICATION_REQUIRED_BUSES` | `2` |
| `VERIFICATION_RADIUS_METERS` | `35` |

Do not copy values from this table into source code. Enter secrets only in the hosting provider's Environment settings.

### Database table creation

On API startup, SQLAlchemy creates the required `public` tables from `backend/app/models.py`, applies additive schema upgrades, and enables Row Level Security on those tables without adding browser-facing policies. The backend connects with its PostgreSQL database account and handles protected data through FastAPI. No service-role key is sent to the browser.

After the API successfully starts, open Supabase → Table Editor and refresh. Tables are only created if `DATABASE_URL` points to this same Supabase project and startup completes. If you do not see tables, inspect the API deployment logs and verify the database URL first.

### Demo markers vs real reports

For a public showcase, set `DEMO_DATA_ENABLED=true` on the Render API service, save, and redeploy. Startup upserts the illustrative Pune demo zones and seeds reports with event IDs prefixed `demo-pune-edge-` if no Pune demo set exists. It also creates a small sample workflow: one reviewed incident, a dispatched order, an in-progress order and a completed order waiting for independent verification, assigned to the Worker account when available. It also removes legacy synthetic Bengaluru incidents identified by the old `demo-edge-` prefix (and their sample work orders); ordinary incident rows with other source IDs are retained. The dashboard shows **PUNE DEMO · ILLUSTRATIVE ONLY**. The Devices screen lists enrolled demo devices for health diagnostics; there is no Live Buses page or moving-bus map layer. Sample coordinates are illustrative only and are not official PMC reports or confirmed pothole locations. Keep `SIMULATOR_ENABLED=false` and `SEED_ON_STARTUP=false` in production. Leave `DEMO_DATA_ENABLED=false` for real municipal operations; turning it off does not delete samples previously seeded.

## Configure Vercel frontend

In Vercel → project `pave-pulse` → Settings → Environment Variables, add for Production (and Preview too if you use previews):

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | The same Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase publishable/anon key (safe for browser use when policies are configured). Never use the service-role key. |
| `VITE_API_BASE` | The deployed API service root, e.g. `https://pavepulse-api.onrender.com` (no trailing slash) |

Save, then go to Deployments and redeploy the latest commit. Vite variables are embedded at build time; changing them without rebuilding does not update the site.

## Verify the deployment

1. Open `https://<api-host>/api/v1/health`; expect JSON with `status: ok` and `database: ok`.
2. Open `https://<api-host>/api/v1/meta`; expect JSON listing the known wards/routes and the verification settings.
3. Open `https://pave-pulse.vercel.app/`, sign in with the existing Supabase Engineer account, and confirm the dashboard reports `Dashboard connected` rather than a configuration error.
4. Confirm the map shows incident markers. On a fresh demo database with `DEMO_DATA_ENABLED=true`, markers should be synthetic and the demo badge must be visible. With demo data disabled, a blank incident map is expected until ingestion occurs.
5. Verify Work Orders, Devices and Team Access all show lists, clear empty states, or actionable API errors—not a blank page.
6. Sign in with the Worker account and verify it opens Work Orders and cannot access Engineer-only backend endpoints.

## Existing accounts and adding additional users

The existing `engineer@pavepulse.local` and `worker@pavepulse.local` identities are authorized by default. The email local-part (`engineer`, `worker`) becomes the operational username in the API database. New users must be created in Supabase Auth and authorized server-side either by adding their email to `SUPABASE_WORKER_EMAILS` / `SUPABASE_ENGINEER_EMAILS` and redeploying, or by assigning a **server-controlled** `app_metadata.role` through Supabase Admin tooling. Do not use editable `user_metadata.role` as an authorization source. The Team Access screen intentionally explains this instead of pretending that a SQL-only user record creates a Supabase login.

## Known deployment caveats

- Public tile servers are best-effort. This fixes the API data flow, not tile-server uptime.
- Work-order evidence files are written to the API filesystem by the current backend. A free ephemeral host can lose those uploads on redeploy/restart; persistent evidence needs a durable disk or a Supabase Storage integration before relying on it for real municipal records.
- `DEMO_DATA_ENABLED=true` is for a public demonstration only. Never mistake seeded sample incidents for actual road conditions.

## Troubleshooting the exact reported symptoms

### Dashboard shows no incident markers

1. Open the Render/FastAPI URL plus `/api/v1/health`. It must return JSON with `status: ok` and `database: ok`.
2. Open the same API URL plus `/api/v1/meta`. It must return JSON (not the Vercel `index.html`).
3. In Vercel → Settings → Environment Variables, verify `VITE_API_BASE` is the FastAPI service root URL with no trailing slash. Redeploy after changing it; Vite embeds these variables during build.
4. If the API works but the map has zero markers, check whether the incidents table is empty. For an isolated demonstration, set `DEMO_DATA_ENABLED=true` on the API, restart/redeploy it, and confirm the **PUNE DEMO · ILLUSTRATIVE ONLY** badge appears. For real operations leave this false and ingest real detection events.

### Work Orders, Devices, or Team Access turns blank

The frontend now validates that list endpoints return JSON arrays before a screen iterates over the rows, and the app has a visible error boundary. If an error is displayed, check its message rather than repeatedly navigating. A response that contains HTML almost always means `VITE_API_BASE` is missing or points to the frontend instead of the FastAPI service. HTTP 401 means the API did not accept the Supabase access token; verify `SUPABASE_URL`, the token signing configuration, and the exact authorized role email. HTTP 403 means that the authenticated identity has no authorized Engineer/Worker role or the account is disabled.

### Supabase Table Editor is empty

The current architecture creates operational tables with SQLAlchemy when the **FastAPI backend starts**. Supabase Auth users do not automatically create application tables. Verify that the backend `DATABASE_URL` is the PostgreSQL connection string from the same Supabase project shown in the frontend's `VITE_SUPABASE_URL`; it must not be a Supabase anon/publishable/service-role API key. Then inspect the backend startup logs for migration, database authentication, or PostGIS extension errors. When startup finishes successfully, refresh Supabase → Table Editor.

Use the Supabase PostgreSQL connection details under **Connect**. Prefer a connection mode suitable for a long-running Python web service; use a session-pooler URI if the host cannot reach the direct database host. Keep the database password URL-encoded if it contains reserved URI characters and enable TLS (`sslmode=require`). Do not paste connection strings or signing secrets into GitHub, browser variables, screenshots, or chat.

### Account can sign in to Supabase but PavePulse says unauthorized

The browser authenticates with Supabase Auth, but the FastAPI backend separately verifies the JWT and maps the verified email to a role. Set `SUPABASE_URL` on the API. Ensure `SUPABASE_ENGINEER_EMAILS` includes `engineer@pavepulse.local` and `SUPABASE_WORKER_EMAILS` includes `worker@pavepulse.local`. For asymmetric Supabase signing, leave `SUPABASE_JWT_SECRET` blank so the API resolves the signing key via Supabase JWKS; for a legacy HS256 project, set the JWT signing secret from Supabase Auth settings. The secret is backend-only. Redeploy the API after configuration changes.


## Final reviewer prototype settings

The login page links directly to `/reviewer-guide.pdf`, which is served from `frontend/public/reviewer-guide.pdf`. This avoids needing a separate public Google Drive link. If you replace the guide, keep the same filename to preserve the login link.

The visible reviewer credentials are `engineer` / `engineer123` and `worker` / `worker123`. Before sharing a prototype deployment, update the two existing users in Supabase Auth by running `python scripts/set_demo_passwords.py` from the repository root with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` set in your local terminal. Never add the service-role key to repository files or Vercel variables. These are weak demo-only credentials and must not be used for real data.

The Audit navigation, Audit panel, public audit-log APIs, work-order log endpoint and new log writes are removed from this prototype. Internal incident-integrity hashing remains server-side because duplicate/repair-verification code depends on it; previously stored log rows are not automatically deleted.
