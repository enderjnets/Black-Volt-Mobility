"""Per-event pricing: surcharges layered on top of the base zone/metered fare, plus
round-trip suggestion (outbound + return + driver wait).

Event fees are keyed to a published :class:`Event` matched by venue + time window, so
they apply to any booking channel (event landing, direct /book, admin-created) — nobody
dodges the fee by booking elsewhere. All time-of-day logic runs in America/Denver.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.services.tenancy import owner_tenant_id
from app.services.venue_profiles import match_venue_key

_DENVER_TZ = ZoneInfo("America/Denver")
_STOP = {"the", "at", "of", "and", "amphitheatre", "amphitheater", "arena", "field",
         "stadium", "center", "theatre", "theater", "park", "mile", "high"}
# How wide around showtime a ride still counts as "for this event".
_PRE_WINDOW = dt.timedelta(hours=8)
_POST_GRACE = dt.timedelta(hours=6)


def _norm(s: str) -> str:
    return " ".join(
        "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in (s or "")).split()
    )


def _as_utc(when: dt.datetime) -> dt.datetime:
    return when if when.tzinfo else when.replace(tzinfo=dt.UTC)


def _after_cutoff(when: dt.datetime, cutoff: str) -> bool:
    """True when the leg's local (Denver) time is at or past HH:MM."""
    local = _as_utc(when).astimezone(_DENVER_TZ)
    try:
        hh, mm = (int(x) for x in cutoff.split(":"))
    except (ValueError, AttributeError):
        hh, mm = 21, 0
    return (local.hour, local.minute) >= (hh, mm)


def _venue_matches(event: Event, text: str) -> bool:
    """Does an address string refer to this event's venue?

    Watchlist venues match via the curated alias list only. Generic venues require ALL
    significant name tokens to appear as whole words (or the exact street number + name) —
    a whole-word test, not a substring test, so "Green" (Fiddler's Green) does not match
    "Greenwood Village" and wrongly attach a surcharge to an unrelated ride.
    """
    t = _norm(text)
    if not t:
        return False
    words = set(t.split())
    key = event.venue_key
    # Watchlist venues match via their distinctive curated aliases (low false-positive).
    if key and key != "generic" and match_venue_key(text or "") == key:
        return True
    # Exact street number + street name — specific and low false-positive — for ANY venue.
    # This is the primary path for event bookings, whose address is the venue's street.
    if event.venue_address:
        m = re.match(r"(\d+)\s+([a-z0-9]+)", _norm(event.venue_address))
        if m and m.group(1) in words and m.group(2) in words:
            return True
    # Generic venues also match when ALL significant name tokens appear as whole words.
    if not key or key == "generic":
        name_tokens = [w for w in _norm(event.venue_name).split() if len(w) > 3 and w not in _STOP]
        if name_tokens and all(tok in words for tok in name_tokens):
            return True
    return False


async def find_event_for_ride(
    db: AsyncSession, *, pickup: str, dropoff: str, when: dt.datetime | None
) -> Event | None:
    """Return the published owner-tenant event this ride is for, or None.

    A ride is "for" an event when its scheduled time falls in the event's window and
    either endpoint is the venue.
    """
    if when is None:
        return None
    when = _as_utc(when)
    tid = await owner_tenant_id(db)
    lo = when - _POST_GRACE  # event could have started up to est_duration+grace before `when`
    rows = (
        await db.execute(
            select(Event).where(
                Event.tenant_id == tid,
                Event.status == "published",
                Event.starts_at >= lo - dt.timedelta(hours=8),
                Event.starts_at <= when + _PRE_WINDOW,
            )
        )
    ).scalars().all()
    for ev in rows:
        starts = _as_utc(ev.starts_at)
        window_end = starts + dt.timedelta(hours=float(ev.est_duration_hours or 3)) + _POST_GRACE
        if not (starts - _PRE_WINDOW <= when <= window_end):
            continue
        if _venue_matches(ev, pickup) or _venue_matches(ev, dropoff):
            return ev
    return None


def event_fee_lines(event: Event, *, leg_dt_utc: dt.datetime) -> list[dict]:
    """Fee line-items for a single leg: the flat event fee + a night fee when the leg's
    local time is at/after the event's cutoff."""
    lines: list[dict] = []
    if event.event_fee and event.event_fee > 0:
        lines.append(
            {"label": "event_fee", "event": event.slug, "amount": round(event.event_fee, 2)}
        )
    if event.night_fee and event.night_fee > 0 and _after_cutoff(leg_dt_utc, event.night_cutoff):
        lines.append({"label": "night_fee", "amount": round(event.night_fee, 2)})
    return lines


def _venue_address(event: Event) -> str:
    return event.venue_address or event.venue_name


def default_return_dt(event: Event) -> dt.datetime:
    """When the show is expected to let out (used as the default return pickup time)."""
    return _as_utc(event.starts_at) + dt.timedelta(hours=float(event.est_duration_hours or 3))


def compose_round_trip(
    *,
    leg_out: dict,
    leg_return: dict,
    event: Event | None,
    return_dt: dt.datetime,
    uber_black: float | None = None,
) -> dict:
    """Combine two one-way leg quotes into a round-trip total: out + return fares, plus a
    single event fee, a single night fee (keyed to the late return), and a single wait fee.
    Honors an admin ``round_trip_price`` override, and caps just under Uber Black when a
    comparable estimate is supplied.
    """
    lines: list[dict] = [
        {"label": "ride_out", "amount": round(leg_out["total"], 2)},
        {"label": "ride_return", "amount": round(leg_return["total"], 2)},
    ]
    wait = 0.0
    if event is not None:
        if event.event_fee and event.event_fee > 0:
            lines.append({"label": "event_fee", "amount": round(event.event_fee, 2)})
        # Night fee is keyed to the show's expected end, NOT the customer-supplied return
        # time — otherwise a rider could pass an early `return_at` to dodge it.
        night_ref = default_return_dt(event)
        night = event.night_fee and event.night_fee > 0
        if night and _after_cutoff(night_ref, event.night_cutoff):
            lines.append({"label": "night_fee", "amount": round(event.night_fee, 2)})
        duration = float(event.est_duration_hours or 3)
        wait = round(float(event.wait_fee_per_hour or 0) * duration, 2)
        if wait > 0:
            lines.append({"label": "wait_fee", "qty": duration, "amount": wait})

    formula_total = round(sum(x["amount"] for x in lines), 2)
    out = {
        "currency": leg_out["currency"],
        "round_trip": True,
        "legs": [leg_out, leg_return],
        "lines": lines,
        "wait_fee": wait,
        "formula_total": formula_total,
        "total": formula_total,
        "overridden": False,
        "capped": False,
        "uber_black": round(uber_black, 2) if uber_black else None,
        "event": (
            {
                "slug": event.slug,
                "title": event.title,
                "starts_at": _as_utc(event.starts_at).isoformat(),
            }
            if event
            else None
        ),
        "return_at": return_dt.isoformat(),
    }
    if event is not None and event.round_trip_price is not None:
        out["total"] = round(float(event.round_trip_price), 2)
        out["overridden"] = True
        return out
    if uber_black and formula_total > 0.92 * uber_black:
        out["total"] = round(0.92 * uber_black, 2)
        out["capped"] = True
    return out


async def suggest_round_trip(
    db: AsyncSession, *, event: Event, origin: str, uber_black: float | None = None
) -> dict:
    """Round-trip suggestion for a representative ``origin`` (dashboard preview / research)."""
    from app.services import booking  # lazy: booking imports this module

    venue = _venue_address(event)
    tid = await owner_tenant_id(db)
    arrive = _as_utc(event.starts_at) - dt.timedelta(hours=1)
    depart = default_return_dt(event)
    leg_out = await booking.build_quote(
        db, tenant_id=tid, pickup=origin, dropoff=venue, scheduled_at=arrive,
        apply_event_fees=False,
    )
    leg_return = await booking.build_quote(
        db, tenant_id=tid, pickup=venue, dropoff=origin, scheduled_at=depart,
        apply_event_fees=False,
    )
    return compose_round_trip(
        leg_out=leg_out, leg_return=leg_return, event=event, return_dt=depart,
        uber_black=uber_black,
    )
