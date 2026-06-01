"""Analytics service: ingest usage events and aggregate them for the Insights
dashboard. Tenant-scoped. Pseudonymous — no raw IP stored."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsEvent

MAX_BATCH = 50
_KNOWN_DEVICES = {"mobile", "tablet", "desktop"}


def _trunc(v, n: int) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s[:n] if len(s) > n else s


def device_from_ua(ua: str | None) -> str:
    """Coarse device class from a user-agent string."""
    if not ua:
        return "desktop"
    u = ua.lower()
    if "ipad" in u or "tablet" in u or ("android" in u and "mobile" not in u):
        return "tablet"
    if "mobi" in u or "iphone" in u or "android" in u:
        return "mobile"
    return "desktop"


async def record_events(
    db: AsyncSession, *, tenant_id: int, events: list[dict], ctx: dict
) -> int:
    """Persist a batch of events. ctx carries server-derived fields:
    {client_id, role, country, user_agent}. Returns the number inserted."""
    rows: list[AnalyticsEvent] = []
    for ev in events[:MAX_BATCH]:
        if not isinstance(ev, dict):
            continue
        etype = _trunc(ev.get("type") or ev.get("event_type"), 40)
        if not etype:
            continue
        utm = ev.get("utm") if isinstance(ev.get("utm"), dict) else {}
        device = ev.get("device")
        if device not in _KNOWN_DEVICES:
            device = device_from_ua(ctx.get("user_agent"))
        dur = ev.get("duration_ms")
        try:
            dur = int(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur = None
        rows.append(
            AnalyticsEvent(
                tenant_id=tenant_id,
                visitor_id=_trunc(ev.get("visitor_id"), 64),
                session_id=_trunc(ev.get("session_id"), 64),
                client_id=ctx.get("client_id"),
                role=_trunc(ctx.get("role"), 20),
                event_type=etype,
                path=_trunc(ev.get("path"), 400),
                referrer=_trunc(ev.get("referrer"), 400),
                utm_source=_trunc(ev.get("utm_source") or utm.get("source"), 120),
                utm_medium=_trunc(ev.get("utm_medium") or utm.get("medium"), 120),
                utm_campaign=_trunc(ev.get("utm_campaign") or utm.get("campaign"), 120),
                device=device,
                country=_trunc(ctx.get("country"), 2),
                duration_ms=dur if dur and dur > 0 else None,
                props=ev.get("props") if isinstance(ev.get("props"), dict) else None,
            )
        )
    if not rows:
        return 0
    db.add_all(rows)
    await db.commit()
    return len(rows)


async def _group_count(db, col, where, *, limit=10, label="value"):
    """Top-N (value, count) for a column, ignoring NULL/empty values."""
    q = (
        select(col.label(label), func.count().label("count"))
        .where(*where, col.isnot(None), col != "")
        .group_by(col)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [{"value": r[0], "count": r[1]} for r in (await db.execute(q)).all()]


async def summary(db: AsyncSession, *, tenant_id: int, days: int = 30) -> dict:
    """Aggregate usage stats for the last `days` for the Insights dashboard."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    base = [AnalyticsEvent.tenant_id == tenant_id, AnalyticsEvent.created_at >= cutoff]
    pv = [*base, AnalyticsEvent.event_type == "pageview"]
    ss = [*base, AnalyticsEvent.event_type == "session_start"]
    dur = [*base, AnalyticsEvent.event_type == "page_duration"]

    pageviews = (await db.execute(select(func.count()).where(*pv))).scalar_one()
    visitors = (
        await db.execute(select(func.count(distinct(AnalyticsEvent.visitor_id))).where(*base))
    ).scalar_one()
    sessions = (
        await db.execute(select(func.count(distinct(AnalyticsEvent.session_id))).where(*base))
    ).scalar_one()
    total_dur = (
        await db.execute(select(func.coalesce(func.sum(AnalyticsEvent.duration_ms), 0)).where(*dur))
    ).scalar_one()
    avg_session_ms = int(total_dur / sessions) if sessions else 0

    # Pageviews + visitors per day.
    day = func.date(AnalyticsEvent.created_at)
    ts_q = (
        select(
            day.label("day"),
            func.count().label("pageviews"),
            func.count(distinct(AnalyticsEvent.visitor_id)).label("visitors"),
        )
        .where(*pv)
        .group_by(day)
        .order_by(day)
    )
    timeseries = [
        {"day": str(r.day), "pageviews": r.pageviews, "visitors": r.visitors}
        for r in (await db.execute(ts_q)).all()
    ]

    # Top pages: views + avg time on page.
    tp_q = (
        select(AnalyticsEvent.path, func.count().label("views"))
        .where(*pv, AnalyticsEvent.path.isnot(None))
        .group_by(AnalyticsEvent.path)
        .order_by(func.count().desc())
        .limit(12)
    )
    avg_q = (
        select(AnalyticsEvent.path, func.avg(AnalyticsEvent.duration_ms).label("avg_ms"))
        .where(*dur, AnalyticsEvent.path.isnot(None))
        .group_by(AnalyticsEvent.path)
    )
    avg_by_path = {r.path: int(r.avg_ms or 0) for r in (await db.execute(avg_q)).all()}
    top_pages = [
        {"path": r.path, "views": r.views, "avg_ms": avg_by_path.get(r.path, 0)}
        for r in (await db.execute(tp_q)).all()
    ]

    # Booking funnel + sign-ins (raw event counts).
    funnel_types = ["book_start", "book_review", "book_pay", "book_confirmed", "sign_in"]
    fq = (
        select(AnalyticsEvent.event_type, func.count())
        .where(*base, AnalyticsEvent.event_type.in_(funnel_types))
        .group_by(AnalyticsEvent.event_type)
    )
    fcounts = {r[0]: r[1] for r in (await db.execute(fq)).all()}
    funnel = {t: fcounts.get(t, 0) for t in funnel_types}

    # Breakdowns from session_start rows (one per session, full context).
    devices = await _group_count(db, AnalyticsEvent.device, ss)
    countries = await _group_count(db, AnalyticsEvent.country, ss)
    referrers = await _group_count(db, AnalyticsEvent.referrer, ss, limit=8)
    utm_sources = await _group_count(db, AnalyticsEvent.utm_source, ss, limit=8)

    # Recent activity.
    rec_q = (
        select(
            AnalyticsEvent.event_type, AnalyticsEvent.path, AnalyticsEvent.created_at
        )
        .where(*base)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(15)
    )
    recent = [
        {"type": r.event_type, "path": r.path, "created_at": r.created_at.isoformat()}
        for r in (await db.execute(rec_q)).all()
    ]

    return {
        "days": days,
        "totals": {
            "visitors": visitors,
            "sessions": sessions,
            "pageviews": pageviews,
            "avg_session_ms": avg_session_ms,
        },
        "timeseries": timeseries,
        "top_pages": top_pages,
        "funnel": funnel,
        "devices": devices,
        "countries": countries,
        "referrers": referrers,
        "utm_sources": utm_sources,
        "recent": recent,
    }
