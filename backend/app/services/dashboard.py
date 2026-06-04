"""Driver dashboard read-models: KPI stats, client CRM aggregation, and
helpers to enrich rides with client + payment info. Tenant-scoped, computed on
the fly (no extra tables)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
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

    rides_today = (
        await db.execute(
            select(func.count()).where(t, func.date(Ride.scheduled_at) == today)
        )
    ).scalar_one()
    # Revenue = paid rides today (any method: cash, Square, Venmo, Zelle…).
    revenue_today = (
        await db.execute(
            select(func.coalesce(func.sum(Ride.fare_total), 0.0)).where(
                t, Ride.paid.is_(True), func.date(Ride.paid_at) == today
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

    # Rides per day, last 7 days (by scheduled_at or created_at), zero-filled.
    start = today - timedelta(days=6)
    day_col = func.date(func.coalesce(Ride.scheduled_at, Ride.created_at))
    rows = (
        await db.execute(
            select(day_col.label("d"), func.count())
            .where(t, day_col >= start)
            .group_by(day_col)
        )
    ).all()
    counts = {str(r[0]): r[1] for r in rows}
    week = []
    for i in range(7):
        d = start + timedelta(days=i)
        week.append({"day": d.strftime("%a"), "date": str(d), "rides": counts.get(str(d), 0)})

    return {
        "today": {
            "rides": rides_today,
            "revenue": round(float(revenue_today), 2),
            "upcoming": upcoming,
        },
        "next_pickup": next_pickup,
        "totals": {"clients": total_clients, "rides": total_rides, "completed": completed},
        "week": week,
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
                "lang": (lang_by.get(c.id) or "EN").upper(),
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
