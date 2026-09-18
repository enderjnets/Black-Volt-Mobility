"""The driver's own flights, ordered by the hour that actually constrains him.

Phase A answers everything that can be known without asking anyone: which airline, which
number, whether the passenger is landing or leaving, and what time he has to be there.
There is no live flight status yet — ``live`` is null and ``live_source`` says ``none``
rather than the screen implying otherwise.

What this deliberately does not do is guess. Eight of the flight numbers in this database
are bare digits, and there is a 976 at every carrier; a row with no airline is reported as
such so the screen can ask once and fix the ride.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ride
from app.models.ride import OPEN_STATUSES
from app.services import flight_code as fc

# The word-boundary airport test, not pricing.looks_like_airport: that one is a raw
# substring match whose "den" keyword hits Garden, Golden and Hidden. Imported rather
# than copied so the two screens can never disagree about what counts as the airport.
from app.services.booking import _airportish
from app.services.dashboard import client_names

# How far ahead the screen looks. Measured, not guessed: at 72 h the owner's live data
# showed ONE of his four booked flights, because he takes bookings a week out. Two weeks
# covers them with room. This is only how far the LIST reaches — Phase B will fetch live
# status for a much shorter horizon, since that is what costs money.
WINDOW_HOURS = 14 * 24


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def upcoming(
    db: AsyncSession,
    *,
    tenant_id: int,
    hours: int = WINDOW_HOURS,
    now: datetime | None = None,
) -> dict:
    """Payload for the Flights screen: one entry per upcoming ride that has a flight."""
    now = now or datetime.now(UTC)
    until = now + timedelta(hours=hours)

    rides = (
        (
            await db.execute(
                select(Ride)
                .where(
                    or_(Ride.tenant_id == tenant_id, Ride.assigned_tenant_id == tenant_id),
                    Ride.status.in_(OPEN_STATUSES),
                    Ride.flight_number.is_not(None),
                    Ride.flight_number != "",
                )
                .order_by(Ride.scheduled_at.asc(), Ride.id.asc())
            )
        )
        .scalars()
        .all()
    )

    names = await client_names(db, tenant_id=tenant_id, ids=[r.client_id for r in rides])

    out: list[dict] = []
    no_time = 0
    not_airport = 0
    unreadable = 0

    for r in rides:
        designator = fc.parse_designator(r.flight_number)
        if designator is None:
            # An airline with no number ("United"). It is a note on the ride, not a
            # flight, and smart.py already refuses to store it in this field.
            unreadable += 1
            continue

        way = fc.direction(
            pickup_airport=_airportish(r.pickup_text),
            dropoff_airport=_airportish(r.dropoff_text),
        )
        if way is None:
            not_airport += 1
            continue

        if r.scheduled_at is None:
            # Nothing to order it by. Counted rather than dropped in silence: a booked
            # flight with no time is a data problem he would want to see.
            no_time += 1
            continue
        if not (now <= r.scheduled_at <= until):
            continue

        name = names.get(r.client_id, (None, None))[0] if r.client_id else None
        # Only meaningful when he is delivering someone to the airport: pickup plus the
        # ride's own duration is when the passenger reaches the terminal. It is NOT a
        # "leave home at" time — the ride's duration is the trip itself, and nothing here
        # knows where the car is beforehand.
        eta = (
            r.scheduled_at + timedelta(minutes=r.duration_minutes)
            if way == fc.DEPARTURE and r.duration_minutes is not None
            else None
        )

        out.append(
            {
                "ride_id": r.id,
                "code": designator.code,
                "carrier": designator.carrier,
                "airline": designator.airline,
                "number": designator.number,
                "needs_airline": designator.needs_airline,
                "raw": r.flight_number,
                "direction": way,
                "client": name or r.passenger_name,
                "pickup": r.pickup_text,
                "dropoff": r.dropoff_text,
                "scheduled_at": _iso(r.scheduled_at),
                "airport_eta": _iso(eta),
                "distance_miles": r.distance_miles,
                "duration_minutes": r.duration_minutes,
                "status": getattr(r.status, "value", r.status),
                # Phase A orders by the ride's own hour, the only one it knows. Phase B
                # replaces this with the flight's — landing for a pickup, take-off for a
                # drop-off — which is not the same instant and can reorder the list.
                "sort_at": _iso(r.scheduled_at),
                "live": None,
            }
        )

    out.sort(key=lambda f: (f["sort_at"] or "", f["ride_id"]))

    return {
        "generated_at": _iso(now),
        "window_hours": hours,
        # "none" is a promise, not a placeholder: with no provider configured the screen
        # shows what it knows and says the rest is unknown, never a plausible-looking time.
        "live_source": "none",
        "flights": out,
        "missing_airline": sum(1 for f in out if f["needs_airline"]),
        "skipped": {
            "no_scheduled_time": no_time,
            "not_an_airport_ride": not_airport,
            "unreadable": unreadable,
        },
    }
