"""Analytics service: ingest usage events and aggregate them for the Insights
dashboard. Tenant-scoped. Pseudonymous — no raw IP stored."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsEvent

MAX_BATCH = 50
# Cap time-on-page so an idle/backgrounded tab (e.g. a dashboard left open for hours)
# can't inflate the average. 30 min is well beyond any genuine page view.
MAX_DURATION_MS = 1_800_000
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
                duration_ms=min(int(dur), MAX_DURATION_MS) if dur and dur > 0 else None,
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


_STEP_KEY = {
    "book_start": "starts",
    "book_review": "reviewed",
    "book_pay": "paid",
    "book_confirmed": "confirmed",
}


async def _campaign_funnel(db, base, step_types: list[str]) -> list[dict]:
    """Funnel by UTM campaign via session attribution: a session's campaign comes from its
    session_start; funnel events are matched by shared session_id. Top campaigns by starts."""
    ss_rows = (
        await db.execute(
            select(
                AnalyticsEvent.session_id,
                func.max(AnalyticsEvent.utm_campaign),
                func.max(AnalyticsEvent.utm_source),
            )
            .where(*base, AnalyticsEvent.event_type == "session_start")
            .group_by(AnalyticsEvent.session_id)
        )
    ).all()
    sess_camp: dict[str, tuple[str, str]] = {}
    for sid, camp, src in ss_rows:
        if sid:
            sess_camp[sid] = (camp or "(none)", src or "(none)")

    fr_rows = (
        await db.execute(
            select(AnalyticsEvent.session_id, AnalyticsEvent.event_type)
            .where(*base, AnalyticsEvent.event_type.in_(step_types))
            .distinct()
        )
    ).all()

    def _blank(camp: str, src: str) -> dict:
        return {
            "campaign": camp, "source": src, "sessions": 0,
            "starts": 0, "reviewed": 0, "paid": 0, "confirmed": 0,
        }

    agg: dict[str, dict] = {}
    for _sid, (camp, src) in sess_camp.items():
        agg.setdefault(camp, _blank(camp, src))["sessions"] += 1
    for sid, etype in fr_rows:
        camp, src = sess_camp.get(sid, ("(none)", "(none)"))
        agg.setdefault(camp, _blank(camp, src))[_STEP_KEY[etype]] += 1

    rows = sorted(agg.values(), key=lambda r: (r["starts"], r["sessions"]), reverse=True)
    return rows[:8]


async def summary(db: AsyncSession, *, tenant_id: int, days: int = 30) -> dict:
    """Aggregate usage stats for the last `days` for the Insights dashboard."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    base = [
        AnalyticsEvent.tenant_id == tenant_id,
        AnalyticsEvent.created_at >= cutoff,
        # Insights reflects the public booking site, not the operator's own dashboard
        # usage — exclude staff (owner/driver) traffic and any /dashboard/* page. NULL role
        # (legacy) counts as a visitor; NULL path (non-pageview events) is kept.
        func.coalesce(AnalyticsEvent.role, "anon").notin_(("owner", "driver")),
        ~func.coalesce(AnalyticsEvent.path, "").like("/dashboard%"),
    ]
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
        await db.execute(
            select(
                func.coalesce(
                    func.sum(func.least(AnalyticsEvent.duration_ms, MAX_DURATION_MS)), 0
                )
            ).where(*dur)
        )
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
        select(
            AnalyticsEvent.path,
            func.avg(func.least(AnalyticsEvent.duration_ms, MAX_DURATION_MS)).label("avg_ms"),
        )
        .where(*dur, AnalyticsEvent.path.isnot(None))
        .group_by(AnalyticsEvent.path)
    )
    avg_by_path = {r.path: int(r.avg_ms or 0) for r in (await db.execute(avg_q)).all()}
    top_pages = [
        {"path": r.path, "views": r.views, "avg_ms": avg_by_path.get(r.path, 0)}
        for r in (await db.execute(tp_q)).all()
    ]

    # Booking funnel — counted by DISTINCT sessions reaching each step (conversion semantics,
    # not raw clicks). sign_in / book_pay_failed stay as raw event counts (side metrics).
    step_types = ["book_start", "book_review", "book_pay", "book_confirmed"]
    sq = (
        select(AnalyticsEvent.event_type, func.count(func.distinct(AnalyticsEvent.session_id)))
        .where(*base, AnalyticsEvent.event_type.in_(step_types))
        .group_by(AnalyticsEvent.event_type)
    )
    scounts = {r[0]: r[1] for r in (await db.execute(sq)).all()}
    eq = (
        select(AnalyticsEvent.event_type, func.count())
        .where(*base, AnalyticsEvent.event_type.in_(["sign_in", "book_pay_failed"]))
        .group_by(AnalyticsEvent.event_type)
    )
    ecounts = {r[0]: r[1] for r in (await db.execute(eq)).all()}
    funnel = {t: scounts.get(t, 0) for t in step_types}
    funnel["sign_in"] = ecounts.get("sign_in", 0)
    funnel["book_pay_failed"] = ecounts.get("book_pay_failed", 0)

    # Conversion by UTM campaign — session attribution (funnel events carry no utm; only
    # session_start does, and they share session_id).
    campaigns = await _campaign_funnel(db, base, step_types)

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
        "campaigns": campaigns,
        "devices": devices,
        "countries": countries,
        "referrers": referrers,
        "utm_sources": utm_sources,
        "recent": recent,
    }
