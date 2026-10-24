"""Set the shared PavePulse prototype passwords in Supabase Auth.

Run this one time from your local computer. Never commit the service-role key.
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the local shell environment.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ACCOUNTS = {
    "engineer@pavepulse.local": "engineer123",
    "worker@pavepulse.local": "worker123",
}


def api_request(url: str, service_key: str, method: str = "GET", body: dict | None = None) -> dict:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Supabase returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Supabase: {exc.reason}") from exc


def main() -> int:
    project_url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not project_url or not service_key:
        print("Missing environment variables. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in your local terminal first.", file=sys.stderr)
        return 2
    if not project_url.startswith("https://"):
        print("SUPABASE_URL must be your https://<project-ref>.supabase.co project URL.", file=sys.stderr)
        return 2

    users_by_email: dict[str, dict] = {}
    for page in range(1, 11):
        query = urlencode({"page": page, "per_page": 100})
        response = api_request(f"{project_url}/auth/v1/admin/users?{query}", service_key)
        users = response.get("users", []) if isinstance(response, dict) else response
        if not isinstance(users, list):
            raise RuntimeError("Unexpected response from Supabase Admin API while listing users.")
        for user in users:
            email = str(user.get("email", "")).strip().lower()
            if email in ACCOUNTS:
                users_by_email[email] = user
        if len(users) < 100:
            break

    missing = sorted(set(ACCOUNTS) - set(users_by_email))
    if missing:
        print("These Supabase Auth users were not found: " + ", ".join(missing), file=sys.stderr)
        print("Create/confirm both accounts in Supabase Authentication > Users, then run this script again.", file=sys.stderr)
        return 1

    print("Setting shared prototype passwords. These are weak demo-only passwords.")
    for email, password in ACCOUNTS.items():
        user_id = users_by_email[email].get("id")
        if not user_id:
            raise RuntimeError(f"Supabase did not return a user ID for {email}.")
        api_request(f"{project_url}/auth/v1/admin/users/{user_id}", service_key, method="PUT", body={"password": password})
        print(f"Updated password for {email}")
    print("Done. Remove SUPABASE_SERVICE_ROLE_KEY from your terminal environment when finished; never commit or expose it.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
