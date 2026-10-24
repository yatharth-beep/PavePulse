"""Isolated API-test settings; set before importing the FastAPI application."""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:////tmp/pavepulse-pytest-{os.getpid()}.db"
os.environ["SIMULATOR_ENABLED"] = "false"
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["JWT_SECRET"] = "pytest-secret-with-sufficient-length-0123456789"
os.environ["DEVICE_API_KEY"] = "pytest-device-key-for-ingestion-123456"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"
os.environ["EVIDENCE_STORAGE_DIR"] = f"/tmp/pavepulse-test-evidence-{os.getpid()}"

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def tokens(client):
    def login(username: str, password: str) -> str:
        response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return {
        "engineer": login("engineer", "engineer123"),
        "worker": login("worker", "worker123"),
    }


@pytest.fixture
def auth(tokens):
    return {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}
