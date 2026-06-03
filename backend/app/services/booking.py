"""Booking service: rate-config access, quoting (maps + pricing), and ride
persistence. All queries are tenant-scoped."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RateConfig, Ride, RideStatus
from app.models.rate_config import DEFAULT_RATES
from app.services import maps, pricing


async def get_or_create_rate_config(db: AsyncSession, *, tenant_id: int) -> RateConfig:
    rc = (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if rc is None:
        rc = RateConfig(tenant_id=tenant_id, **DEFAULT_RATES)
        db.add(rc)
        await db.commit()
        await db.refresh(rc)
    return rc


# Fields a client/dashboard may edit on the rate engine.
RATE_FIELDS = (
    "currency",
    "minimum",
    "base",
    "per_mile",
    "per_minute",
    "airport_flat",
    "extra_stop_fee",
    "group_surcharge",
    "group_threshold",
    "peak_enabled",
    "peak_multiplier",
    "loyalty_discount_pct",
)


async def update_rate_config(db: AsyncSession, *, tenant_id: int, changes: dict) -> RateConfig:
    rc = await get_or_create_rate_config(db, tenant_id=tenant_id)
    for k, v in changes.items():
        if k in RATE_FIELDS and v is not None:
            setattr(rc, k, v)
    await db.commit()
    await db.refresh(rc)
    return rc


async def build_quote(
    db: AsyncSession,
    *,
    tenant_id: int,
    pickup: str,
    dropoff: str,
    stops: list[str] | None = None,
    pax: int | None = None,
    scheduled_at: datetime | None = None,
    is_loyalty: bool = False,
    is_peak: bool | None = None,
) -> dict:
    """Compute a fare for a candidate trip without persisting it. Returns the
    route facts + the pricing breakdown."""
    rc = await get_or_create_rate_config(db, tenant_id=tenant_id)
    rr = await maps.route(pickup, dropoff, stops)
    is_airport = pricing.looks_like_airport(pickup, dropoff)
    facts = pricing.RouteFacts(
        distance_miles=rr.distance_miles,
        duration_minutes=rr.duration_minutes,
        is_airport=is_airport,
        pax=pax,
        extra_stops=len(stops) if stops else 0,
        scheduled_at=scheduled_at,
        is_peak=is_peak,
        is_loyalty=is_loyalty,
    )
    breakdown = pricing.quote(rc, facts)
    breakdown["route_simulated"] = rr.simulated
    return breakdown


async def create_ride(
    db: AsyncSession,
    *,
    tenant_id: int,
    pickup: str,
    dropoff: str,
    stops: list[str] | None = None,
    client_id: int | None = None,
    passenger_name: str | None = None,
    passenger_phone: str | None = None,
    pax: int | None = None,
    scheduled_at: datetime | None = None,
    flight_number: str | None = None,
    lang: str | None = None,
    notes: str | None = None,
    vehicle: str | None = None,
    is_loyalty: bool = False,
    is_peak: bool | None = None,
    status: RideStatus = RideStatus.QUOTED,
    fare_override: float | None = None,
) -> Ride:
    """Quote (maps + pricing) then persist the ride. `fare_override` lets the
    driver pin a negotiated fare while still snapshotting the computed route."""
    breakdown = await build_quote(
        db,
        tenant_id=tenant_id,
        pickup=pickup,
        dropoff=dropoff,
        stops=stops,
        pax=pax,
        scheduled_at=scheduled_at,
        is_loyalty=is_loyalty,
        is_peak=is_peak,
    )
    ride = Ride(
        tenant_id=tenant_id,
        client_id=client_id,
        status=status,
        pickup_text=pickup,
        dropoff_text=dropoff,
        stops=[{"text": s} for s in stops] if stops else None,
        scheduled_at=scheduled_at,
        distance_miles=breakdown["distance_miles"],
        duration_minutes=breakdown["duration_minutes"],
        fare_total=fare_override if fare_override is not None else breakdown["total"],
        currency=breakdown["currency"],
        price_breakdown=breakdown,
        pax=pax,
        vehicle=vehicle,
        flight_number=flight_number,
        lang=lang,
        notes=notes,
        passenger_name=passenger_name,
        passenger_phone=passenger_phone,
    )
    db.add(ride)
    await db.commit()
    await db.refresh(ride)
    await sync_ride_to_calendar(db, ride)
    return ride


# Statuses that should NOT appear on the calendar.
_INACTIVE = (RideStatus.CANCELLED, RideStatus.NO_SHOW, RideStatus.COMPLETED)


async def sync_ride_to_calendar(db: AsyncSession, ride: Ride) -> None:
    """Push a scheduled, active ride to Google Calendar (create or update) and
    store the event id. Best-effort — never raises (calendar must not block
    bookings)."""
    if ride.scheduled_at is None or ride.status in _INACTIVE:
        return
    try:
        from app.models import Client
        from app.services import calendar

        name = ride.passenger_name
        if ride.client_id:
            c = (
                await db.execute(select(Client).where(Client.id == ride.client_id))
            ).scalar_one_or_none()
            if c and c.name:
                name = c.name
        ev = calendar.build_ride_event(
            client_name=name,
            pickup=ride.pickup_text,
            dropoff=ride.dropoff_text,
            fare=ride.fare_total,
            flight=ride.flight_number,
            phone=ride.passenger_phone,
            notes=ride.notes,
        )
        event_id = calendar.upsert_event(
            summary=ev["summary"],
            description=ev["description"],
            location=ev["location"],
            start=ride.scheduled_at,
            duration_min=int(ride.duration_minutes or 60),
            event_id=ride.google_event_id,
        )
        if event_id and event_id != ride.google_event_id:
            ride.google_event_id = event_id
            await db.commit()
    except Exception:  # noqa: BLE001 — best-effort, never block the booking
        await db.rollback()


async def list_rides(
    db: AsyncSession, *, tenant_id: int, status: RideStatus | None = None, limit: int = 100
) -> list[Ride]:
    q = select(Ride).where(Ride.tenant_id == tenant_id)
    if status is not None:
        q = q.where(Ride.status == status)
    q = q.order_by(
        Ride.scheduled_at.is_(None), Ride.scheduled_at.asc(), Ride.id.desc()
    ).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_ride(db: AsyncSession, *, tenant_id: int, ride_id: int) -> Ride | None:
    return (
        await db.execute(
            select(Ride).where(Ride.tenant_id == tenant_id, Ride.id == ride_id)
        )
    ).scalar_one_or_none()


async def set_ride_status(
    db: AsyncSession, *, tenant_id: int, ride_id: int, status: RideStatus
) -> Ride | None:
    ride = await get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        return None
    ride.status = status
    await db.commit()
    await db.refresh(ride)
    return ride
