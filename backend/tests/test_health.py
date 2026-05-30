"""Smoke test for the root + health endpoints (no DB required for root)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "Black Volt Mobility"
    assert "version" in body
