from datetime import datetime, timedelta, timezone
from uuid import uuid4


def event_payload(*, event_id=None, vehicle="BUS-101", route="R12", lon=73.94513, lat=18.60223, minute=0):
    return {
        "event_id": event_id or f"test-{uuid4().hex}",
        "vehicle_label": vehicle,
        "route_id": route,
        "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=minute)).isoformat(),
        "lon": lon,
        "lat": lat,
        "speed_kmh": 24,
        "engine_status": "ok",
        "sensors": {"accel_z": 1.2, "rms_vibration": 2.1, "depth_mm": 58.0, "surface_class": "critical"},
        "severity": "critical",
    }


def test_authentication_and_role_access(client, auth):
    assert client.get("/api/v1/incidents").status_code == 401
    assert client.get("/api/v1/auth/users", headers=auth["worker"]).status_code == 403
    assert client.get("/api/v1/telemetry/devices", headers=auth["worker"]).status_code == 403
    assert client.get("/api/v1/incidents", headers=auth["worker"]).status_code == 403
    assert client.get("/api/v1/analytics/summary", headers=auth["worker"]).status_code == 403
    assert client.get("/api/v1/audit/logs", headers=auth["worker"]).status_code == 404
    assert client.get("/api/v1/audit/logs", headers=auth["engineer"]).status_code == 404
    assert client.get("/api/v1/auth/users", headers=auth["engineer"]).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth["engineer"]).json()["role"] == "engineer"
    roles = client.get("/api/v1/meta").json()["auth_roles"]
    assert roles == ["engineer", "worker"]
    accounts = client.get("/api/v1/auth/users", headers=auth["engineer"]).json()
    assert {account["role"] for account in accounts} == {"engineer", "worker"}
    assert not {account["username"].lower() for account in accounts} & {
        "admin", "administrator", "fleet", "fleet_manager", "fleetmanager", "contractor", "contractor1"
    }
    assert client.post(
        "/api/v1/auth/users", headers=auth["engineer"],
        json={"username": "legacyrole", "password": "A-Temporary-Passphrase-987!", "role": "admin"},
    ).status_code == 422


def test_ingestion_requires_device_key_and_validates_payload(client, auth):
    payload = event_payload()
    assert client.post("/api/v1/events", json=payload).status_code == 401
    assert client.post("/api/v1/events", json={**payload, "timestamp": "2026-10-21T10:30:00"}, headers={"X-Device-Key": "pytest-device-key-for-ingestion-123456"}).status_code == 422
    mismatch = {**payload, "vehicle_label": "BUS-101", "route_id": "R22"}
    response = client.post("/api/v1/events", json=mismatch, headers={"X-Device-Key": "pytest-device-key-for-ingestion-123456"})
    assert response.status_code == 422, response.text


def test_event_idempotency_and_spatial_deduplication(client, auth):
    headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    payload = event_payload(lon=73.94134, lat=18.60523)
    first = client.post("/api/v1/events", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    first_body = first.json()

    replay = client.post("/api/v1/events", json=payload, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first_body["id"]
    assert replay.json()["hit_count"] == first_body["hit_count"]
    conflicting_replay = client.post("/api/v1/events", json={**payload, "lon": payload["lon"] + 0.01}, headers=headers)
    assert conflicting_replay.status_code == 409, conflicting_replay.text

    nearby = event_payload(lon=73.94140, lat=18.60525, minute=2)
    nearby_response = client.post("/api/v1/events", json=nearby, headers=headers)
    assert nearby_response.status_code == 200, nearby_response.text
    assert nearby_response.json()["id"] == first_body["id"]
    assert nearby_response.json()["hit_count"] == first_body["hit_count"] + 1


def test_review_is_required_before_dispatch(client, auth):
    headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    payload = event_payload(lon=73.92567, lat=18.59234)
    created = client.post("/api/v1/events", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    incident_id = created.json()["id"]

    before_review = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    assert before_review.status_code == 409, before_review.text

    reviewed = client.post(f"/api/v1/incidents/{incident_id}/review", headers=auth["engineer"], json={"status": "reviewing", "note": "Ground-truth spot check"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "reviewing"
    assert reviewed.json()["hash_valid"] is True

    dispatched = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["incident"]["status"] == "dispatched"
    assert dispatched.json()["work_order"]["ticket_no"].startswith("WO-")



def test_engineer_quick_status_updates_incident_and_order(client, auth):
    payload = event_payload(lon=73.95811, lat=18.61731)
    created = client.post("/api/v1/events", json=payload, headers={"X-Device-Key": "pytest-device-key-for-ingestion-123456"})
    assert created.status_code == 200, created.text
    incident_id = created.json()["id"]
    reviewed = client.post(f"/api/v1/incidents/{incident_id}/review", headers=auth["engineer"], json={"status": "reviewing", "note": "Quick-action test"})
    assert reviewed.status_code == 200, reviewed.text
    dispatched = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["incident"]["status"] == "dispatched"
    assert dispatched.json()["work_order"]["status"] == "dispatched"

    started = client.patch(f"/api/v1/incidents/{incident_id}/status", headers=auth["engineer"], json={"status": "in_progress"})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"

    resolved = client.patch(f"/api/v1/incidents/{incident_id}/status", headers=auth["engineer"], json={"status": "resolved"})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "awaiting_verification"
    assert resolved.json()["verification_status"] == "pending"
    orders = client.get("/api/v1/work-orders", headers=auth["engineer"]).json()
    order = next(row for row in orders if row["incident_id"] == incident_id)
    assert order["status"] == "resolved"
    assert "field evidence was not submitted" in order["completion_notes"]


def test_worker_scope_evidence_and_work_order_lifecycle(client, auth):
    headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    payload = event_payload(lon=73.94711, lat=18.60873)
    created = client.post("/api/v1/events", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    incident_id = created.json()["id"]
    review = client.post(f"/api/v1/incidents/{incident_id}/review", headers=auth["engineer"], json={"status": "reviewing", "note": "Review for assigned-worker test"})
    assert review.status_code == 200, review.text
    dispatched = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    assert dispatched.status_code == 200, dispatched.text
    order = dispatched.json()["work_order"]
    order_id = order["id"]

    users = client.get("/api/v1/auth/users", headers=auth["engineer"])
    assert users.status_code == 200
    worker = next(user for user in users.json() if user["username"] == "worker")
    assigned = client.patch(
        f"/api/v1/work-orders/{order_id}",
        headers=auth["engineer"],
        json={"assigned_to_id": worker["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_username"] == "worker"

    worker_headers = auth["worker"]
    visible = client.get("/api/v1/work-orders", headers=worker_headers)
    assert visible.status_code == 200, visible.text
    assert order_id in {item["id"] for item in visible.json()}
    assert all(item["assigned_to_id"] == worker["id"] for item in visible.json())
    assert client.get(f"/api/v1/work-orders/{order_id}/audit", headers=worker_headers).status_code == 404
    # Worker cannot change assignment/crew, but can start the assigned repair.
    forbidden = client.patch(f"/api/v1/work-orders/{order_id}", headers=worker_headers, json={"crew": "Other crew"})
    assert forbidden.status_code == 403
    started = client.patch(f"/api/v1/work-orders/{order_id}", headers=worker_headers, json={"status": "in_progress"})
    assert started.status_code == 200, started.text
    no_closeout = client.patch(f"/api/v1/work-orders/{order_id}", headers=worker_headers, json={"status": "resolved"})
    assert no_closeout.status_code == 422, no_closeout.text
    uploaded = client.post(
        f"/api/v1/work-orders/{order_id}/evidence", headers=worker_headers,
        files={"file": ("repair-proof.png", b"\x89PNG\r\n\x1a\nsmall-valid-signature", "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence = uploaded.json()["evidence_files"][0]
    download = client.get(evidence["download_url"], headers=worker_headers)
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG\r\n\x1a\n")
    completed = client.patch(
        f"/api/v1/work-orders/{order_id}",
        headers=worker_headers,
        json={"status": "resolved"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "resolved"
    assert completed.json()["completed_at"] is not None
    parent = client.get(f"/api/v1/incidents/{incident_id}", headers=auth["engineer"])
    assert parent.status_code == 200
    assert parent.json()["status"] == "awaiting_verification"
    assert parent.json()["verification_status"] == "pending"
    assert parent.json()["verification_passes"] == 0
    assert parent.json()["verification_required"] == 2
    post_closeout = client.patch(f"/api/v1/work-orders/{order_id}", headers=worker_headers, json={"completion_notes": "Changed after completion"})
    assert post_closeout.status_code == 409


def test_device_credentials_are_scoped_to_a_vehicle(client, auth):
    issued = client.post("/api/v1/telemetry/devices/BUS-101/credentials", headers=auth["engineer"])
    assert issued.status_code == 200, issued.text
    key = issued.json()["device_key"]
    assert "device_key_hash" not in issued.text
    valid_event = event_payload(vehicle="BUS-101", route="R12", lon=73.95002, lat=18.61188)
    accepted = client.post("/api/v1/events", json=valid_event, headers={"X-Device-Key": key})
    assert accepted.status_code == 200, accepted.text
    wrong_vehicle = event_payload(vehicle="BUS-102", route="R12", lon=73.95502, lat=18.61488)
    rejected = client.post("/api/v1/events", json=wrong_vehicle, headers={"X-Device-Key": key})
    assert rejected.status_code == 403, rejected.text


def test_public_audit_routes_and_new_log_writes_are_removed(client, auth):
    assert client.get("/api/v1/audit/logs", headers=auth["engineer"]).status_code == 404
    assert client.get("/api/v1/audit/verify", headers=auth["engineer"]).status_code == 404
    from app.database import SessionLocal
    from app.models import AuditLog
    with SessionLocal() as db:
        assert db.query(AuditLog).count() == 0


def test_password_change_revokes_previous_session(client, auth):
    created = client.post(
        "/api/v1/auth/users",
        headers=auth["engineer"],
        json={"username": f"pwtest_{uuid4().hex[:8]}", "password": "Temporary-Passphrase-123!", "role": "engineer"},
    )
    assert created.status_code == 201, created.text
    username = created.json()["username"]
    login = client.post("/api/v1/auth/login", json={"username": username, "password": "Temporary-Passphrase-123!"})
    assert login.status_code == 200
    old_token = login.json()["access_token"]
    updated = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"current_password": "Temporary-Passphrase-123!", "new_password": "New-Strong-Passphrase-456!"},
    )
    assert updated.status_code == 200, updated.text
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    fresh_token = updated.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh_token}"}).status_code == 200


def test_engineer_can_register_device_then_issue_a_scoped_key(client, auth):
    label = f"BUS-{uuid4().hex[:6].upper()}"
    created = client.post(
        "/api/v1/telemetry/devices",
        headers=auth["engineer"],
        json={"vehicle_label": label.lower(), "fleet_id": "pilot-fleet", "route_id": "R12", "software_version": "edge-1.2.3"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["vehicle_label"] == label
    assert created.json()["credential_configured"] is False

    bad_route = client.post(
        "/api/v1/telemetry/devices",
        headers=auth["engineer"],
        json={"vehicle_label": f"{label}X", "fleet_id": "pilot-fleet", "route_id": "R999"},
    )
    assert bad_route.status_code == 422

    issued = client.post(f"/api/v1/telemetry/devices/{label}/credentials", headers=auth["engineer"])
    assert issued.status_code == 200, issued.text
    key = issued.json()["device_key"]
    payload = event_payload(vehicle=label, route="R12", lon=73.95222, lat=18.61881)
    accepted = client.post("/api/v1/events", json=payload, headers={"X-Device-Key": key})
    assert accepted.status_code == 200, accepted.text


def test_duplicate_merge_archives_source_and_keeps_hash_integrity(client, auth):
    headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    first_payload = event_payload(lon=73.75210, lat=18.47210)
    second_payload = event_payload(lon=73.75210, lat=18.47272)
    first = client.post("/api/v1/events", json=first_payload, headers=headers)
    second = client.post("/api/v1/events", json=second_payload, headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]

    merged = client.post(
        f"/api/v1/incidents/{first.json()['id']}/merge",
        headers=auth["engineer"],
        json={"duplicate_id": second.json()["id"], "note": "Ground-truth duplicate merge"},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["hash_valid"] is True
    assert merged.json()["hit_count"] == first.json()["hit_count"] + second.json()["hit_count"]
    assert client.get(f"/api/v1/incidents/{second.json()['id']}", headers=auth["engineer"]).status_code == 404
    # Replaying an event absorbed by a manual merge resolves to the primary incident.
    replay = client.post("/api/v1/events", json=second_payload, headers={"X-Device-Key": "pytest-device-key-for-ingestion-123456"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]


def test_repaired_incident_requires_two_distinct_bus_checks_and_reopens_on_defect(client, auth):
    device_headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    base = event_payload(vehicle="BUS-101", route="R12", lon=73.77321, lat=18.57731)
    created = client.post("/api/v1/events", json=base, headers=device_headers)
    assert created.status_code == 200, created.text
    incident_id = created.json()["id"]
    reviewed = client.post(f"/api/v1/incidents/{incident_id}/review", headers=auth["engineer"], json={"status": "reviewing"})
    assert reviewed.status_code == 200, reviewed.text
    dispatch = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    assert dispatch.status_code == 200, dispatch.text
    order_id = dispatch.json()["work_order"]["id"]

    # The engineer assigns the work order to the seeded Field Crew account.
    users = client.get("/api/v1/auth/users", headers=auth["engineer"]).json()
    worker = next(row for row in users if row["username"] == "worker")
    assigned = client.patch(f"/api/v1/work-orders/{order_id}", headers=auth["engineer"], json={"assigned_to_id": worker["id"]})
    assert assigned.status_code == 200, assigned.text
    started = client.patch(f"/api/v1/work-orders/{order_id}", headers=auth["worker"], json={"status": "in_progress"})
    assert started.status_code == 200, started.text
    completed = client.patch(
        f"/api/v1/work-orders/{order_id}", headers=auth["worker"],
        json={"status": "resolved", "completion_notes": "Patch cured and compacted; ready for fleet verification."},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["incident_status"] == "awaiting_verification"
    assert completed.json()["verification_status"] == "pending"

    clean1 = {
        **event_payload(vehicle="BUS-102", route="R12", lon=base["lon"] + 0.00002, lat=base["lat"] + 0.00002),
        "event_id": f"verify-{uuid4().hex}", "severity": "clear",
        "sensors": {"depth_mm": 2, "surface_class": "clear", "rms_vibration": 0.25},
    }
    first_pass = client.post("/api/v1/events", json=clean1, headers=device_headers)
    assert first_pass.status_code == 200, first_pass.text
    assert first_pass.json()["id"] == incident_id
    assert first_pass.json()["status"] == "awaiting_verification"
    assert first_pass.json()["verification_passes"] == 1

    # Repeated checks by the same bus are recorded but do not inflate independent fleet confirmation.
    same_bus = {**clean1, "event_id": f"verify-{uuid4().hex}", "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    repeated_pass = client.post("/api/v1/events", json=same_bus, headers=device_headers)
    assert repeated_pass.status_code == 200, repeated_pass.text
    assert repeated_pass.json()["verification_passes"] == 1

    clean2 = {
        **clean1, "event_id": f"verify-{uuid4().hex}", "vehicle_label": "BUS-118", "route_id": "R18",
        "timestamp": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
    }
    second_pass = client.post("/api/v1/events", json=clean2, headers=device_headers)
    assert second_pass.status_code == 200, second_pass.text
    assert second_pass.json()["status"] == "verified_fixed"
    assert second_pass.json()["verification_status"] == "verified"
    assert second_pass.json()["verification_passes"] == 2
    assert second_pass.json()["verified_at"] is not None



def test_defect_seen_during_verification_reopens_incident(client, auth):
    headers = {"X-Device-Key": "pytest-device-key-for-ingestion-123456"}
    original = event_payload(vehicle="BUS-101", route="R12", lon=73.79221, lat=18.59873)
    created = client.post("/api/v1/events", json=original, headers=headers)
    incident_id = created.json()["id"]
    client.post(f"/api/v1/incidents/{incident_id}/review", headers=auth["engineer"], json={"status": "reviewing"})
    dispatch = client.post(f"/api/v1/incidents/{incident_id}/dispatch", headers=auth["engineer"])
    order_id = dispatch.json()["work_order"]["id"]
    users = client.get("/api/v1/auth/users", headers=auth["engineer"]).json()
    worker = next(row for row in users if row["username"] == "worker")
    client.patch(f"/api/v1/work-orders/{order_id}", headers=auth["engineer"], json={"assigned_to_id": worker["id"]})
    client.patch(f"/api/v1/work-orders/{order_id}", headers=auth["worker"], json={"status": "in_progress"})
    closeout = client.patch(f"/api/v1/work-orders/{order_id}", headers=auth["worker"], json={"status": "resolved", "completion_notes": "Patch complete."})
    assert closeout.status_code == 200, closeout.text

    recurrence = event_payload(vehicle="BUS-102", route="R12", lon=original["lon"] + 0.00002, lat=original["lat"] + 0.00002)
    recurrence["event_id"] = f"recurrence-{uuid4().hex}"
    detected = client.post("/api/v1/events", json=recurrence, headers=headers)
    assert detected.status_code == 200, detected.text
    assert detected.json()["id"] == incident_id
    assert detected.json()["status"] == "open"
    assert detected.json()["verification_status"] == "failed"


def test_supabase_access_token_maps_to_authorized_operational_user(client, monkeypatch):
    """A Supabase JWT is accepted by the API and mapped to the server-side Engineer profile."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://pavepulse-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-supabase-signing-secret-0123456789")
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        "sub": str(uuid4()),
        "email": "engineer@pavepulse.local",
        "aud": "authenticated",
        "iss": "https://pavepulse-test.supabase.co/auth/v1",
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "app_metadata": {},
        "user_metadata": {"role": "worker"},  # Untrusted and intentionally ignored.
    }, settings.supabase_jwt_secret, algorithm="HS256")

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "engineer"
    assert response.json()["role"] == "engineer"


def test_supabase_token_without_authorized_role_is_rejected(client, monkeypatch):
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://pavepulse-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-supabase-signing-secret-0123456789")
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        "sub": str(uuid4()),
        "email": "unknown@pavepulse.local",
        "aud": "authenticated",
        "iss": "https://pavepulse-test.supabase.co/auth/v1",
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "app_metadata": {},
        "user_metadata": {"role": "engineer"},
    }, settings.supabase_jwt_secret, algorithm="HS256")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_demo_geography_and_metadata_are_pune(client):
    from app.geo import CITY_CENTER, ROUTES, WARDS

    # longitude, latitude for Pune city centre (with modest coordinate tolerance).
    assert abs(CITY_CENTER[0] - 73.8567) < 0.001
    assert abs(CITY_CENTER[1] - 18.5204) < 0.001
    assert len(WARDS) == 8
    assert all(73.72 <= lon <= 73.98 and 18.45 <= lat <= 18.63
               for route in ROUTES.values() for lon, lat in route)

    meta = client.get("/api/v1/meta")
    assert meta.status_code == 200
    assert meta.json()["city"] == "Pune, Maharashtra, India"
    assert meta.json()["demo_dataset_label"] is None or "Pune" in meta.json()["demo_dataset_label"]


def test_seeded_demo_incidents_are_in_pune(client):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Incident

    with SessionLocal() as db:
        rows = db.execute(
            select(Incident).where(Incident.source_event_id.like("demo-pune-edge-%"))
        ).scalars().all()
    assert len(rows) >= 40, f"Expected a substantial Pune demo dataset, found {len(rows)} sample incidents"
    assert all(73.72 <= row.lon <= 73.98 and 18.45 <= row.lat <= 18.63 for row in rows)


def test_explicit_pune_demo_seed_removes_only_legacy_sample_rows(client, auth):
    from uuid import UUID
    from app.database import SessionLocal
    from app.models import EventReceipt, Incident, WorkOrder
    from app.seed import seed_demo_data_if_empty

    legacy_id = "demo-edge-legacy-bengaluru-test"
    payload = event_payload(event_id=legacy_id, lon=73.7525, lat=18.4725)
    created = client.post(
        "/api/v1/events", json=payload,
        headers={"X-Device-Key": "pytest-device-key-for-ingestion-123456"},
    )
    assert created.status_code == 200, created.text
    legacy_incident_id = created.json()["id"]

    with SessionLocal() as db:
        seed_demo_data_if_empty(db)
        assert db.get(EventReceipt, legacy_id) is None
        assert db.get(Incident, UUID(legacy_incident_id)) is None
        pune_samples = db.query(Incident).filter(Incident.source_event_id.like("demo-pune-edge-%")).count()
        assert pune_samples >= 40
        sample_orders = (
            db.query(WorkOrder)
            .join(Incident, WorkOrder.incident_id == Incident.id)
            .filter(Incident.source_event_id.like("demo-pune-edge-%"))
            .all()
        )
        assert len(sample_orders) >= 3
        assert {order.status for order in sample_orders} >= {"dispatched", "in_progress", "resolved"}

