"""Client detail (CRM) API: GET /clients/{id} + PATCH /clients/{id}."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _seed_client(name: str = "CRM Test", lang: str | None = None) -> int:
    """Insert a client + 3 rides on a throwaway engine (own loop) so the data is
    committed to Postgres before the TestClient (app engine) reads it."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client, Ride, RideStatus
    from app.services.tenancy import get_default_tenant

    async def go() -> int:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                tenant = await get_default_tenant(db)
                c = Client(
                    tenant_id=tenant.id, name=name, phone="+15551234567",
                    email="crm@example.com", lang=lang,
                )
                db.add(c)
                await db.commit()
                await db.refresh(c)
                db.add_all([
                    Ride(tenant_id=tenant.id, client_id=c.id, status=RideStatus.COMPLETED,
                         pickup_text="Aurora", dropoff_text="DEN", fare_total=100.0,
                         paid=True, lang="ES"),
                    Ride(tenant_id=tenant.id, client_id=c.id, status=RideStatus.CONFIRMED,
                         pickup_text="Boulder", dropoff_text="DEN", fare_total=50.0, paid=False),
                    Ride(tenant_id=tenant.id, client_id=c.id, status=RideStatus.CANCELLED,
                         pickup_text="X", dropoff_text="Y", fare_total=999.0, paid=False),
                ])
                await db.commit()
                return c.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_client_detail_returns_profile_stats_and_history():
    cid = _seed_client()
    c = _owner()
    r = c.get(f"/api/v1/clients/{cid}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] == cid and d["name"] == "CRM Test"
    assert d["rides_count"] == 2          # completed + confirmed; cancelled excluded
    assert d["lifetime_spend"] == 100.0   # only the paid ride
    assert len(d["rides"]) == 3           # full history incl. cancelled
    assert d["lang"] == "ES"              # latest ride language (no client.lang yet)
    # Rides carry the brief shape.
    assert {"id", "status", "pickup", "dropoff", "fare_total"} <= set(d["rides"][0].keys())


def test_client_patch_updates_and_normalizes_lang():
    cid = _seed_client(name="Before")
    c = _owner()
    r = c.patch(
        f"/api/v1/clients/{cid}",
        json={"name": "After", "phone": "+1 999 000", "lang": "Spanish"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "After" and d["phone"] == "+1 999 000" and d["lang"] == "ES"
    # Persisted: a fresh GET reflects it.
    assert c.get(f"/api/v1/clients/{cid}").json()["lang"] == "ES"


def test_client_not_found():
    c = _owner()
    assert c.get("/api/v1/clients/99999999").status_code == 404
    assert c.patch("/api/v1/clients/99999999", json={"name": "x"}).status_code == 404


def test_client_requires_staff():
    c = TestClient(app)  # no session
    assert c.get("/api/v1/clients/1").status_code == 401
    assert c.patch("/api/v1/clients/1", json={"name": "x"}).status_code == 401
