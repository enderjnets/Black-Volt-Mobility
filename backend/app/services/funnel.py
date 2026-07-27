"""Driver sales-funnel read/write models for the "My Stats" tab.

The *top* of the funnel (conversations/pitches/contacts) is logged by hand, one
row per day. The *bottom* (clients won, revenue) is derived from real Client/Ride
data. `summary()` stitches both together with the smoothed math in
`funnel_math.py` to produce funnel rates, a streak, weekly progress vs goal, and
a forward projection. `project()` powers the interactive goal calculator.

Everything is tenant-scoped.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, DriverFunnelLog, DriverGoal, Ride
from app.services import dashboard as dashboard_svc
from app.services import funnel_math as fm
from app.services.booking import earned_ride_filter

# Calendar constants for translating a weekly goal to month/year.
_WEEKS = {"week": 1.0, "month": 4.345, "year": 52.143}


# ── Logs (daily quick-entry) ──────────────────────────────────────────────────
async def _get_log(db: AsyncSession, tenant_id: int, log_date: date) -> DriverFunnelLog | None:
    return (
        await db.execute(
            select(DriverFunnelLog).where(
                DriverFunnelLog.tenant_id == tenant_id,
                DriverFunnelLog.log_date == log_date,
            )
        )
    ).scalar_one_or_none()


async def upsert_log(
    db: AsyncSession,
    *,
    tenant_id: int,
    log_date: date,
    conversations: int,
    pitches: int,
    contacts: int,
    notes: str | None = None,
) -> DriverFunnelLog:
    """Create or overwrite the funnel counts for a given day. Counts are clamped
    to be non-negative and monotonic down the funnel (you can't pitch more people
    than you talked to, or get more contacts than pitches)."""
    conversations = max(0, int(conversations))
    pitches = max(0, min(int(pitches), conversations))
    contacts = max(0, min(int(contacts), pitches))

    row = await _get_log(db, tenant_id, log_date)
    if row is None:
        row = DriverFunnelLog(tenant_id=tenant_id, log_date=log_date)
        db.add(row)
    row.conversations = conversations
    row.pitches = pitches
    row.contacts = contacts
    row.notes = (notes or None) if notes is not None else row.notes
    await db.commit()
    await db.refresh(row)
    return row


def _log_out(row: DriverFunnelLog) -> dict:
    return {
        "date": str(row.log_date),
        "conversations": row.conversations,
        "pitches": row.pitches,
        "contacts": row.contacts,
        "notes": row.notes,
    }


# ── Goal ──────────────────────────────────────────────────────────────────────
async def get_goal(db: AsyncSession, *, tenant_id: int) -> dict:
    row = (
        await db.execute(select(DriverGoal).where(DriverGoal.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:
        return {
            "target_weekly_revenue": None,
            "target_monthly_clients": None,
            "working_days_per_week": 5,
            "currency": "USD",
        }
    return {
        "target_weekly_revenue": row.target_weekly_revenue,
        "target_monthly_clients": row.target_monthly_clients,
        "working_days_per_week": row.working_days_per_week,
        "currency": row.currency,
    }


async def set_goal(
    db: AsyncSession,
    *,
    tenant_id: int,
    target_weekly_revenue: float | None,
    target_monthly_clients: int | None,
    working_days_per_week: int,
) -> dict:
    row = (
        await db.execute(select(DriverGoal).where(DriverGoal.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:
        row = DriverGoal(tenant_id=tenant_id)
        db.add(row)
    row.target_weekly_revenue = (
        max(0.0, target_weekly_revenue) if target_weekly_revenue is not None else None
    )
    row.target_monthly_clients = (
        max(0, int(target_monthly_clients)) if target_monthly_clients is not None else None
    )
    row.working_days_per_week = max(1, min(7, int(working_days_per_week)))
    await db.commit()
    await db.refresh(row)
    return await get_goal(db, tenant_id=tenant_id)


# ── Derived metrics ───────────────────────────────────────────────────────────
async def _earned_revenue_between(
    db: AsyncSession, *, tenant_id: int, start: date, end: date
) -> float:
    # Same local service-day definition as the dashboard, so My Stats and the KPIs
    # can never report a different day for the same ride.
    ride_day = dashboard_svc.service_day()
    return float(
        (
            await db.execute(
                select(dashboard_svc.revenue_sum()).where(
                    Ride.tenant_id == tenant_id,
                    earned_ride_filter(),
                    ride_day >= start,
                    ride_day <= end,
                )
            )
        ).scalar_one()
    )


async def _clients_between(
    db: AsyncSession, *, tenant_id: int, start: date, end: date
) -> int:
    cdate = func.date(Client.created_at)
    return int(
        (
            await db.execute(
                select(func.count()).where(
                    Client.tenant_id == tenant_id, cdate >= start, cdate <= end
                )
            )
        ).scalar_one()
    )


async def _value_per_client(db: AsyncSession, *, tenant_id: int) -> tuple[float | None, float]:
    """All-time average earned revenue per client (what one new client is worth),
    plus the average earned fare as a fallback when there's no client-linked
    history yet. Returns (value_per_client | None, avg_fare)."""
    total, n_clients = (
        await db.execute(
            select(
                dashboard_svc.revenue_sum(),
                func.count(func.distinct(Ride.client_id)),
            ).where(
                Ride.tenant_id == tenant_id,
                earned_ride_filter(),
                Ride.client_id.is_not(None),
            )
        )
    ).one()
    # avg_fare (a.k.a. value_per_client) measures pricing, not take-home earnings, so
    # it stays fare-only — tips would inflate it and distort quote/coaching targets.
    avg_fare = float(
        (
            await db.execute(
                select(func.coalesce(func.avg(Ride.fare_total), 0.0)).where(
                    Ride.tenant_id == tenant_id, earned_ride_filter()
                )
            )
        ).scalar_one()
    )
    if n_clients and float(total) > 0:
        return float(total) / int(n_clients), avg_fare
    # No client-linked earnings yet — fall back to average fare so the calculator
    # still gives a usable number (flagged low-data by the caller).
    return (avg_fare or None), avg_fare


async def _streak(db: AsyncSession, *, tenant_id: int, today: date) -> int:
    """Consecutive days (ending today or yesterday) with a logged entry."""
    rows = (
        await db.execute(
            select(DriverFunnelLog.log_date)
            .where(
                DriverFunnelLog.tenant_id == tenant_id,
                DriverFunnelLog.log_date >= today - timedelta(days=400),
            )
            .order_by(DriverFunnelLog.log_date.desc())
        )
    ).scalars().all()
    have = set(rows)
    # Allow the streak to "hold" if today isn't logged yet but yesterday was.
    cursor = today if today in have else today - timedelta(days=1)
    streak = 0
    while cursor in have:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ── Summary (the whole tab in one payload) ────────────────────────────────────
async def summary(db: AsyncSession, *, tenant_id: int, days: int = 30) -> dict:
    days = max(1, min(int(days), 365))
    now = datetime.now(UTC)
    today = now.date()
    start = today - timedelta(days=days - 1)

    logs = (
        await db.execute(
            select(DriverFunnelLog)
            .where(
                DriverFunnelLog.tenant_id == tenant_id,
                DriverFunnelLog.log_date >= start,
                DriverFunnelLog.log_date <= today,
            )
            .order_by(DriverFunnelLog.log_date.asc())
        )
    ).scalars().all()

    conv = sum(x.conversations for x in logs)
    pit = sum(x.pitches for x in logs)
    con = sum(x.contacts for x in logs)
    logged_days = len(logs)

    clients_won = await _clients_between(db, tenant_id=tenant_id, start=start, end=today)
    revenue_window = await _earned_revenue_between(db, tenant_id=tenant_id, start=start, end=today)
    value_per_client, avg_fare = await _value_per_client(db, tenant_id=tenant_id)

    rates = fm.funnel_rates(conversations=conv, pitches=pit, contacts=con, clients=clients_won)

    # Per-day timeseries (logged conversations + earned revenue), zero-filled.
    rev_rows = (
        await db.execute(
            select(
                dashboard_svc.service_day().label("d"),
                dashboard_svc.revenue_sum(),
            )
            .where(
                Ride.tenant_id == tenant_id,
                earned_ride_filter(),
                func.date(func.coalesce(Ride.scheduled_at, Ride.created_at)) >= start,
                func.date(func.coalesce(Ride.scheduled_at, Ride.created_at)) <= today,
            )
            .group_by("d")
        )
    ).all()
    rev_by_day = {str(r[0]): float(r[1]) for r in rev_rows}
    conv_by_day = {str(x.log_date): x.conversations for x in logs}
    timeseries = []
    for i in range(days):
        d = start + timedelta(days=i)
        timeseries.append(
            {
                "date": str(d),
                "day": d.strftime("%a"),
                "conversations": conv_by_day.get(str(d), 0),
                "revenue": round(rev_by_day.get(str(d), 0.0), 2),
            }
        )

    streak = await _streak(db, tenant_id=tenant_id, today=today)
    today_row = next((x for x in logs if x.log_date == today), None)

    # This-week progress (Mon→today) vs goal.
    week_start = today - timedelta(days=today.weekday())
    week_conv = sum(x.conversations for x in logs if x.log_date >= week_start)
    week_clients = await _clients_between(db, tenant_id=tenant_id, start=week_start, end=today)
    week_revenue = await _earned_revenue_between(
        db, tenant_id=tenant_id, start=week_start, end=today
    )
    goal = await get_goal(db, tenant_id=tenant_id)

    # Forward projection at the driver's recent pace.
    pace = (conv / logged_days) if logged_days else 0.0
    wd = goal["working_days_per_week"]
    proj_week = fm.project(
        rates=rates,
        conversations_per_day=pace,
        working_days=wd,
        revenue_per_client=value_per_client or 0.0,
    )
    proj_month = fm.project(
        rates=rates,
        conversations_per_day=pace,
        working_days=wd * _WEEKS["month"],
        revenue_per_client=value_per_client or 0.0,
    )

    return {
        "days": days,
        "today": str(today),
        "totals": {
            "conversations": conv,
            "pitches": pit,
            "contacts": con,
            "clients": clients_won,
            "revenue": round(revenue_window, 2),
            "logged_days": logged_days,
        },
        "rates": {
            "pitch": rates.pitch.dict(),
            "contact": rates.contact.dict(),
            "convert": rates.convert.dict(),
            "overall_point": rates.overall_point,
            "overall_low": rates.overall_low,
            "overall_high": rates.overall_high,
        },
        "value_per_client": round(value_per_client, 2) if value_per_client else None,
        "avg_fare": round(avg_fare, 2),
        "has_earnings": value_per_client is not None and value_per_client > 0,
        "timeseries": timeseries,
        "streak": streak,
        "today_log": _log_out(today_row) if today_row else None,
        "week": {
            "conversations": week_conv,
            "clients": week_clients,
            "revenue": round(week_revenue, 2),
        },
        "goal": goal,
        "projection": {
            "pace_per_day": round(pace, 2),
            "week": asdict(proj_week),
            "month": asdict(proj_month),
        },
    }


async def project(
    db: AsyncSession,
    *,
    tenant_id: int,
    period: str = "week",
    target_revenue: float | None = None,
    target_clients: float | None = None,
    days: int = 30,
) -> dict:
    """Goal calculator: given a revenue or client target for a period, return the
    required activity (total + per working day, with an effort band). Uses the
    smoothed funnel rates over the recent window."""
    period = period if period in _WEEKS else "week"
    sm = await summary(db, tenant_id=tenant_id, days=days)
    rates = fm.funnel_rates(
        conversations=sm["totals"]["conversations"],
        pitches=sm["totals"]["pitches"],
        contacts=sm["totals"]["contacts"],
        clients=sm["totals"]["clients"],
    )
    value_per_client = sm["value_per_client"]
    weeks = _WEEKS[period]
    working_days = sm["goal"]["working_days_per_week"] * weeks

    # Resolve a client target (from an explicit client goal, or from revenue).
    clients_target = None
    revenue_unknown = False
    if target_clients is not None:
        clients_target = max(0.0, float(target_clients))
    elif target_revenue is not None:
        c = fm.clients_for_revenue(float(target_revenue), value_per_client or 0.0)
        if c is None:
            revenue_unknown = True
        else:
            clients_target = c

    if clients_target is None:
        return {
            "period": period,
            "ok": False,
            "revenue_unknown": revenue_unknown,
            "value_per_client": value_per_client,
        }

    req = fm.required_activity(
        target_clients=clients_target, rates=rates, working_days=working_days
    )
    return {
        "period": period,
        "ok": True,
        "value_per_client": value_per_client,
        "target_clients": round(req.target_clients, 2),
        "working_days": round(working_days, 1),
        "required": {
            "conversations": round(req.conversations, 1),
            "pitches": round(req.pitches, 1),
            "contacts": round(req.contacts, 1),
            "conversations_per_day": round(req.conversations_per_day, 2),
            "conversations_per_day_low": round(req.conversations_per_day_low, 2),
            "conversations_per_day_high": round(req.conversations_per_day_high, 2),
        },
        "rates": {
            "overall_point": rates.overall_point,
            "low_data": rates.pitch.low_data or rates.contact.low_data or rates.convert.low_data,
        },
    }
