"""Multi-driver onboarding (Phase A): allow-list gating, auto-provisioned tenant,
isolation between drivers, and the Team admin API."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
# Keep test_auth_api's pinned admin too — env is process-global across test files;
# we union both so neither file's expectations break. GOOGLE_CLIENT_ID stays unset
# (we patch verify_google_id_token directly), so the "not configured" test still holds.
os.environ["GOOGLE_ADMIN_EMAILS"] = "admin@bv.com,owner@bv.test"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

OWNER = "owner@bv.test"


def _admin() -> TestClient:
    """Owner master session via the dashboard password (super-admin)."""
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"password": "test-pw"}).status_code == 200
    return c


def _google(email: str, name: str = "Friend") -> tuple[TestClient, dict]:
    """Sign in with a (mocked) verified Google identity."""
    c = TestClient(app)
    info = {"email": email, "sub": f"sub-{email}", "name": name}
    with patch("app.services.auth.verify_google_id_token", return_value=info):
        r = c.post("/api/v1/auth/login/google", json={"id_token": "x"})
    return c, r.json()


def _clear(*emails: str) -> None:
    """Remove allow-list rows for the given emails on a throwaway engine (own loop)
    so each test starts from a known state regardless of prior runs."""
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import AllowedUser

    async def go() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                await db.execute(
                    delete(AllowedUser).where(
                        AllowedUser.email.in_([e.lower() for e in emails])
                    )
                )
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _make_ride(c: TestClient, name: str) -> int:
    r = c.post(
        "/api/v1/rides",
        json={"pickup": "Cherry Creek", "dropoff": "DEN", "pax": 1, "passenger_name": name},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_team_requires_admin():
    # No session at all.
    assert TestClient(app).get("/api/v1/team").status_code == 401
    # A driver session is staff but NOT admin → 403.
    _clear("driver-403@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "driver-403@bv.test", "name": "D"})
    dc, body = _google("driver-403@bv.test")
    assert body["role"] == "owner" and body["is_admin"] is False
    assert dc.get("/api/v1/team").status_code == 403


def test_add_list_and_dedup():
    _clear("alex@bv.test")
    a = _admin()
    r = a.post("/api/v1/team", json={"email": "Alex@BV.test", "name": "Alex"})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["email"] == "alex@bv.test" and m["role"] == "driver"
    assert m["active"] is True and m["immutable"] is False
    # Duplicate → 409.
    assert a.post("/api/v1/team", json={"email": "alex@bv.test"}).status_code == 409
    emails = {x["email"] for x in a.get("/api/v1/team").json()}
    assert "alex@bv.test" in emails


def test_driver_first_login_provisions_isolated_tenant():
    _clear("bob@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "bob@bv.test", "name": "Bob"})
    # Bob signs in → owner of his OWN tenant (not black-volt), provisioned now.
    bob, body = _google("bob@bv.test", name="Bob Driver")
    assert body["role"] == "owner" and body["is_admin"] is False
    assert body["tenant"] not in (None, "black-volt")
    # Bob creates a ride; he sees it.
    _make_ride(bob, "BOBS-PASSENGER-XYZ")
    bob_rides = bob.get("/api/v1/rides").json()["rides"]
    assert any(r["passenger_name"] == "BOBS-PASSENGER-XYZ" for r in bob_rides)
    # The admin (black-volt tenant) must NOT see Bob's ride — tenant isolation.
    admin_rides = a.get("/api/v1/rides").json()["rides"]
    assert not any(r["passenger_name"] == "BOBS-PASSENGER-XYZ" for r in admin_rides)


def test_inactive_driver_cannot_access_dashboard():
    _clear("carol@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "carol@bv.test", "name": "Carol"})
    assert a.patch("/api/v1/team/carol@bv.test", json={"active": False}).status_code == 200
    # Deactivated → falls back to passenger, blocked from staff endpoints.
    carol, body = _google("carol@bv.test")
    assert body["role"] == "passenger"
    assert carol.get("/api/v1/auth/me").json()["role"] == "passenger"
    assert carol.get("/api/v1/dashboard/stats").status_code == 403


def test_reactivate_restores_driver_access():
    _clear("dave@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "dave@bv.test"})
    a.patch("/api/v1/team/dave@bv.test", json={"active": False})
    a.patch("/api/v1/team/dave@bv.test", json={"active": True})
    _dave, body = _google("dave@bv.test")
    assert body["role"] == "owner"


def test_pinned_admin_is_immutable_and_listed():
    # Owner google sign-in materializes the pinned admin row.
    _admin()  # ensure app/tenant exist
    _google(OWNER, name="Ender")
    a = _admin()
    row = next((x for x in a.get("/api/v1/team").json() if x["email"] == OWNER), None)
    assert row is not None and row["role"] == "admin" and row["immutable"] is True
    # Can't deactivate or remove the pinned admin.
    assert a.patch(f"/api/v1/team/{OWNER}", json={"active": False}).status_code == 400
    assert a.delete(f"/api/v1/team/{OWNER}").status_code == 400


def test_remove_driver():
    _clear("erin@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "erin@bv.test"})
    assert a.delete("/api/v1/team/erin@bv.test").status_code == 204
    assert "erin@bv.test" not in {x["email"] for x in a.get("/api/v1/team").json()}
