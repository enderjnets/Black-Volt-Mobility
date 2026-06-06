"""Overdue rides: badge flag, manual confirm, and auto-complete when paid."""
import os
from datetime import UTC, datetime, timedelta

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["CALENDAR_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Ride, RideStatus  # noqa: E402
from app.services import booking  # noqa: E402


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _past(days=1):
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _future(days=2):
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def test_is_overdue_logic():
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=1)
    assert booking.is_overdue(Ride(scheduled_at=past, status=RideStatus.CONFIRMED)) is True
    assert booking.is_overdue(Ride(scheduled_at=future, status=RideStatus.CONFIRMED)) is False
    # Inactive statuses are never overdue.
    assert booking.is_overdue(Ride(scheduled_at=past, status=RideStatus.COMPLETED)) is False
    assert booking.is_overdue(Ride(scheduled_at=past, status=RideStatus.CANCELLED)) is False
    # No schedule → never overdue.
    assert booking.is_overdue(Ride(scheduled_at=None, status=RideStatus.CONFIRMED)) is False


def test_past_unpaid_ride_is_overdue_in_payload():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Arvada, CO", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert detail["overdue"] is True
    assert detail["status"] not in ("completed", "cancelled", "no_show")


def test_future_ride_not_overdue():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Parker, CO", "dropoff": "DEN", "scheduled_at": _future(), "confirm": True},
    ).json()["id"]
    assert c.get(f"/api/v1/rides/{rid}").json()["overdue"] is False


def test_marking_past_ride_paid_auto_completes():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Aurora, CO", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    c.patch(f"/api/v1/rides/{rid}", json={"paid": True})
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert detail["status"] == "completed"
    assert detail["overdue"] is False


def test_manual_confirm_completes_unpaid_past_ride():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "Lone Tree", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    # Driver confirms the pickup happened without payment.
    c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"})
    assert c.get(f"/api/v1/rides/{rid}").json()["status"] == "completed"


def test_patch_naive_scheduled_at_on_paid_ride_no_crash():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "D", "dropoff": "DEN", "scheduled_at": _future(), "confirm": True},
    ).json()["id"]
    # A naive datetime (no offset) in the past must not crash is_overdue.
    naive_past = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    r = c.patch(f"/api/v1/rides/{rid}", json={"scheduled_at": naive_past, "paid": True})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/v1/rides/{rid}").json()["status"] == "completed"


@pytest.mark.asyncio
async def test_explicit_cancel_respected_on_paid_past_ride():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "E", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    from app.db.base import get_session_factory

    async with get_session_factory()() as s:
        ride = await s.get(Ride, rid)
        ride.paid = True  # paid + past + active
        await s.commit()
    # An explicit cancel must NOT be auto-completed (cancelled is never overdue).
    c.patch(f"/api/v1/rides/{rid}", json={"status": "cancelled"})
    assert c.get(f"/api/v1/rides/{rid}").json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_detail_view_completes_paid_past_ride():
    c = _owner()
    rid = c.post(
        "/api/v1/rides",
        json={"pickup": "F", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    from app.db.base import get_session_factory

    async with get_session_factory()() as s:
        ride = await s.get(Ride, rid)
        ride.paid = True
        await s.commit()
    # Opening the detail directly (no list sweep) still closes a paid past ride.
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert detail["status"] == "completed"
    assert detail["overdue"] is False


@pytest.mark.asyncio
async def test_reconcile_only_completes_paid_past_active():
    c = _owner()
    paid_past = c.post(
        "/api/v1/rides",
        json={"pickup": "A", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    unpaid_past = c.post(
        "/api/v1/rides",
        json={"pickup": "B", "dropoff": "DEN", "scheduled_at": _past(), "confirm": True},
    ).json()["id"]
    paid_future = c.post(
        "/api/v1/rides",
        json={"pickup": "C", "dropoff": "DEN", "scheduled_at": _future(), "confirm": True},
    ).json()["id"]

    from app.db.base import get_session_factory

    async with get_session_factory()() as s:
        # Flip paid directly (bypass patch auto-complete) to isolate reconcile.
        for rid in (paid_past, paid_future):
            ride = await s.get(Ride, rid)
            ride.paid = True
        await s.commit()
        tenant_id = (await s.get(Ride, paid_past)).tenant_id
        await booking.reconcile_overdue_paid(s, tenant_id=tenant_id)
        await s.commit()
        assert (await s.get(Ride, paid_past)).status == RideStatus.COMPLETED
        assert (await s.get(Ride, unpaid_past)).status != RideStatus.COMPLETED
        assert (await s.get(Ride, paid_future)).status != RideStatus.COMPLETED
