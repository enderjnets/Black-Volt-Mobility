"""Auth API tests. DB-backed (get_default_tenant) — run with Postgres available
(CI service / compose db). Sets the dashboard password before app import."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()  # re-read env (set above) before the app caches settings

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_login_wrong_password():
    r = client.post("/api/v1/auth/login", json={"password": "nope"})
    assert r.status_code == 401


def test_login_ok_sets_cookie_and_me():
    r = client.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "owner"
    assert "bv_auth" in r.cookies
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["authenticated"] is True
    assert body["role"] == "owner"


def test_logout_clears_session():
    client.post("/api/v1/auth/login", json={"password": "test-pw"})
    client.post("/api/v1/auth/logout")
    me = client.get("/api/v1/auth/me")
    assert me.json()["authenticated"] is False


def test_google_login_not_configured():
    # No GOOGLE_CLIENT_ID set → verify raises before any DB work → 401.
    r = client.post("/api/v1/auth/login/google", json={"id_token": "x"})
    assert r.status_code == 401
    assert "google_signin_not_configured" in r.json()["detail"]


def test_me_open_mode_reports_flags():
    fresh = TestClient(app)
    body = fresh.get("/api/v1/auth/me").json()
    assert "auth_enabled" in body
    assert "google_signin_enabled" in body
