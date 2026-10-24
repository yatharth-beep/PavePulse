# PavePulse final prototype: novice release checklist

This guide explains how to update the public demo from the project ZIP. You do not need to understand the source code to follow the main steps.

## What changed

- The login screen now has a visible **Open reviewer guide (PDF)** link. The PDF lives at `frontend/public/reviewer-guide.pdf`, so it is deployed with the website; no Google Drive sharing configuration is required.
- The login screen displays Engineer and Worker demo credentials and lets a reviewer fill the chosen account with one click.
- The Audit page, public audit log APIs, and new log writes are removed. The server still calculates incident-integrity hashes used by duplicate/repair verification. Previously stored database log rows are not automatically deleted.
- The old Live Buses interface remains absent. The independent **Awaiting verification** queue is retained because it is the road-repair confirmation workflow, not the old Audit log screen.
- A one-time password utility updates the two existing Supabase Auth users to the requested demo passwords.

## Before you start

1. Download/extract the final ZIP and open the top-level `PavePulse` folder.
2. Make sure the GitHub repository connected to Vercel/Render is the correct repository and branch.
3. Do not copy any `.env` files containing secrets to GitHub. The password utility needs a Supabase service-role key, but only in your local terminal.

## Step 1 - set the demo passwords in Supabase Auth

The login page can display a password, but Supabase will only accept it once the password on that Auth user is actually changed. Run the supplied one-time script from the project root, on your own computer.

Find these values in Supabase Dashboard -> Project Settings -> API (use the secret/service-role key; do not use the anon/publishable key):

- Project URL: `https://YOUR-PROJECT-REF.supabase.co`
- Service-role key: secret administrative key for this project

### Windows PowerShell

Open PowerShell in the project root, then paste and run each line. The password/key prompt does not echo the secret as you type.

```powershell
$env:SUPABASE_URL = Read-Host "Supabase project URL"
$secureKey = Read-Host "Paste service_role key" -AsSecureString
$env:SUPABASE_SERVICE_ROLE_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
python scripts/set_demo_passwords.py
Remove-Item Env:SUPABASE_SERVICE_ROLE_KEY
Remove-Item Env:SUPABASE_URL
```

### macOS / Linux terminal

```bash
read -r -p "Supabase project URL: " SUPABASE_URL
export SUPABASE_URL
read -r -s -p "Paste service_role key: " SUPABASE_SERVICE_ROLE_KEY; echo
export SUPABASE_SERVICE_ROLE_KEY
python scripts/set_demo_passwords.py
unset SUPABASE_SERVICE_ROLE_KEY SUPABASE_URL
```

The script updates the existing users by email:

| Role | Username | Email | New demo password |
|---|---|---|---|
| Engineer | `engineer` | `engineer@pavepulse.local` | `engineer123` |
| Worker | `worker` | `worker@pavepulse.local` | `worker123` |

If it reports that an account is missing, open Supabase -> Authentication -> Users and verify that exact email exists. Never share the service-role key or commit it. These are weak public-demo credentials only; do not store real or sensitive data in this prototype.

## Step 2 - update GitHub

1. Open the current PavePulse repository in GitHub.
2. Upload/replace files using the contents of the extracted `PavePulse` folder, not the ZIP itself. Keep the repository's expected folder structure.
3. Confirm `frontend/public/reviewer-guide.pdf` and `scripts/set_demo_passwords.py` are present in the repository.
4. Commit the changes to the branch currently deployed by Vercel and Render (often `main`).

## Step 3 - check Vercel

1. Open Vercel -> `pave-pulse` -> Deployments. Wait for the new deployment to report **Ready**.
2. Keep the existing frontend environment variables, especially `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_API_BASE`. Do not put the service-role key in Vercel.
3. Open `https://pave-pulse.vercel.app/reviewer-guide.pdf`. It should render/download the five-page quick-start PDF. If it is a 404, check that the PDF was uploaded to `frontend/public/reviewer-guide.pdf` and that Vercel's Root Directory is `frontend`.
4. Open `https://pave-pulse.vercel.app/` in a private/incognito browser window and verify that the reviewer guide link and credentials appear on the login screen.

## Step 4 - check Render

1. Open Render -> `pavepulse-backend` -> Events/Logs and wait for the current deployment to be **Live**.
2. Keep `CORS_ORIGINS=https://pave-pulse.vercel.app`.
3. Open `https://pavepulse-backend.onrender.com/api/v1/health`; expect `status: ok` and `database: ok`.
4. If the backend is on Render's free plan and has been idle, its first request can take about one minute because the service sleeps after 15 minutes without inbound traffic. This is normal for the free tier. See https://render.com/docs/free.

## Step 5 - test as a reviewer

1. Sign in as Engineer using `engineer` / `engineer123`. Confirm the Pune map, Work Orders, Devices and Team access render. There should be no Audit tab.
2. Click a map marker, review the incident, then dispatch a work order.
3. Sign out and sign in as Worker using `worker` / `worker123`. Confirm only assigned Work Orders are available. Try starting a job, adding completion notes/evidence, and resolving it.
4. Sign back in as Engineer and confirm the completed repair appears in **Awaiting verification**.
5. Check the guide link in the login page and test it in another browser window.

## What free hosting means

Render confirms that a free web service spins down after 15 minutes without inbound HTTP traffic or WebSocket messages and needs about a minute to start on the next request. The Vercel frontend remains served, but API-backed actions may feel slow during the first request. The Supabase database is separate from Render's local filesystem; uploads stored only on a free Render filesystem can still be lost after a restart/redeploy. This is a public prototype setup, not a guaranteed 24/7 production service.

## Final limitations

- The credentials are shared and intentionally weak so reviewers can try the prototype. Do not expose sensitive personal data, production credentials, or real municipal repair records.
- The PDF screen drawings are illustrations of the navigation and workflow, not live screenshots from the deployed instance; data and counts can differ.
- The Audit view and audit-log read APIs are removed; previously stored database log rows are not automatically deleted. Incident integrity hashes remain internal.
- Run a frontend production build and visual browser test after dependency installation before calling this release production-ready.
