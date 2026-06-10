"""Driver dashboard read-models: KPI stats, client CRM aggregation, and
helpers to enrich rides with client + payment info. Tenant-scoped, computed on
the fly (no extra tables)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Payment, PaymentStatus, Ride, RideStatus

_CANCELLED = (RideStatus.CANCELLED, RideStatus.NO_SHOW)
_OPEN = (RideStatus.REQUESTED, RideStatus.QUOTED, RideStatus.CONFIRMED, RideStatus.ASSIGNED)


def _tier(rides_count: int, spend: float) -> str:
    if spend >= 1000 or rides_count >= 15:
        return "VIP"
    if rides_count >= 3:
        return "Regular"
    return "New"


async def stats(db: AsyncSession, *, tenant_id: int) -> dict:
    now = datetime.now(UTC)
    today = now.date()
    t = Ride.tenant_id == tenant_id

    # Attribute a ride to its service day (scheduled_at, falling back to when it
    # was created) — so "today" and the weekly chart line up with when rides
    # actually happen, not when they were marked paid.
    ride_day = func.date(func.coalesce(Ride.scheduled_at, Ride.created_at))

    rides_today = (
        await db.execute(
            select(func.count()).where(t, func.date(Ride.scheduled_at) == today)
        )
    ).scalar_one()
    # Revenue = paid rides whose service day is today (any method: cash, Square…).
    revenue_today = (
        await db.execute(
            select(func.coalesce(func.sum(Ride.fare_total), 0.0)).where(
                t, Ride.paid.is_(True), ride_day == today
            )
        )
    ).scalar_one()
    upcoming = (
        await db.execute(
            select(func.count()).where(
                t, Ride.scheduled_at > now, Ride.status.in_(_OPEN)
            )
        )
    ).scalar_one()

    total_clients = (
        await db.execute(select(func.count()).where(Client.tenant_id == tenant_id))
    ).scalar_one()
    total_rides = (await db.execute(select(func.count()).where(t))).scalar_one()
    completed = (
        await db.execute(
            select(func.count()).where(t, Ride.status == RideStatus.COMPLETED)
        )
    ).scalar_one()

    # Next pickup (with client name resolved).
    nxt_ride = (
        await db.execute(
            select(Ride)
            .where(t, Ride.scheduled_at > now, Ride.status.in_(_OPEN))
            .order_by(Ride.scheduled_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_pickup = None
    if nxt_ride is not None:
        names = await client_names(db, tenant_id=tenant_id, ids=[nxt_ride.client_id])
        nm = names.get(nxt_ride.client_id, (None, None))[0] if nxt_ride.client_id else None
        next_pickup = {
            "at": nxt_ride.scheduled_at.isoformat() if nxt_ride.scheduled_at else None,
            "client": nm or nxt_ride.passenger_name,
            "pickup": nxt_ride.pickup_text,
        }

    # Earnings per day for the current Mon→Sun week (paid rides, by service day),
    # zero-filled. Plus the week's total.
    start = today - timedelta(days=today.weekday())  # Monday of this week
    end = start + timedelta(days=6)  # Sunday
    rows = (
        await db.execute(
            select(ride_day.label("d"), func.coalesce(func.sum(Ride.fare_total), 0.0))
            .where(t, Ride.paid.is_(True), ride_day >= start, ride_day <= end)
            .group_by(ride_day)
        )
    ).all()
    earned = {str(r[0]): float(r[1]) for r in rows}
    week = []
    for i in range(7):
        d = start + timedelta(days=i)
        week.append(
            {"day": d.strftime("%a"), "date": str(d), "revenue": round(earned.get(str(d), 0.0), 2)}
        )
    week_total = round(sum(x["revenue"] for x in week), 2)

    return {
        "today": {
            "rides": rides_today,
            "revenue": round(float(revenue_today), 2),
            "upcoming": upcoming,
        },
        "next_pickup": next_pickup,
        "totals": {"clients": total_clients, "rides": total_rides, "completed": completed},
        "week": week,
        "week_total": week_total,
    }


async def client_names(
    db: AsyncSession, *, tenant_id: int, ids: list[int | None]
) -> dict[int, tuple[str | None, str | None]]:
    """Map of client_id → (name, phone) for the given ids (ignores None)."""
    real = [i for i in ids if i]
    if not real:
        return {}
    rows = (
        await db.execute(
            select(Client.id, Client.name, Client.phone).where(
                Client.tenant_id == tenant_id, Client.id.in_(real)
            )
        )
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def list_clients(db: AsyncSession, *, tenant_id: int) -> list[dict]:
    clients = (
        await db.execute(
            select(Client).where(Client.tenant_id == tenant_id).order_by(Client.id)
        )
    ).scalars().all()
    if not clients:
        return []

    # Ride aggregates per client (exclude cancelled/no-show).
    agg = (
        await db.execute(
            select(
                Ride.client_id,
                func.count().label("rides"),
                func.max(func.coalesce(Ride.scheduled_at, Ride.created_at)).label("last"),
            )
            .where(
                Ride.tenant_id == tenant_id,
                Ride.client_id.isnot(None),
                Ride.status.notin_(_CANCELLED),
            )
            .group_by(Ride.client_id)
        )
    ).all()
    rides_by = {r.client_id: (r.rides, r.last) for r in agg}

    # Lifetime spend per client = paid rides (any method), in dollars.
    spend_rows = (
        await db.execute(
            select(Ride.client_id, func.coalesce(func.sum(Ride.fare_total), 0.0))
            .where(
                Ride.tenant_id == tenant_id,
                Ride.client_id.isnot(None),
                Ride.paid.is_(True),
            )
            .group_by(Ride.client_id)
        )
    ).all()
    spend_by = {r[0]: float(r[1]) for r in spend_rows}

    # Latest ride language per client.
    lang_rows = (
        await db.execute(
            select(Ride.client_id, Ride.lang)
            .where(Ride.tenant_id == tenant_id, Ride.client_id.isnot(None), Ride.lang.isnot(None))
            .order_by(Ride.client_id, Ride.created_at.desc())
        )
    ).all()
    lang_by: dict[int, str] = {}
    for cid, lang in lang_rows:
        lang_by.setdefault(cid, lang)

    out = []
    for c in clients:
        rides_count, last = rides_by.get(c.id, (0, None))
        spend = round(spend_by.get(c.id, 0.0), 2)
        out.append(
            {
                "id": c.id,
                "name": c.name or (c.email.split("@")[0] if c.email else "Client"),
                "phone": c.phone,
                "email": c.email,
                # Preferred language: client's own setting first, else latest ride.
                "lang": (c.lang or lang_by.get(c.id) or "EN").upper(),
                "rides_count": rides_count,
                "lifetime_spend": spend,
                "tier": _tier(rides_count, spend),
                "last_ride_at": last.isoformat() if last else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        )
    # Most valuable first.
    out.sort(key=lambda x: (x["lifetime_spend"], x["rides_count"]), reverse=True)
    return out


def _ride_brief(r: Ride) -> dict:
    """Compact ride row for a client's history list."""
    return {
        "id": r.id,
        "status": r.status.value if isinstance(r.status, RideStatus) else r.status,
        "pickup": r.pickup_text,
        "dropoff": r.dropoff_text,
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
        "fare_total": r.fare_total,
        "flight_number": r.flight_number,
        "paid": r.paid,
    }


async def client_detail(db: AsyncSession, *, tenant_id: int, client_id: int) -> dict | None:
    """Full client profile + stats + their ride history. Tenant-scoped (a client
    of another tenant returns None — no cross-tenant leakage)."""
    c = (
        await db.execute(
            select(Client).where(Client.tenant_id == tenant_id, Client.id == client_id)
        )
    ).scalar_one_or_none()
    if c is None:
        return None
    rides = list(
        (
            await db.execute(
                select(Ride)
                .where(Ride.tenant_id == tenant_id, Ride.client_id == client_id)
                .order_by(Ride.scheduled_at.is_(None), Ride.scheduled_at.desc(), Ride.id.desc())
            )
        )
        .scalars()
        .all()
    )
    active = [r for r in rides if r.status not in _CANCELLED]
    rides_count = len(active)
    spend = round(sum((r.fare_total or 0.0) for r in rides if r.paid), 2)
    last = max((r.scheduled_at or r.created_at for r in active), default=None)
    latest_lang = next(
        (r.lang for r in sorted(rides, key=lambda r: r.created_at, reverse=True) if r.lang),
        None,
    )
    return {
        "id": c.id,
        "name": c.name or (c.email.split("@")[0] if c.email else "Client"),
        "phone": c.phone,
        "email": c.email,
        "lang": (c.lang or latest_lang or "EN").upper(),
        "home_address": c.home_address,
        "rides_count": rides_count,
        "lifetime_spend": spend,
        "tier": _tier(rides_count, spend),
        "last_ride_at": last.isoformat() if last else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "rides": [_ride_brief(r) for r in rides],
    }


_CLIENT_EDITABLE = ("name", "phone", "email", "lang", "home_address")


async def update_client(
    db: AsyncSession, *, tenant_id: int, client_id: int, changes: dict
) -> Client | None:
    """Update a client's editable profile fields. Tenant-scoped."""
    c = (
        await db.execute(
            select(Client).where(Client.tenant_id == tenant_id, Client.id == client_id)
        )
    ).scalar_one_or_none()
    if c is None:
        return None
    for k in _CLIENT_EDITABLE:
        if k in changes and changes[k] is not None:
            setattr(c, k, changes[k] or None)
    await db.commit()
    await db.refresh(c)
    return c


async def search_clients(
    db: AsyncSession, *, tenant_id: int, q: str, limit: int = 8
) -> list[dict]:
    """Compact client matches for the Add-ride name autocomplete. Matches name,
    phone, or email (case-insensitive), most-active first. Tenant-scoped."""
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    clients = (
        await db.execute(
            select(Client)
            .where(
                Client.tenant_id == tenant_id,
                or_(
                    Client.name.ilike(like),
                    Client.phone.ilike(like),
                    Client.email.ilike(like),
                ),
            )
            # Cap the candidate set on the hot (per-keystroke) path; we only need
            # the top `limit` by ride count, not every ILIKE match for a 2-char q.
            .limit(50)
        )
    ).scalars().all()
    if not clients:
        return []
    ids = [c.id for c in clients]
    agg = (
        await db.execute(
            select(Ride.client_id, func.count())
            .where(
                Ride.tenant_id == tenant_id,
                Ride.client_id.in_(ids),
                Ride.status.notin_(_CANCELLED),
            )
            .group_by(Ride.client_id)
        )
    ).all()
    rides_by = {r[0]: r[1] for r in agg}
    clients.sort(key=lambda c: rides_by.get(c.id, 0), reverse=True)
    return [
        {
            "id": c.id,
            "name": c.name or (c.email.split("@")[0] if c.email else "Client"),
            "phone": c.phone,
            "lang": (c.lang or "EN").upper(),
        }
        for c in clients[:limit]
    ]


async def create_client(
    db: AsyncSession,
    *,
    tenant_id: int,
    name: str,
    phone: str | None = None,
    email: str | None = None,
    lang: str | None = None,
    home_address: str | None = None,
) -> Client:
    """Create a client by hand from the Clients page (staff). Tenant-scoped."""
    c = Client(
        tenant_id=tenant_id,
        name=name.strip(),
        phone=(phone or "").strip() or None,
        email=(email or "").strip() or None,
        lang=lang or None,
        home_address=(home_address or "").strip() or None,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def delete_client(db: AsyncSession, *, tenant_id: int, client_id: int) -> bool:
    """Delete a client while preserving ride history: backfill the passenger
    name/phone snapshot onto each ride that lacks it, detach client_id (the FK is
    ON DELETE SET NULL, but we backfill first so the name survives), then remove
    the client. Returns False if the client doesn't exist. Tenant-scoped."""
    c = (
        await db.execute(
            select(Client).where(Client.tenant_id == tenant_id, Client.id == client_id)
        )
    ).scalar_one_or_none()
    if c is None:
        return False
    rides = (
        await db.execute(
            select(Ride).where(Ride.tenant_id == tenant_id, Ride.client_id == client_id)
        )
    ).scalars().all()
    for r in rides:
        if not r.passenger_name and c.name:
            r.passenger_name = c.name
        if not r.passenger_phone and c.phone:
            r.passenger_phone = c.phone
        r.client_id = None
    await db.delete(c)
    await db.commit()
    return True


async def latest_payment(db: AsyncSession, *, tenant_id: int, ride_id: int) -> Payment | None:
    return (
        await db.execute(
            select(Payment)
            .where(Payment.tenant_id == tenant_id, Payment.ride_id == ride_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def ride_detail_extra(db: AsyncSession, *, tenant_id: int, ride: Ride) -> dict:
    """Client + latest payment info to enrich a single ride's detail view."""
    client = None
    if ride.client_id:
        c = (
            await db.execute(select(Client).where(Client.id == ride.client_id))
        ).scalar_one_or_none()
        if c:
            client = {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email}
    pay = await latest_payment(db, tenant_id=tenant_id, ride_id=ride.id)
    payment = (
        {
            "id": pay.id,
            "status": pay.status.value if isinstance(pay.status, PaymentStatus) else pay.status,
            "amount": pay.amount,
            "currency": pay.currency,
            "simulated": pay.simulated,
        }
        if pay
        else None
    )
    return {"client": client, "payment": payment}


async def team_stats_by_tenant(db: AsyncSession) -> dict[int, dict]:
    """Per-tenant ride count, paid revenue, and last activity for the Team panel
    — one row per driver (each driver owns one tenant). Keyed by tenant_id.
    Rides exclude cancelled/no-show; revenue counts paid rides (any method)."""
    agg = (
        await db.execute(
            select(
                Ride.tenant_id,
                func.count().label("rides"),
                func.max(func.coalesce(Ride.scheduled_at, Ride.created_at)).label("last"),
            )
            .where(Ride.tenant_id.isnot(None), Ride.status.notin_(_CANCELLED))
            .group_by(Ride.tenant_id)
        )
    ).all()
    rev_rows = (
        await db.execute(
            select(Ride.tenant_id, func.coalesce(func.sum(Ride.fare_total), 0.0))
            .where(Ride.tenant_id.isnot(None), Ride.paid.is_(True))
            .group_by(Ride.tenant_id)
        )
    ).all()
    rev_by = {r[0]: round(float(r[1]), 2) for r in rev_rows}

    out: dict[int, dict] = {}
    for r in agg:
        out[r.tenant_id] = {
            "rides": int(r.rides),
            "revenue": rev_by.get(r.tenant_id, 0.0),
            "last_activity": r.last.isoformat() if r.last else None,
        }
    for tid, amt in rev_by.items():  # paid-but-all-cancelled tenants still show revenue
        out.setdefault(tid, {"rides": 0, "revenue": amt, "last_activity": None})
    return out
