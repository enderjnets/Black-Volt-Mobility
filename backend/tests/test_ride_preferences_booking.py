"""Per-ride preferences in the booking flow: a ride can carry an explicit
preference snapshot, otherwise it inherits the client's standing preferences.
DB-backed (long-lived dev database; rows use unique names to stay isolated)."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
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


def _seed_client_with_prefs(prefs: dict) -> int:
    """Insert a Client in the default (owner) tenant with standing prefs; return id."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client

    async def go() -> int:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                c = Client(
                    tenant_id=1,
                    name=f"Pref {uuid.uuid4().hex[:8]}",
                    ride_preferences=prefs,
                )
                db.add(c)
                await db.commit()
                await db.refresh(c)
                return c.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_create_ride_accepts_explicit_preferences():
    r = _owner().post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek",
            "dropoff": "Denver Intl (DEN)",
            "pax": 1,
            "ride_preferences": {"music": "soft", "conversation": "quiet"},
        },
    )
    assert r.status_code == 201, r.text
    prefs = r.json()["ride_preferences"]
    assert prefs["music"] == "soft"
    assert prefs["conversation"] == "quiet"
    assert prefs["temperature"] == "no_pref"  # unset dimensions default


def test_create_ride_invalid_preferences_422():
    r = _owner().post(
        "/api/v1/rides",
        json={"pickup": "A", "dropoff": "B", "pax": 1, "ride_preferences": {"music": "bogus"}},
    )
    assert r.status_code == 422, r.text


def test_create_ride_snapshots_client_standing_preferences():
    cid = _seed_client_with_prefs({"pet": True, "temperature": "warmer"})
    r = _owner().post(
        "/api/v1/rides",
        json={"pickup": "A", "dropoff": "B", "pax": 1, "client_id": cid},
    )
    assert r.status_code == 201, r.text
    prefs = r.json()["ride_preferences"]
    assert prefs["pet"] is True
    assert prefs["temperature"] == "warmer"
    assert prefs["music"] == "no_pref"


def test_create_ride_without_client_or_prefs_is_null():
    r = _owner().post("/api/v1/rides", json={"pickup": "A", "dropoff": "B", "pax": 1})
    assert r.status_code == 201, r.text
    assert r.json()["ride_preferences"] is None


def test_explicit_preferences_win_over_client_standing():
    cid = _seed_client_with_prefs({"music": "none"})
    r = _owner().post(
        "/api/v1/rides",
        json={
            "pickup": "A",
            "dropoff": "B",
            "pax": 1,
            "client_id": cid,
            "ride_preferences": {"music": "driver_choice"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["ride_preferences"]["music"] == "driver_choice"
