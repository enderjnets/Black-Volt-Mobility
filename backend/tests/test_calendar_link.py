"""Per-user Google Calendar connect flow (OAuth endpoints)."""
import os
import urllib.parse

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")
os.environ.setdefault("MAPS_SIMULATED", "true")

from cryptography.fernet import Fernet  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"password": "test-pw"}).status_code == 200
    return c


def _enable_oauth(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(
        s, "GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com", raising=False
    )
    monkeypatch.setattr(s, "GOOGLE_OAUTH_CLIENT_SECRET", "shh-secret", raising=False)
    monkeypatch.setattr(s, "CALENDAR_TOKEN_ENC_KEY", Fernet.generate_key().decode(), raising=False)


def _disable_oauth(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "GOOGLE_OAUTH_CLIENT_ID", "", raising=False)
    monkeypatch.setattr(s, "GOOGLE_OAUTH_CLIENT_SECRET", "", raising=False)
    monkeypatch.setattr(s, "CALENDAR_TOKEN_ENC_KEY", "", raising=False)


def test_connection_requires_auth(monkeypatch):
    monkeypatch.setattr(get_settings(), "AUTH_ENABLED", True, raising=False)
    r = TestClient(app).get("/api/v1/calendar/connection")
    assert r.status_code == 401


def test_connect_unconfigured_returns_503(monkeypatch):
    _disable_oauth(monkeypatch)
    c = _owner()
    r = c.post("/api/v1/calendar/connect")
    assert r.status_code == 503
    assert r.json()["detail"] == "calendar_oauth_unconfigured"


def test_connect_returns_consent_url(monkeypatch):
    _enable_oauth(monkeypatch)
    c = _owner()
    r = c.post("/api/v1/calendar/connect")
    assert r.status_code == 200
    url = r.json()["auth_url"]
    assert "accounts.google.com" in url
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert "calendar.events" in q["scope"][0]
    assert q.get("state")  # CSRF state present


def test_callback_bad_state_redirects_error(monkeypatch):
    _enable_oauth(monkeypatch)
    c = _owner()
    r = c.get(
        "/api/v1/calendar/callback",
        params={"code": "x", "state": "tampered.sig"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "calendar=error" in r.headers["location"]


def test_callback_error_param_redirects_error(monkeypatch):
    c = _owner()
    r = c.get(
        "/api/v1/calendar/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "calendar=error" in r.headers["location"]


def test_full_connect_then_disconnect(monkeypatch):
    _enable_oauth(monkeypatch)

    # Fake the OAuth exchange so no network is needed.
    class _FakeCreds:
        refresh_token = "1//0gFakeRefreshToken"
        id_token = None

    class _FakeFlow:
        def __init__(self, state=None):
            self.state = state
            self.credentials = _FakeCreds()

        def authorization_url(self, **kw):
            return (
                f"https://accounts.google.com/o/oauth2/auth?state={self.state}",
                self.state,
            )

        def fetch_token(self, code=None):
            return None

    import app.api.v1.calendar_link as cl

    monkeypatch.setattr(cl, "_flow", lambda state=None: _FakeFlow(state))

    revoked = {"called": False}

    def _fake_post(url, **kwargs):
        revoked["called"] = True

        class R:
            status_code = 200

        return R()

    monkeypatch.setattr("requests.post", _fake_post)

    c = _owner()

    # 1) Get a valid signed state from connect.
    connect = c.post("/api/v1/calendar/connect").json()
    state = urllib.parse.parse_qs(
        urllib.parse.urlparse(connect["auth_url"]).query
    )["state"][0]

    # 2) Complete the callback → stored + redirect connected.
    cb = c.get(
        "/api/v1/calendar/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 302
    assert "calendar=connected" in cb.headers["location"]

    # 3) Status reflects connected, and the token is stored ENCRYPTED.
    status = c.get("/api/v1/calendar/connection").json()
    assert status["connected"] is True

    import asyncio

    import asyncpg

    async def _fetch_enc():
        conn = await asyncpg.connect(
            os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
        )
        try:
            return await conn.fetch("select refresh_token_enc from calendar_credential")
        finally:
            await conn.close()

    stored = asyncio.run(_fetch_enc())
    assert stored, "credential row should exist"
    for row in stored:
        enc = row["refresh_token_enc"]
        assert enc != "1//0gFakeRefreshToken"  # never plaintext
        assert "1//0gFakeRefreshToken" not in enc

    # 4) Disconnect revokes + removes the row.
    dr = c.post("/api/v1/calendar/disconnect")
    assert dr.status_code == 200
    assert revoked["called"] is True
    assert c.get("/api/v1/calendar/connection").json()["connected"] is False
