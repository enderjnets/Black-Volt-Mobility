"""Round-trip booking: linked rides, split fares, single payment covering both legs."""

import datetime as dt
import os
import uuid
from zoneinfo import ZoneInfo

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Event, Tenant  # noqa: E402
from app.models.ride import RideStatus  # noqa: E402
from app.services import booking, payments  # noqa: E402
from app.services.payments_square import PaymentError  # noqa: E402

_DENVER = ZoneInfo("America/Denver")


def _denver(y, mo, d, h, mi=0) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=_DENVER).astimezone(dt.UTC)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db, monkeypatch):
    t = Tenant(slug=f"ev-{uuid.uuid4().hex[:8]}", name="Event Test")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    monkeypatch.setattr(get_settings(), "OWNER_TENANT_ID", t.id)
    return t.id


async def _mk_event(db, tid) -> Event:
    ev = Event(
        tenant_id=tid, slug=f"evt-{uuid.uuid4().hex[:8]}", title="Ed Sheeran",
        venue_key="empower_field", venue_name="Empower Field at Mile High",
        venue_address="1701 Bryant St, Denver, CO 80204",
        starts_at=_denver(2026, 7, 4, 20, 0), status="published",
        event_fee=40, night_fee=25, wait_fee_per_hour=30, est_duration_hours=3,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest.mark.asyncio
async def test_build_round_trip_quote_event_fees_once(db, owner):
    await _mk_event(db, owner)
    q = await booking.build_round_trip_quote(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    labels = [x["label"] for x in q["lines"]]
    assert labels.count("event_fee") == 1
    assert labels.count("wait_fee") == 1
    assert q["round_trip"] is True
    # 120 + 120 + 40 + 25 + 90.
    assert q["total"] == 395.0


@pytest.mark.asyncio
async def test_create_round_trip_links_and_splits(db, owner):
    await _mk_event(db, owner)
    outbound, ret = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    assert outbound.return_ride_id == ret.id
    assert ret.is_return is True and outbound.is_return is False
    assert round(outbound.fare_total + ret.fare_total, 2) == 395.0
    assert outbound.price_breakdown["round_trip_total"] == 395.0


@pytest.mark.asyncio
async def test_payment_covers_both_legs(db, owner):
    await _mk_event(db, owner)
    outbound, ret = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=outbound, source_id="cnon:card-nonce-ok",
    )
    # Charge equals the combined total, not just the outbound share.
    assert pay.amount == 39500
    # Event rides are captured in full at booking (not held), so both legs are paid now.
    assert pay.status.value == "captured"
    await db.refresh(outbound)
    await db.refresh(ret)
    assert outbound.status == RideStatus.CONFIRMED
    assert ret.status == RideStatus.CONFIRMED
    assert ret.payment_id == outbound.payment_id
    assert outbound.paid is True and ret.paid is True


@pytest.mark.asyncio
async def test_paid_round_trip_route_edit_blocked(db, owner):
    await _mk_event(db, owner)
    outbound, ret = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    # Event round trip is captured (paid) at authorize.
    await payments.authorize_for_ride(
        db, tenant_id=owner, ride=outbound, source_id="cnon:card-nonce-ok",
    )
    await db.refresh(outbound)
    assert outbound.paid is True
    with pytest.raises(booking.RoundTripLockedError):
        await booking.apply_ride_update(
            db, ride=outbound, changes={"pickup": "Elsewhere, CO"}, persist=True
        )


@pytest.mark.asyncio
async def test_cannot_pay_return_leg_directly(db, owner):
    # Fee-dodge guard: authorizing the return leg (which carries only its own fare) must be
    # refused — payment has to go through the outbound, which sums both legs.
    await _mk_event(db, owner)
    outbound, ret = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    with pytest.raises(PaymentError):
        await payments.authorize_for_ride(
            db, tenant_id=owner, ride=ret, source_id="cnon:card-nonce-ok",
        )


@pytest.mark.asyncio
async def test_round_trip_ignores_client_amount(db, owner):
    # A client-supplied `amount` must not undercut the combined round-trip charge.
    await _mk_event(db, owner)
    outbound, _ = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=outbound, source_id="cnon:card-nonce-ok", amount=1,
    )
    assert pay.amount == 39500  # server-computed combined total, not the client's 1 cent


@pytest.mark.asyncio
async def test_override_below_return_fare_no_negative_leg(db, owner):
    ev = await _mk_event(db, owner)
    ev.round_trip_price = 100  # below the ~$120 return-leg fare
    await db.commit()
    outbound, ret = await booking.create_round_trip(
        db, tenant_id=owner, pickup="Downtown Denver, CO",
        dropoff="Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204",
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )
    assert outbound.fare_total >= 0 and ret.fare_total >= 0
    assert round(outbound.fare_total + ret.fare_total, 2) == 100.0


_VENUE = "Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204"


async def _event_ride(db, owner):
    return await booking.create_ride(
        db, tenant_id=owner, pickup="Cherry Creek, Denver, CO", dropoff=_VENUE,
        scheduled_at=_denver(2026, 7, 4, 19, 0),
    )


@pytest.mark.asyncio
async def test_one_way_event_captured_at_booking(db, owner):
    await _mk_event(db, owner)
    ride = await _event_ride(db, owner)
    assert ride.price_breakdown.get("event")  # detected as an event ride
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=ride, source_id="cnon:card-nonce-ok"
    )
    assert pay.status.value == "captured"  # charged in full now, not just held
    await db.refresh(ride)
    assert ride.paid is True and ride.status == RideStatus.CONFIRMED


@pytest.mark.asyncio
async def test_non_event_ride_only_held(db, owner):
    ride = await booking.create_ride(
        db, tenant_id=owner, pickup="Cherry Creek, Denver, CO", dropoff="Wash Park, Denver, CO",
        scheduled_at=_denver(2026, 8, 1, 14, 0),
    )
    assert not ride.price_breakdown.get("event")
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=ride, source_id="cnon:card-nonce-ok"
    )
    assert pay.status.value == "authorized"  # hold, captured later by staff
    await db.refresh(ride)
    assert ride.paid is False


@pytest.mark.asyncio
async def test_event_cancel_full_refund(db, owner):
    await _mk_event(db, owner)
    ride = await _event_ride(db, owner)
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=ride, source_id="cnon:card-nonce-ok"
    )
    amt = pay.amount
    ride.status = RideStatus.CANCELLED
    await db.commit()
    out = await payments.settle_cancellation(db, tenant_id=owner, ride=ride, fee_pct=0)
    assert out is not None and out.status.value == "refunded"
    assert out.refunded_amount == amt


@pytest.mark.asyncio
async def test_event_cancel_half_refund(db, owner):
    await _mk_event(db, owner)
    ride = await _event_ride(db, owner)
    pay = await payments.authorize_for_ride(
        db, tenant_id=owner, ride=ride, source_id="cnon:card-nonce-ok"
    )
    amt = pay.amount
    ride.status = RideStatus.CANCELLED
    await db.commit()
    out = await payments.settle_cancellation(db, tenant_id=owner, ride=ride, fee_pct=50)
    assert out.status.value == "refunded"
    assert out.refunded_amount == amt - round(amt * 50 / 100)  # half refunded, half kept
    await db.refresh(ride)
    assert ride.paid is True  # the driver kept the cancellation fee


@pytest.mark.asyncio
async def test_non_event_round_trip_no_fees(db, owner):
    # A round trip that matches no event: just out + return, no event/night/wait lines.
    q = await booking.build_round_trip_quote(
        db, tenant_id=owner, pickup="Cherry Creek, Denver, CO",
        dropoff="Wash Park, Denver, CO",
        scheduled_at=_denver(2026, 8, 1, 14, 0),
        return_at=_denver(2026, 8, 1, 18, 0),
    )
    labels = {x["label"] for x in q["lines"]}
    assert labels == {"ride_out", "ride_return"}
    assert q["event"] is None
