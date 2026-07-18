"""Android-readiness backend: Bearer session, multi-audience Google Sign-In,
native login (token in body + long TTL), and FCM push routing. All against the
isolated blackvolt_test DB; no real Google/FCM network.
"""
import asyncio
import os
import time

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"
os.environ["VAPID_PUBLIC_KEY"] = "test-public"
os.environ["VAPID_PRIVATE_KEY"] = "test-private"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client, PushSubscription  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import fcm, push  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_tenant_client() -> tuple[int, int]:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"and-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Android Rider",
                    phone="+13035550166",
                    email=f"and-{os.urandom(4).hex()}@pgtest.local",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                    lang="en",
                )
                db.add(client)
                await db.commit()
                await db.refresh(client)
                return client.id, tenant.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


# ── Bearer session ───────────────────────────────────────────────────────────
def test_bearer_token_authenticates_me():
    _, tid = _seed_tenant_client()
    token = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid)
    c = TestClient(app)  # no cookie
    r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["authenticated"] is True


def test_bearer_garbage_is_anonymous():
    c = TestClient(app)
    r = c.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 200
    assert r.json()["authenticated"] is False


def test_cookie_wins_over_bearer():
    _, tid = _seed_tenant_client()
    good = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid)
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, good)
    # A bogus Bearer must not override a valid cookie.
    r = c.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.json()["authenticated"] is True


def test_bearer_reaches_protected_endpoint():
    _, tid = _seed_tenant_client()
    token = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid)
    c = TestClient(app)
    r = c.get("/api/v1/rides", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "rides" in r.json()


# ── Multi-audience Google Sign-In ────────────────────────────────────────────
def _fake_google(monkeypatch, aud: str):
    def fake_verify(*_a, **_k):
        return {
            "aud": aud,
            "email": "rider@example.com",
            "email_verified": True,
            "sub": "google-sub-123",
            "name": "Rider Example",
        }

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", fake_verify)


@pytest.mark.parametrize("aud", ["web-client.apps", "android-client.apps", "ios-client.apps"])
def test_google_accepts_all_configured_audiences(monkeypatch, aud):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps")
    monkeypatch.setenv("GOOGLE_CLIENT_IDS", "android-client.apps,ios-client.apps")
    get_settings.cache_clear()
    _fake_google(monkeypatch, aud)
    info = authsvc.verify_google_id_token("dummy")
    assert info["email"] == "rider@example.com"
    get_settings.cache_clear()


def test_google_rejects_unknown_audience(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "web-client.apps")
    monkeypatch.setenv("GOOGLE_CLIENT_IDS", "")
    get_settings.cache_clear()
    _fake_google(monkeypatch, "someone-elses-client.apps")
    with pytest.raises(authsvc.GoogleAuthError) as e:
        authsvc.verify_google_id_token("dummy")
    assert "audience_mismatch" in str(e.value)
    get_settings.cache_clear()


# ── Native login: token in body + long TTL ───────────────────────────────────
def test_native_login_returns_token_and_long_ttl(monkeypatch):
    monkeypatch.setattr(
        authsvc,
        "verify_google_id_token",
        lambda _t: {
            "email": f"nr-{os.urandom(3).hex()}@example.com",
            "sub": f"gs-{os.urandom(4).hex()}",
            "name": "Native Rider",
            "given_name": "Native",
            "family_name": "Rider",
        },
    )
    c = TestClient(app)
    r = c.post(
        "/api/v1/auth/login/google",
        json={"id_token": "x"},
        headers={"X-BV-Native": "1"},
    )
    assert r.status_code == 200
    token = r.json().get("token")
    assert token, "native login must return the session token in the body"
    payload = authsvc.decode_token(token)
    assert payload is not None
    ttl_left = payload["exp"] - time.time()
    # ~180 days, comfortably more than the 7-day web cookie.
    assert ttl_left > 60 * 24 * 3600


def test_web_login_does_not_leak_token(monkeypatch):
    monkeypatch.setattr(
        authsvc,
        "verify_google_id_token",
        lambda _t: {
            "email": f"wr-{os.urandom(3).hex()}@example.com",
            "sub": f"gs-{os.urandom(4).hex()}",
            "name": "Web Rider",
            "given_name": "Web",
            "family_name": "Rider",
        },
    )
    c = TestClient(app)
    r = c.post("/api/v1/auth/login/google", json={"id_token": "x"})  # no native header
    assert r.status_code == 200
    assert "token" not in r.json()


# ── FCM subscribe + delivery routing ─────────────────────────────────────────
def _staff(tid: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid))
    return c


def _sub_row(endpoint: str):
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return (
                    await db.execute(
                        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
                    )
                ).scalar_one_or_none()
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_fcm_subscribe_stores_platform_without_keys():
    _, tid = _seed_tenant_client()
    ep = f"fcm-token-{os.urandom(5).hex()}"
    r = _staff(tid).post("/api/v1/push/subscribe", json={"endpoint": ep, "platform": "fcm"})
    assert r.status_code == 200, r.text
    row = _sub_row(ep)
    assert row is not None and row.platform == "fcm"
    assert row.p256dh is None and row.auth is None


def test_webpush_subscribe_requires_keys():
    _, tid = _seed_tenant_client()
    ep = f"web-ep-{os.urandom(5).hex()}"
    r = _staff(tid).post("/api/v1/push/subscribe", json={"endpoint": ep, "platform": "webpush"})
    assert r.status_code == 422


def test_send_one_routes_fcm_to_fcm(monkeypatch):
    calls = []
    monkeypatch.setattr(fcm, "send", lambda *a, **k: calls.append((a, k)) or "sent")
    sub = PushSubscription(
        tenant_id=1, audience="client", platform="fcm", endpoint="tok-123", p256dh=None, auth=None
    )
    result = asyncio.run(
        push._send_one(sub, {"title": "T", "body": "B", "url": "/trips", "tag": "x"})
    )
    assert result == "sent"
    assert len(calls) == 1
    assert calls[0][0][0] == "tok-123"  # the registration token is passed through


def test_send_one_routes_webpush_to_webpush(monkeypatch):
    called = {"fcm": 0, "web": 0}

    def fake_fcm(*_a, **_k):
        called["fcm"] += 1
        return "sent"

    monkeypatch.setattr(fcm, "send", fake_fcm)

    def fake_webpush(*_a, **_k):
        called["web"] += 1

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    sub = PushSubscription(
        tenant_id=1, audience="staff", platform="webpush", endpoint="https://web/ep",
        p256dh="k", auth="a",
    )
    result = asyncio.run(push._send_one(sub, {"title": "T", "body": "B", "url": "/x", "tag": "y"}))
    assert result == "sent"
    assert called == {"fcm": 0, "web": 1}


def test_fcm_send_is_noop_without_creds(monkeypatch):
    # No FCM_* configured → send never raises and keeps the subscription.
    monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
    monkeypatch.delenv("FCM_CREDENTIALS_JSON_B64", raising=False)
    get_settings.cache_clear()
    fcm._reset_cache()
    assert fcm.send("tok", "T", "B", "/x", "y") == "keep"
    get_settings.cache_clear()
