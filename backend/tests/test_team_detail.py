"""Team member detail drawer read-model: GET /api/v1/team/{email}/detail.

Super-admin sees everything about one driver — identity/access, business KPIs,
30-day engagement, recent rides + activity. Verifies admin gating, the unknown
and never-logged-in edge cases, and that business aggregates are tenant-scoped."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["GOOGLE_ADMIN_EMAILS"] = "admin@bv.com,owner@bv.test"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _admin() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"password": "test-pw"}).status_code == 200
    return c


def _google(email: str, name: str = "Friend") -> tuple[TestClient, dict]:
    c = TestClient(app)
    info = {"email": email, "sub": f"sub-{email}", "name": name}
    with patch("app.services.auth.verify_google_id_token", return_value=info):
        r = c.post("/api/v1/auth/login/google", json={"id_token": "x"})
    return c, r.json()


def _clear(*emails: str) -> None:
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
                    delete(AllowedUser).where(AllowedUser.email.in_([e.lower() for e in emails]))
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


def test_detail_requires_admin():
    _clear("det-driver@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "det-driver@bv.test", "name": "D"})
    # No session → 401.
    assert TestClient(app).get("/api/v1/team/det-driver@bv.test/detail").status_code == 401
    # Driver session (staff, not admin) → 403.
    dc, body = _google("det-driver@bv.test")
    assert body["is_admin"] is False
    assert dc.get("/api/v1/team/det-driver@bv.test/detail").status_code == 403


def test_detail_unknown_email_404():
    a = _admin()
    assert a.get("/api/v1/team/nobody-here@bv.test/detail").status_code == 404


def test_detail_unprovisioned_member():
    """A member added but who never signed in has no tenant → provisioned False,
    empty stat blocks, no engagement."""
    _clear("det-pending@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "det-pending@bv.test", "name": "Pending"})
    d = a.get("/api/v1/team/det-pending@bv.test/detail")
    assert d.status_code == 200, d.text
    j = d.json()
    assert j["provisioned"] is False
    assert j["role"] == "driver" and j["active"] is True and j["immutable"] is False
    assert j["rides"] == {"total": 0, "completed": 0, "upcoming": 0, "cancelled": 0}
    assert j["revenue_total"] == 0.0 and j["clients"] == 0
    assert j["engagement"] is None
    assert j["recent_rides"] == [] and j["recent_activity"] == []
    assert j["subscription"] is None


def test_detail_aggregates_business_for_provisioned_driver():
    """After sign-in + a ride, the detail reports the driver's own tenant stats
    (provisioned, ride counted, recent ride listed, engagement block present)."""
    _clear("det-active@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "det-active@bv.test", "name": "Active"})
    drv, body = _google("det-active@bv.test", name="Active Driver")
    assert body["tenant"] not in (None, "black-volt")
    rid = _make_ride(drv, "DETAIL-PASSENGER-XYZ")

    d = a.get("/api/v1/team/det-active@bv.test/detail")
    assert d.status_code == 200, d.text
    j = d.json()
    assert j["provisioned"] is True
    assert j["last_login"] is not None
    assert j["tenant_slug"] not in (None, "black-volt")
    assert j["rides"]["total"] >= 1
    assert len(j["week"]) == 7 and "week_total" in j
    # The just-created ride shows in recent_rides.
    assert any(r["id"] == rid for r in j["recent_rides"])
    # Engagement block exists for a provisioned tenant (zeros are fine).
    assert j["engagement"] is not None
    for k in ("visitors", "sessions", "pageviews", "avg_session_ms"):
        assert k in j["engagement"]


def test_detail_is_tenant_scoped():
    """One driver's detail must not leak another driver's ride into recent_rides."""
    _clear("det-a@bv.test", "det-b@bv.test")
    a = _admin()
    a.post("/api/v1/team", json={"email": "det-a@bv.test"})
    a.post("/api/v1/team", json={"email": "det-b@bv.test"})
    ca, _ = _google("det-a@bv.test")
    cb, _ = _google("det-b@bv.test")
    _make_ride(ca, "ONLY-A-PASSENGER")
    rid_b = _make_ride(cb, "ONLY-B-PASSENGER")

    ja = a.get("/api/v1/team/det-a@bv.test/detail").json()
    assert not any(r["id"] == rid_b for r in ja["recent_rides"])
