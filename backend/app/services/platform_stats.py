"""Platform stats: read an Uber/Lyft/Co-op earnings screenshot with the AI vision
model, and store/aggregate the result for the My Stats platform-income panel.

Extraction mirrors services/smart.py (same vision providers, same simulated
fallback) but with its own prompt/keys. Persistence + the platform-vs-private
comparison are tenant-scoped DB reads. Nothing here touches the sales funnel.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PlatformStat, Ride
from app.services import llm
from app.services.booking import earned_ride_filter

logger = logging.getLogger("blackvolt.platform")

PLATFORMS = ("uber", "lyft", "coop", "other")
EXTRACT_KEYS = (
    "platform",
    "period_label",
    "period_start",
    "period_end",
    "trips",
    "earnings",
    "online_hours",
    "currency",
)

EXTRACT_PROMPT = (
    "You read a screenshot of a rideshare DRIVER's earnings/stats summary from an "
    "app like Uber Driver, Lyft Driver, or a co-op/other rideshare platform. The "
    "image shows totals for a period — typically total earnings, number of trips, "
    "and online/active hours, plus a date range or label.\n"
    "Return ONLY a JSON object — no prose, no markdown — with EXACTLY these keys, "
    "using null when a value is not visible:\n"
    '{"platform": "uber"|"lyft"|"coop"|"other"|null, "period_label": string|null, '
    '"period_start": string|null, "period_end": string|null, "trips": number|null, '
    '"earnings": number|null, "online_hours": number|null, "currency": string|null}\n'
    "Notes:\n"
    '- "platform": which app, lowercased; use "coop" for a cooperative/other named '
    'rideshare, "other" if unclear.\n'
    '- "period_label": the period as shown (e.g. "This week", "Jun 9 - Jun 15").\n'
    '- "period_start"/"period_end": ISO dates (YYYY-MM-DD) if a range is shown, '
    "else null.\n"
    '- "trips": total trips/rides as an integer.\n'
    '- "earnings": total earnings as a number (dollars), no currency symbol.\n'
    '- "online_hours": online/active hours as a number (decimal hours).\n'
    '- "currency": 3-letter code (e.g. "USD") if shown, else null.'
)

# Returned in simulated mode (no vision key) so the panel works offline.
SAMPLE_EXTRACTION: dict = {
    "platform": "uber",
    "period_label": "This week",
    "period_start": None,
    "period_end": None,
    "trips": 42,
    "earnings": 884.50,
    "online_hours": 31.5,
    "currency": "USD",
}


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _coerce(obj: dict) -> dict:
    out = {k: obj.get(k) for k in EXTRACT_KEYS}
    p = out.get("platform")
    if p is not None:
        s = str(p).strip().lower()
        out["platform"] = s if s in PLATFORMS else "other"
    trips_n = _num(out.get("trips"))
    out["trips"] = int(trips_n) if trips_n is not None else None
    out["earnings"] = _num(out.get("earnings"))
    out["online_hours"] = _num(out.get("online_hours"))
    cur = out.get("currency")
    out["currency"] = (str(cur).strip().upper()[:3] or None) if cur else None
    for k in ("period_label", "period_start", "period_end"):
        v = out.get(k)
        out[k] = str(v).strip()[:80] if v not in (None, "") else None
    return out


def _parse_json(text: str) -> dict:
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no_json_object")
    return json.loads(text[a : b + 1])


async def _extract_anthropic(images: list[tuple[str, bytes]]) -> dict:
    import base64

    settings = get_settings()
    payload = [(mt, base64.b64encode(raw).decode("ascii")) for mt, raw in images]
    text = await llm.vision_complete(
        prompt=EXTRACT_PROMPT,
        images=payload,
        model=settings.SMART_VISION_MODEL,
        base_url=settings.SMART_VISION_BASE_URL,
        api_key=settings.SMART_VISION_API_KEY,
        max_tokens=512,
    )
    return _coerce(_parse_json(text))


async def _extract_vlm(images: list[tuple[str, bytes]]) -> dict:
    """One image is enough for a stats summary; use the first, retry transient
    failures via the coding-plan VLM."""
    import base64

    settings = get_settings()
    mt, raw = images[0]
    data_url = f"data:{mt};base64,{base64.b64encode(raw).decode('ascii')}"
    last: Exception | None = None
    for _ in range(2):
        try:
            text = await llm.minimax_vlm_understand(
                host=settings.SMART_VISION_HOST,
                api_key=settings.SMART_VISION_API_KEY,
                prompt=EXTRACT_PROMPT,
                image_data_url=data_url,
                timeout=settings.SMART_VISION_TIMEOUT,
            )
            return _coerce(_parse_json(text))
        except Exception as e:
            last = e
    raise llm.LLMError(f"vlm:{type(last).__name__ if last else 'failed'}")


async def extract_platform_stats(images: list[tuple[str, bytes]]) -> dict:
    """Read a stats screenshot → draft fields (the driver reviews before saving).
    Simulated mode returns SAMPLE_EXTRACTION; a live failure returns all-null."""
    settings = get_settings()
    if not settings.smart_live:
        return _coerce(dict(SAMPLE_EXTRACTION))
    try:
        if settings.SMART_VISION_PROVIDER == "minimax_anthropic":
            return await _extract_anthropic(images)
        return await _extract_vlm(images)
    except Exception as e:  # extraction must never 500 the endpoint
        logger.warning("platform extract failed: %s", e)
        return {k: None for k in EXTRACT_KEYS}


# ── Persistence + aggregation ────────────────────────────────────────────────
def _row_out(r: PlatformStat) -> dict:
    return {
        "id": r.id,
        "platform": r.platform,
        "period_label": r.period_label,
        "period_start": str(r.period_start) if r.period_start else None,
        "period_end": str(r.period_end) if r.period_end else None,
        "trips": r.trips,
        "earnings": r.earnings,
        "online_hours": r.online_hours,
        "currency": r.currency,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _as_date(v: str | date | None) -> date | None:
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


async def save_stat(
    db: AsyncSession,
    *,
    tenant_id: int,
    platform: str,
    period_label: str | None,
    period_start: str | date | None,
    period_end: str | date | None,
    trips: int | None,
    earnings: float | None,
    online_hours: float | None,
    currency: str | None,
) -> dict:
    row = PlatformStat(
        tenant_id=tenant_id,
        platform=platform if platform in PLATFORMS else "other",
        period_label=(period_label or None),
        period_start=_as_date(period_start),
        period_end=_as_date(period_end),
        trips=max(0, int(trips)) if trips is not None else None,
        earnings=max(0.0, float(earnings)) if earnings is not None else None,
        online_hours=max(0.0, float(online_hours)) if online_hours is not None else None,
        currency=(currency or "USD").upper()[:3],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_out(row)


async def delete_stat(db: AsyncSession, *, tenant_id: int, stat_id: int) -> bool:
    row = (
        await db.execute(
            select(PlatformStat).where(
                PlatformStat.tenant_id == tenant_id, PlatformStat.id == stat_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def summary(db: AsyncSession, *, tenant_id: int, days: int = 30) -> dict:
    """Platform totals over the window + a per-platform breakdown, plus the
    driver's private (Black Volt) earned revenue in the same window for the
    platform-vs-private comparison. Stats are attributed to period_end (falling
    back to the import date)."""
    days = max(1, min(int(days), 365))
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    attr_day = func.coalesce(PlatformStat.period_end, func.date(PlatformStat.created_at))

    rows = (
        await db.execute(
            select(PlatformStat)
            .where(PlatformStat.tenant_id == tenant_id, attr_day >= start, attr_day <= today)
            .order_by(PlatformStat.id.desc())
        )
    ).scalars().all()

    by_platform: dict[str, dict] = {}
    tot_earnings = 0.0
    tot_trips = 0
    tot_hours = 0.0
    for r in rows:
        b = by_platform.setdefault(
            r.platform, {"platform": r.platform, "earnings": 0.0, "trips": 0, "hours": 0.0}
        )
        b["earnings"] += r.earnings or 0.0
        b["trips"] += r.trips or 0
        b["hours"] += r.online_hours or 0.0
        tot_earnings += r.earnings or 0.0
        tot_trips += r.trips or 0
        tot_hours += r.online_hours or 0.0

    # Private earned revenue in the same window (completed-or-paid rides).
    ride_day = func.date(func.coalesce(Ride.scheduled_at, Ride.created_at))
    private_revenue = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Ride.fare_total), 0.0)).where(
                    Ride.tenant_id == tenant_id,
                    earned_ride_filter(),
                    ride_day >= start,
                    ride_day <= today,
                )
            )
        ).scalar_one()
    )

    platform_total = round(tot_earnings, 2)
    per_trip = round(tot_earnings / tot_trips, 2) if tot_trips else None
    per_hour = round(tot_earnings / tot_hours, 2) if tot_hours else None
    return {
        "days": days,
        "totals": {
            "earnings": platform_total,
            "trips": int(tot_trips),
            "online_hours": round(tot_hours, 1),
            "per_trip": per_trip,
            "per_hour": per_hour,
        },
        "by_platform": sorted(
            (
                {
                    "platform": p["platform"],
                    "earnings": round(p["earnings"], 2),
                    "trips": p["trips"],
                    "hours": round(p["hours"], 1),
                }
                for p in by_platform.values()
            ),
            key=lambda x: x["earnings"],
            reverse=True,
        ),
        "private_revenue": round(private_revenue, 2),
        "comparison": {
            "platform": platform_total,
            "private": round(private_revenue, 2),
            "private_share": (
                round(private_revenue / (private_revenue + platform_total), 3)
                if (private_revenue + platform_total) > 0
                else None
            ),
        },
        "imports": [_row_out(r) for r in rows[:20]],
    }
