"""Event payment enforcement at the API boundary (regression for the audit findings):
event rides can't be confirmed as cash via confirm=true, and a round-trip return leg
can't be confirmed on its own."""

import asyncio
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_VENUE = "Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204"


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


async def _seed_event() -> str:
    from app.db.base import get_session_factory
    from app.models import Event
    from app.services.tenancy import owner_tenant_id

    async with get_session_factory()() as db:
        tid = await owner_tenant_id(db)
        slug = f"evt-{uuid.uuid4().hex[:8]}"
        db.add(
            Event(
                tenant_id=tid, slug=slug, title="Ed Sheeran", venue_key="empower_field",
                venue_name="Empower Field at Mile High",
                venue_address="1701 Bryant St, Denver, CO 80204",
                starts_at=dt.datetime(2026, 8, 14, 2, 0, tzinfo=dt.UTC), status="published",
                event_fee=0, night_fee=25, wait_fee_per_hour=40, est_duration_hours=3,
            )
        )
        await db.commit()
    return slug


def test_confirm_true_event_forced_to_quoted():
    # Audit finding 1: an event ride with confirm=true must NOT become a confirmed cash ride.
    c = _owner()
    asyncio.run(_seed_event())
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek, Denver, CO", "dropoff": _VENUE,
            "scheduled_at": "2026-08-14T01:00:00Z", "confirm": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["price_breakdown"].get("event")  # it IS an event ride
    assert body["status"] == "quoted"  # ...so confirm was ignored — must pay by card


def test_confirm_true_non_event_still_confirms():
    c = _owner()
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek, Denver, CO", "dropoff": "Union Station, Denver, CO",
            "scheduled_at": "2026-08-14T01:00:00Z", "confirm": True,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "confirmed"  # everyday rides unaffected


def test_confirm_return_leg_blocked():
    # Audit finding 2: a round-trip return leg is confirmed/paid only via its outbound.
    c = _owner()
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek, Denver, CO", "dropoff": "Union Station, Denver, CO",
            "scheduled_at": "2026-08-14T01:00:00Z", "return_at": "2026-08-14T05:00:00Z",
            "round_trip": True,
        },
    )
    assert r.status_code == 201, r.text
    ret_id = r.json()["return_ride_id"]
    assert ret_id
    r2 = c.post(f"/api/v1/rides/{ret_id}/confirm")
    assert r2.status_code == 400, r2.text
    assert r2.json()["detail"] == "confirm_via_outbound"
