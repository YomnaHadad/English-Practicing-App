import os
import tempfile

# Must be set before the backend is imported
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest
from fastapi.testclient import TestClient

from backend.db import Base, engine
from backend.main import app


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    """Register + log in; returns headers for an authenticated user."""
    client.post(
        "/api/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "password123", "full_name": "Alice"},
    )
    token = client.post("/api/auth/token", data={"username": "alice", "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
