# PavePulse Pune demo release

## What changed

- Changed the MapLibre start position to Pune, Maharashtra (`73.8567, 18.5204`) and changed the map label accordingly.
- Replaced the old Bengaluru demo grid with eight illustrative Pune demo zones and four synthetic routes through areas such as Baner, Aundh, Shivajinagar, Deccan, Kothrud, Koregaon Park, Viman Nagar, Kharadi and Hadapsar.
- Updated the API `/api/v1/meta` response with `city: "Pune, Maharashtra, India"` and a clearly labelled dataset description when demo mode is enabled.
- Changed generated sample event IDs to the `demo-pune-edge-` prefix.
- Updated/upserted the existing W01-W08 zones on startup so an existing database does not keep the Bengaluru names/geometries.
- When demo mode is explicitly enabled, removed legacy synthetic incidents identified by `demo-edge-` together with their linked sample work orders/evidence, while retaining ordinary event records with non-demo IDs and preserving the audit log.
- Seeded a sample workflow: one incident in review, a dispatched work order, an in-progress work order, and a completed work order waiting for independent verification. These sample work orders are assigned to the Worker account when it exists.
- Added a conspicuous Pune demo disclaimer to secondary pages and changed visible ward labels to “Pune demo zone” to avoid representing the illustrative rectangles as official PMC boundaries.
- Confirmed that the frontend contains no Live Buses page or moving-bus map layer. The Engineer-only Devices screen remains for registration and device-health diagnostics.

## Deploy steps

1. Commit/push the extracted project contents to the GitHub repository connected to both Vercel and Render. Do not commit real `.env` files or credentials.
2. In Render → the `pavepulse-backend` service → Environment, set `DEMO_DATA_ENABLED=true`.
3. Keep `SIMULATOR_ENABLED=false` and `SEED_ON_STARTUP=false`. The demo seeding is a separate explicit option and does not require fake moving-bus telemetry.
4. Save/redeploy the Render service. Startup should upsert Pune zones, create labelled Pune incidents if the Pune sample set does not exist, and add the sample work-order lifecycle if none exists for the sample incidents.
5. Wait for deployment to become Live, then check `/api/v1/health` and `/api/v1/meta`. Meta should include `city: "Pune, Maharashtra, India"` and `demo_data_enabled: true`.
6. Redeploy the Vercel frontend (automatic on push if Git integration is enabled), then hard-refresh `https://pave-pulse.vercel.app/`.

## Important demo-data behaviour

- The generated locations are illustrative examples near Pune localities; they are not real pothole reports, surveyed defects, or official PMC ward boundaries.
- Setting `DEMO_DATA_ENABLED=false` stops further demo seeding, but does not automatically delete already-seeded Pune sample data.
- The next startup with demo mode enabled removes only legacy synthetic rows whose source event IDs use the old `demo-edge-` prefix and related work orders/evidence. It preserves incident rows with non-demo event IDs.
- Before enabling demo mode against a database that contains valuable real operational history, take a backup. Do not enable the demo option on a real municipal production database.

## Verification

- Backend test suite: **18 passed**.
- Python compilation: passed.
- `node --check` for the updated MapLibre engine: passed.
- Frontend Vite production build: **not verified**. The environment had no `node_modules`; `npm ci` timed out, so the browser bundle could not be built here. Run `npm ci && npm run build` in an environment with npm registry access.
