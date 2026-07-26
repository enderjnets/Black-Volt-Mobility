"""Driver dashboard read-models: KPI stats, client CRM aggregation, and
helpers to enrich rides with client + payment info. Tenant-scoped, computed on
the fly (no extra tables)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    AllowedUser,
    Client,
    Payment,
    PaymentStatus,
    Ride,
    RideStatus,
    Subscription,
    SubscriptionStatus,
    Tenant,
)
from app.services import analytics, booking
from app.services import profile as profile_svc

_CANCELLED = (RideStatus.CANCELLED, RideStatus.NO_SHOW)
_OPEN = (RideStatus.REQUESTED, RideStatus.QUOTED, RideStatus.CONFIRMED, RideStatus.ASSIGNED)


def _tier(rides_count: int, spend: float) -> str:
    if spend >= 1000 or rides_count >= 15:
        return "VIP"
    if rides_count >= 3:
        return "Regular"
    return "New"


def monday_of(d: date) -> date:
    """The Monday of the week containing `d`."""
    return d - timedelta(days=d.weekday())


def service_tz() -> str:
    """IANA zone the driver actually works in. Every KPI buckets by this, never UTC:
    Denver is UTC-6/-7, so a 19:45 pickup is 01:45 UTC the NEXT day and would land on
    tomorrow's numbers."""
    return get_settings().CALENDAR_TIMEZONE or "UTC"


def service_day():
    """SQL expression for the day a ride belongs to, in the driver's local time.

    `timezone(tz, <timestamptz>)` converts to local wall-clock, then `date()` cuts the
    day there. Falls back to created_at for ad-hoc rides with no schedule. This is THE
    definition of a service day — stats, the week chart and the week history all use it
    so they can never disagree with each other again.
    """
    local = func.timezone(service_tz(), func.coalesce(Ride.scheduled_at, Ride.created_at))
    return func.date(local)


def today_local() -> date:
    """Today on the driver's clock (not the server's UTC clock)."""
    from zoneinfo import ZoneInfo

    try:
        return datetime.now(ZoneInfo(service_tz())).date()
    except Exception:  # bad tz name → never break the dashboard
        return datetime.now(UTC).date()


async def week_earnings(db: AsyncSession, *, tenant_id: int, monday: date) -> dict:
    """Daily earned revenue Mon→Sun for the week starting at `monday`
    (zero-filled), plus the week total and ISO date range. Tenant-scoped; uses
    the same earned/service-day definition as the dashboard KPIs so a navigable
    past week matches the "This week" card exactly."""
    ride_day = service_day()
    start = monday
    end = start + timedelta(days=6)
    rows = (
        await db.execute(
            select(ride_day.label("d"), func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0))
            .where(
                Ride.tenant_id == tenant_id,
                booking.earned_ride_filter(),
                ride_day >= start,
                ride_day <= end,
            )
            .group_by(ride_day)
        )
    ).all()
    by_day = {str(r[0]): float(r[1]) for r in rows}
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append(
            {
                "day": d.strftime("%a"),
                "date": str(d),
                "revenue": round(by_day.get(str(d), 0.0), 2),
            }
        )
    total = round(sum(x["revenue"] for x in days), 2)
    return {"start": str(start), "end": str(end), "total": total, "days": days}


async def weeks_summary(db: AsyncSession, *, tenant_id: int, count: int = 12) -> list[dict]:
    """Earned-revenue totals for the last `count` Mon→Sun weeks (offset 0 = current,
    negative = past), zero-filled — one query, bucketed by week. Powers the totals
    shown in the dashboard week-picker dropdown. Same earned/service-day definition
    as `week_earnings`, so each total matches that week's chart."""
    count = max(1, min(int(count), 52))
    today = today_local()
    cur_monday = monday_of(today)
    oldest_monday = cur_monday - timedelta(weeks=count - 1)
    ride_day = service_day()
    rows = (
        await db.execute(
            select(ride_day.label("d"), func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0))
            .where(
                Ride.tenant_id == tenant_id,
                booking.earned_ride_filter(),
                ride_day >= oldest_monday,
                ride_day <= cur_monday + timedelta(days=6),
            )
            .group_by(ride_day)
        )
    ).all()
    # Bucket each earning day into its week (by Monday).
    by_week: dict[date, float] = {}
    for d_str, amount in rows:
        d = d_str if isinstance(d_str, date) else date.fromisoformat(str(d_str))
        by_week[monday_of(d)] = by_week.get(monday_of(d), 0.0) + float(amount)
    out = []
    for i in range(count):
        m = cur_monday - timedelta(weeks=i)  # offset = -i
        out.append(
            {
                "offset": -i,
                "start": str(m),
                "end": str(m + timedelta(days=6)),
                "total": round(by_week.get(m, 0.0), 2),
            }
        )
    return out


async def stats(db: AsyncSession, *, tenant_id: int) -> dict:
    now = datetime.now(UTC)
    today = today_local()
    t = Ride.tenant_id == tenant_id

    # Attribute a ride to its service day (scheduled_at, falling back to when it
    # was created) IN THE DRIVER'S TIMEZONE — so "today" and the weekly chart line up
    # with when rides actually happen, not when they were marked paid, and an evening
    # pickup doesn't jump to tomorrow because UTC already rolled over.
    ride_day = service_day()

    # A ride "counts" as revenue once it actually happened and earned money:
    # completed OR settled, never cancelled/no-show (shared definition so the
    # dashboard and the My Stats funnel agree on what "revenue" means).
    earned = booking.earned_ride_filter()

    # Rides today = every non-cancelled ride on today's service day (incl. ad-hoc
    # rides that have no scheduled_at, via the coalesce day).
    rides_today = (
        await db.execute(
            select(func.count()).where(
                t, Ride.status.not_in(_CANCELLED), ride_day == today
            )
        )
    ).scalar_one()
    # Revenue = earned rides (completed or paid) whose service day is today.
    revenue_today = (
        await db.execute(
            select(func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0)).where(
                t, earned, ride_day == today
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

    # Earnings per day for the current Mon→Sun week (earned rides, by service
    # day), zero-filled. Plus the week's total. Shared with /dashboard/week so a
    # navigable past week renders identically to "This week".
    wk = await week_earnings(db, tenant_id=tenant_id, monday=monday_of(today))
    week = wk["days"]
    week_total = wk["total"]

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


async def assigned_drivers(db: AsyncSession, *, ids: list[int | None]) -> dict[int, dict]:
    """Map of assigned_tenant_id → driver contact card (name, phone, vehicle,
    rating). Drivers are top-level tenants, so this is not tenant-scoped. The
    phone is included because callers only attach this to a ride the viewer owns
    or manages (a signed-in passenger seeing their own ride, or staff)."""
    real = [i for i in ids if i]
    if not real:
        return {}
    rows = (
        await db.execute(
            select(
                Tenant.id, Tenant.name, Tenant.phone, Tenant.vehicle, Tenant.rating
            ).where(Tenant.id.in_(real))
        )
    ).all()
    return {
        r[0]: {"name": r[1], "phone": r[2], "vehicle": r[3], "rating": r[4]} for r in rows
    }


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
            select(Ride.client_id, func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0))
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
    spend = round(sum((r.fare_total or 0.0) + (r.tip or 0.0) for r in rides if r.paid), 2)
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
            await db.execute(
                select(Client).where(
                    Client.id == ride.client_id,
                    Client.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if c:
            client = {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                # Standing ride preferences (normalized) so the driver sees them inline.
                "preferences": profile_svc.normalize_ride_preferences(c.ride_preferences),
            }
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
            select(Ride.tenant_id, func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0))
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


async def _subscription_brief(db: AsyncSession, *, tenant_id: int) -> dict | None:
    """Latest non-canceled subscription for the tenant, with the entitlement
    `paid` flag (in production, simulated rows never count as paid)."""
    row = (
        await db.execute(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status != SubscriptionStatus.CANCELED,
            )
            .order_by(Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    paid = row.status == SubscriptionStatus.ACTIVE and (
        not get_settings().is_production or not row.simulated
    )
    return {
        "plan_key": row.plan_key,
        "status": row.status.value if isinstance(row.status, SubscriptionStatus) else row.status,
        "current_period_end": (
            row.current_period_end.isoformat() if row.current_period_end else None
        ),
        "simulated": row.simulated,
        "paid": paid,
    }


async def team_member_detail(
    db: AsyncSession, *, email: str, pinned: set[str]
) -> dict | None:
    """Everything the super-admin should see about one team member (driver):
    identity/access, subscription, business KPIs, 30-day platform engagement,
    recent rides and recent activity. Tenant-scoped. Returns None if the email
    isn't on the access list. A member who's never signed in has no tenant yet
    (`provisioned=False`) and gets empty stats blocks."""
    email = (email or "").lower().strip()
    u = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if u is None:
        return None

    out: dict = {
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "active": u.active,
        "immutable": u.email in pinned,
        "provisioned": u.tenant_id is not None,
        "added_by": u.added_by,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "tenant_slug": None,
        "tenant_name": None,
        "tenant_created_at": None,
        "subscription": None,
        "rides": {"total": 0, "completed": 0, "upcoming": 0, "cancelled": 0},
        "revenue_total": 0.0,
        "clients": 0,
        "first_ride_at": None,
        "last_ride_at": None,
        "week": [],
        "week_total": 0.0,
        "engagement": None,
        "recent_rides": [],
        "recent_activity": [],
    }
    if u.tenant_id is None:
        return out
    tid = u.tenant_id

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tid))
    ).scalar_one_or_none()
    if tenant is not None:
        out["tenant_slug"] = tenant.slug
        out["tenant_name"] = tenant.name
        out["tenant_created_at"] = (
            tenant.created_at.isoformat() if tenant.created_at else None
        )

    # Business — reuse stats() for the week chart + totals (clients/rides/completed),
    # then a few aggregates it doesn't expose (all-time revenue, upcoming/cancelled
    # counts, first/last ride).
    s = await stats(db, tenant_id=tid)
    out["week"] = s["week"]
    out["week_total"] = s["week_total"]
    out["clients"] = s["totals"]["clients"]

    t = Ride.tenant_id == tid
    upcoming = (
        await db.execute(select(func.count()).where(t, Ride.status.in_(_OPEN)))
    ).scalar_one()
    cancelled = (
        await db.execute(select(func.count()).where(t, Ride.status.in_(_CANCELLED)))
    ).scalar_one()
    out["rides"] = {
        "total": int(s["totals"]["rides"]),
        "completed": int(s["totals"]["completed"]),
        "upcoming": int(upcoming),
        "cancelled": int(cancelled),
    }

    revenue_total = (
        await db.execute(
            select(func.coalesce(func.sum(Ride.fare_total + func.coalesce(Ride.tip, 0.0)), 0.0)).where(t, Ride.paid.is_(True))
        )
    ).scalar_one()
    out["revenue_total"] = round(float(revenue_total), 2)

    ride_day = func.coalesce(Ride.scheduled_at, Ride.created_at)
    first_last = (
        await db.execute(
            select(func.min(ride_day), func.max(ride_day)).where(
                t, Ride.status.notin_(_CANCELLED)
            )
        )
    ).first()
    if first_last is not None:
        out["first_ride_at"] = first_last[0].isoformat() if first_last[0] else None
        out["last_ride_at"] = first_last[1].isoformat() if first_last[1] else None

    recent = (
        (
            await db.execute(
                select(Ride)
                .where(t)
                .order_by(
                    Ride.scheduled_at.is_(None), Ride.scheduled_at.desc(), Ride.id.desc()
                )
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    out["recent_rides"] = [_ride_brief(r) for r in recent]

    out["subscription"] = await _subscription_brief(db, tenant_id=tid)

    # Platform engagement (last 30 days) — reuse the Insights aggregator.
    summ = await analytics.summary(db, tenant_id=tid, days=30)
    out["engagement"] = {
        "visitors": summ["totals"]["visitors"],
        "sessions": summ["totals"]["sessions"],
        "pageviews": summ["totals"]["pageviews"],
        "avg_session_ms": summ["totals"]["avg_session_ms"],
        "funnel": summ["funnel"],
        "devices": summ["devices"],
        "countries": summ["countries"],
    }
    out["recent_activity"] = summ["recent"]
    return out
