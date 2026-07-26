"""A discount must survive editing the ride.

Re-quoting on a route/time edit used to call build_quote() without the ride's discount
context, so the fare silently jumped back to LIST price — overcharging the customer and
inflating the base the assigned driver is paid on. Isolated blackvolt_test DB only.
"""
import asyncio
import datetime as dt
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Ride  # noqa: E402
from app.services import booking  # noqa: E402
from app.services import discounts as D  # noqa: E402
from tests.test_ride_messages_api import _seed_tenant_client, _session_factory  # noqa: E402

PICKUP = "1600 Glenarm Pl, Denver"
DROPOFF = "Denver Intl (DEN)"


def _make_code(tenant_id: int, pct: int = 20) -> str:
    code = f"SAVE{os.urandom(2).hex().upper()}"

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                await D.create_code(
                    db,
                    tenant_id=tenant_id,
                    is_admin=True,
                    code=code,
                    discount_pct=pct,
                    max_uses=50,
                    expires_at=dt.datetime(2030, 1, 1, 0, 0),
                    created_by_email="owner@test.local",
                )
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())
    return code


def _quote_and_ride(tenant_id: int, code: str | None) -> tuple[int, float, float]:
    """Book a ride (optionally with a code) and return (ride_id, fare, discount)."""

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = await booking.create_ride(
                    db,
                    tenant_id=tenant_id,
                    pickup=PICKUP,
                    dropoff=DROPOFF,
                    scheduled_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=3),
                    passenger_name="Test Rider",
                    discount_code=code,
                )
                return ride.id, ride.fare_total, ride.discount_amount
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _edit(ride_id: int, **changes) -> tuple[float, float, dict]:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = await db.get(Ride, ride_id)
                await booking.apply_ride_update(db, ride=ride, changes=changes, persist=False)
                return ride.fare_total, ride.discount_amount, ride.price_breakdown
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _discount_line(breakdown: dict) -> float:
    for line in (breakdown or {}).get("lines", []):
        if line.get("label") in ("discount_code", "loyalty_discount"):
            return abs(line["amount"])
    return 0.0


def test_editing_the_route_keeps_the_discount():
    """THE regression: changing the pickup must not put the fare back to list price."""
    _cid, tenant = _seed_tenant_client("disc")
    code = _make_code(tenant, pct=20)
    ride_id, fare_with, disc = _quote_and_ride(tenant, code)
    assert disc > 0, "the booking itself must record the discount"

    fare_after, disc_after, breakdown = _edit(ride_id, pickup="1700 Lincoln St, Denver")

    assert disc_after > 0, "the discount was wiped by the edit"
    assert _discount_line(breakdown) > 0, "the breakdown lost its discount line"
    # The re-quoted fare must still be BELOW the undiscounted price for the same trip.
    _cid2, plain_tenant = _seed_tenant_client("plain")
    _rid, list_price, _d = _quote_and_ride(plain_tenant, None)
    assert fare_after < list_price, f"{fare_after} should be under list {list_price}"


def test_editing_the_time_keeps_the_discount():
    _cid, tenant = _seed_tenant_client("disctime")
    code = _make_code(tenant, pct=20)
    ride_id, _fare, disc = _quote_and_ride(tenant, code)
    assert disc > 0

    _fare_after, disc_after, breakdown = _edit(
        ride_id, scheduled_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=5)
    )
    assert disc_after > 0
    assert _discount_line(breakdown) > 0


def test_discount_amount_matches_the_breakdown_after_an_edit():
    """discount_amount used to go stale — it must always equal the breakdown's line."""
    _cid, tenant = _seed_tenant_client("discsync")
    code = _make_code(tenant, pct=25)
    ride_id, _f, _d = _quote_and_ride(tenant, code)

    _fare, disc_after, breakdown = _edit(ride_id, pickup="2000 Larimer St, Denver")
    assert round(disc_after, 2) == round(_discount_line(breakdown), 2)


def test_a_ride_without_a_discount_is_unaffected():
    """No-regression: a plain ride re-quotes exactly as before."""
    _cid, tenant = _seed_tenant_client("nodisc")
    ride_id, fare, disc = _quote_and_ride(tenant, None)
    assert disc == 0

    fare_after, disc_after, breakdown = _edit(ride_id, pickup="2000 Larimer St, Denver")
    assert disc_after == 0
    assert _discount_line(breakdown) == 0
    assert fare_after > 0
