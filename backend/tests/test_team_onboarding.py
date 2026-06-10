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


def test_stale_owner_session_recovers_admin():
    """A pre-`adm` owner cookie (minted before v0.21.0) still counts as admin —
    no re-login needed."""
    from app.services import auth as A

    a = _admin()
    default_tid = a.get("/api/v1/auth/me").json()["tenant_id"]
    stale = A.make_token(role=A.ROLE_OWNER, tenant_id=default_tid)  # no is_admin flag
    c = TestClient(app)
    c.cookies.set("bv_auth", stale)
    assert c.get("/api/v1/auth/me").json()["is_admin"] is True
    assert c.get("/api/v1/team").status_code == 200


def test_driver_owner_token_is_not_admin():
    """An owner session on a driver's own tenant must never be treated as admin."""
    from app.services import auth as A

    _clear("frank@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "frank@bv.test"})
    fr, body = _google("frank@bv.test")
    assert body["role"] == "owner" and body["is_admin"] is False
    driver_tid = fr.get("/api/v1/auth/me").json()["tenant_id"]
    tok = A.make_token(role=A.ROLE_OWNER, tenant_id=driver_tid)  # owner of their own tenant
    c = TestClient(app)
    c.cookies.set("bv_auth", tok)
    assert c.get("/api/v1/auth/me").json()["is_admin"] is False
    assert c.get("/api/v1/team").status_code == 403


# ── v0.22.0: roles, welcome email, stats, resend ────────────────────────────


def test_add_member_returns_email_status():
    """Adding a member triggers the welcome email; EMAIL_SIMULATED (default) →
    'simulated' status surfaced to the owner."""
    _clear("grace@bv.test")
    a = _admin()
    r = a.post("/api/v1/team", json={"email": "grace@bv.test", "name": "Grace", "lang": "es"})
    assert r.status_code == 201, r.text
    assert r.json()["email_status"] == "simulated"


def test_resend_invite():
    _clear("hank@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "hank@bv.test"})
    r = a.post("/api/v1/team/hank@bv.test/resend-invite")
    assert r.status_code == 200, r.text
    assert r.json()["email_status"] == "simulated"
    # Unknown member → 404.
    assert a.post("/api/v1/team/nobody@bv.test/resend-invite").status_code == 404


def test_promote_and_demote_role():
    _clear("ivy@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "ivy@bv.test"})
    assert a.patch("/api/v1/team/ivy@bv.test", json={"role": "admin"}).json()["role"] == "admin"
    assert a.patch("/api/v1/team/ivy@bv.test", json={"role": "driver"}).json()["role"] == "driver"
    # Bad role value → 422 (schema validation).
    assert a.patch("/api/v1/team/ivy@bv.test", json={"role": "ceo"}).status_code == 422


def test_cannot_demote_pinned_admin():
    """A pinned (env) admin can't be demoted to driver."""
    _admin()
    _google(OWNER, name="Ender")  # materialize the pinned admin row
    a = _admin()
    assert a.patch(f"/api/v1/team/{OWNER}", json={"role": "driver"}).status_code == 400


def test_last_login_and_ride_stats_in_team_list():
    """A driver's last_login is stamped on sign-in and their ride count shows in
    the Team list the owner sees."""
    _clear("jane@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "jane@bv.test", "name": "Jane"})
    jane, _ = _google("jane@bv.test", name="Jane")
    _make_ride(jane, "JANES-PASSENGER")
    row = next((x for x in a.get("/api/v1/team").json() if x["email"] == "jane@bv.test"), None)
    assert row is not None
    assert row["last_login"] is not None
    assert row["rides"] >= 1
    assert "revenue" in row and row["revenue"] >= 0
