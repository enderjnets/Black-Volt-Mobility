"""'Where to wait' orchestration: turn the owner's trips, waits and offers plus the
static priors into the 7×24 planner per zone, on a schedule, cached in Redis.

Data flow per tenant:
  base_profile   — offers/min by hour-of-week (dispatch windows → trips → default)
  priors         — per-zone average of cell multipliers (affluence, hotels, generators)
  covariates     — DEN flight banks (relative), events near the zone, US/CO holidays
  own data       — `open` minutes (exposure) and Black/SUV offers per zone × hour
  posterior      — demand_model.posterior per (zone, hour), hours pooled ±1
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    DemandImport,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    EventSuggestion,
    HexPrior,
    OfferEvent,
    Ride,
    RideStatus,
    SegmentSource,
    UberProduct,
    UberTrip,
    WeekScore,
)
from app.services import demand_model as dm
from app.services import demand_places as dpl
from app.services import demand_spot
from app.services import flights_baseline as fb

logger = logging.getLogger("blackvolt.demand")

_PREMIUM = {UberProduct.BLACK, UberProduct.BLACK_SUV}
_LIVE_RATE_MIN_MINUTES = 600.0   # below this the global rate stays the default
_EVENT_RADIUS_MI = 3.0
_EVENT_LIFT = 1.5


def _miles(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


# ── Pure pieces ─────────────────────────────────────────────────────────────────
def _normalize(profile: list[float], level: float) -> list[float]:
    """Scale the pooled shape to `level` with every hour clamped to BASE_SHAPE_RANGE of
    the week mean. The clamp is the point: an hour the owner happened to log no trip in
    is thin evidence, not proof that no Black offer can arrive there, and an unbounded
    spike hands the driver with the least history the most confident-looking answer."""
    mean = sum(profile) / len(profile)
    if mean <= 0:
        return [level] * len(profile)
    return [dm.clamp(v / mean, *dm.BASE_SHAPE_RANGE) * level for v in profile]


def base_profile(
    *, windows: list[DispatchWindow], trips: list[UberTrip], live_rate: float | None
) -> list[float]:
    """168 offers/min. Shape from dispatch windows (real offer counts) when present,
    else from the trips' request-time histogram; level = live observed rate or default."""
    level = live_rate if live_rate is not None else dm.DEFAULT_BASE_RATE
    shape = [0.0] * dm.HOURS_PER_WEEK
    if windows:
        minutes = [0.0] * dm.HOURS_PER_WEEK
        for w in windows:
            how = dm.hour_of_week(w.window_start)
            shape[how] += float(w.dispatches or 0)
            minutes[how] += float(w.minutes_online or 0)
        shape = [s / m if m > 0 else 0.0 for s, m in zip(shape, minutes, strict=True)]
    elif trips:
        for t in trips:
            at = t.request_at or t.begin_at
            if at is not None:
                shape[dm.hour_of_week(at)] += 1.0
    else:
        return [level] * dm.HOURS_PER_WEEK
    pooled = [o for o, _ in dm.pool_hours([(v, 0.0) for v in shape])]
    return _normalize(pooled, level)


def event_multipliers(
    events: list[dict], zone: dict, now: datetime
) -> tuple[list[float], list[list[str]]]:
    """Lift the hours people travel to/from an event near the zone: 2h before doors
    to 1h after (arrivals) and 2h–4h after (departures)."""
    mult = [1.0] * dm.HOURS_PER_WEEK
    reasons: list[list[str]] = [[] for _ in range(dm.HOURS_PER_WEEK)]
    horizon = now + timedelta(days=7)
    for ev in events:
        if ev.get("lat") is None or ev.get("lng") is None:
            continue
        if _miles(ev["lat"], ev["lng"], zone["lat"], zone["lng"]) > _EVENT_RADIUS_MI:
            continue
        start = ev["starts_at"]
        if not (now <= start <= horizon):
            continue
        for off_h in (-2, -1, 0, 1, 2, 3, 4):
            how = dm.hour_of_week(start + timedelta(hours=off_h))
            mult[how] = max(mult[how], _EVENT_LIFT)
            if ev["title"] not in reasons[how]:
                reasons[how].append(ev["title"])
    return mult, reasons


def _segment_minutes_by_hour(segs: list[DriverStateSegment]) -> list[float]:
    """Exposure: `open` minutes per hour-of-week, walking each segment in 10-min steps."""
    out = [0.0] * dm.HOURS_PER_WEEK
    for s in segs:
        end = s.end_at or s.last_ping_at
        if end is None or end <= s.begin_at:
            continue
        t = s.begin_at
        while t < end:
            step = min(timedelta(minutes=10), end - t)
            out[dm.hour_of_week(t)] += step.total_seconds() / 60.0
            t += step
    return out


# ── DB helpers ──────────────────────────────────────────────────────────────────
async def tenants_with_data(db: AsyncSession) -> list[int]:
    ids: set[int] = set()
    for model in (DriverStateSegment, UberTrip, OfferEvent):
        rows = (await db.execute(select(model.tenant_id).distinct())).scalars().all()
        ids.update(int(r) for r in rows)
    return sorted(ids)


async def _zone_cells(db: AsyncSession) -> dict[str, list[HexPrior]]:
    rows = (
        await db.execute(select(HexPrior).where(HexPrior.zone_key.is_not(None)))
    ).scalars().all()
    out: dict[str, list[HexPrior]] = {}
    for r in rows:
        out.setdefault(r.zone_key, []).append(r)
    return out


async def _upcoming_events(db: AsyncSession, tenant_id: int, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(EventSuggestion).where(
                EventSuggestion.tenant_id == tenant_id,
                EventSuggestion.starts_at >= now,
                EventSuggestion.starts_at <= now + timedelta(days=7),
                EventSuggestion.venue_lat.is_not(None),
            )
        )
    ).scalars().all()
    return [
        {"title": r.title, "venue_name": r.venue_name, "lat": r.venue_lat,
         "lng": r.venue_lng, "starts_at": r.starts_at}
        for r in rows
    ]


def _holiday_dows(now: datetime) -> dict[int, str]:
    """dow → holiday name for the next 7 days (US + Colorado)."""
    try:
        import holidays

        cal = holidays.country_holidays("US", subdiv="CO", years={now.year, now.year + 1})
    except Exception as e:  # never block the recompute on the calendar package
        logger.warning("holidays unavailable: %s", e)
        return {}
    out: dict[int, str] = {}
    for i in range(7):
        d = (now.astimezone(dm.DENVER) + timedelta(days=i)).date()
        if d in cal:
            out[d.weekday()] = str(cal.get(d))
    return out


async def _gps_coverage(db: AsyncSession, tenant_id: int) -> list[tuple[datetime, datetime]]:
    """[start, end] of every imported GPS file: inside them the GPS owns the exposure."""
    rows = (
        await db.execute(
            select(DemandImport.summary).where(DemandImport.tenant_id == tenant_id)
        )
    ).scalars().all()
    out: list[tuple[datetime, datetime]] = []
    for summary in rows:
        gps = (summary or {}).get("gps") or {}
        if gps.get("start") and gps.get("end"):
            out.append((datetime.fromisoformat(gps["start"]), datetime.fromisoformat(gps["end"])))
    return out


# ── Recompute ───────────────────────────────────────────────────────────────────
async def recompute_week(
    db: AsyncSession, *, tenant_id: int, now: datetime | None = None
) -> dict:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    since = now - timedelta(days=90)

    windows = (
        await db.execute(select(DispatchWindow).where(DispatchWindow.tenant_id == tenant_id))
    ).scalars().all()
    trips = (
        await db.execute(
            select(UberTrip).where(
                UberTrip.tenant_id == tenant_id, UberTrip.product.in_(_PREMIUM)
            )
        )
    ).scalars().all()
    segs = (
        await db.execute(
            select(DriverStateSegment).where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.state == EarnerState.OPEN,
                DriverStateSegment.begin_at >= since,
            )
        )
    ).scalars().all()
    # Addendum A: inside a GPS coverage window the GPS owns the exposure; home never counts.
    coverage = await _gps_coverage(db, tenant_id)

    def _covered(at: datetime) -> bool:
        return any(a <= at <= b for a, b in coverage)

    segs = [
        s
        for s in segs
        if s.zone_key != "home"
        and not (s.source != SegmentSource.GPS and _covered(s.begin_at))
    ]
    offers = (
        await db.execute(
            select(OfferEvent).where(
                OfferEvent.tenant_id == tenant_id,
                OfferEvent.product.in_(_PREMIUM),
                OfferEvent.at >= since,
            )
        )
    ).scalars().all()
    # Export `enroute` segments = accepted offers with a location; the product comes
    # from the trip whose request time matches within 3 minutes.
    enroute = (
        await db.execute(
            select(DriverStateSegment).where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.state == EarnerState.ENROUTE,
                DriverStateSegment.begin_at >= since,
                DriverStateSegment.h3_r8.is_not(None),
            )
        )
    ).scalars().all()
    premium_requests = sorted(t.request_at for t in trips if t.request_at)

    def _is_premium_at(at: datetime) -> bool:
        lo = at - timedelta(minutes=3)
        hi = at + timedelta(minutes=3)
        return any(lo <= r <= hi for r in premium_requests)

    accepted_live = [o.at for o in offers if o.accepted]

    def _live_accepted_near(at: datetime) -> bool:
        return any(abs((a - at).total_seconds()) <= 180 for a in accepted_live)

    enroute = [s for s in enroute if not _live_accepted_near(s.begin_at)]

    total_open_min = sum(_segment_minutes_by_hour(segs))
    live_offers = len(offers) + sum(1 for s in enroute if _is_premium_at(s.begin_at))
    live_rate = (
        live_offers / total_open_min
        if total_open_min >= _LIVE_RATE_MIN_MINUTES and live_offers > 0
        else None
    )
    base = base_profile(windows=list(windows), trips=list(trips), live_rate=live_rate)

    zone_cells = await _zone_cells(db)
    baseline = await fb.load_baseline(db)
    events = await _upcoming_events(db, tenant_id, now)
    holidays_by_dow = _holiday_dows(now)
    denver_now = now.astimezone(dm.DENVER)

    await db.execute(delete(WeekScore).where(WeekScore.tenant_id == tenant_id))
    rows = 0
    for zone in dpl.ZONES:
        cells = zone_cells.get(zone["key"], [])
        if not cells:
            continue
        cell_ids = {c.h3_r8 for c in cells}
        # Static multiplier of the zone = mean over its cells (with base=1).
        static = sum(
            dm.prior_rate(1.0, affluence=c.affluence, hotels=c.hotels, generators=c.generators)
            for c in cells
        ) / len(cells)
        ev_mult, ev_reasons = event_multipliers(events, zone, now)
        zone_segs = [s for s in segs if s.h3_r8 in cell_ids or s.zone_key == zone["key"]]
        exposure = _segment_minutes_by_hour(zone_segs)
        offer_counts = [0.0] * dm.HOURS_PER_WEEK
        for o in offers:
            if o.h3_r8 in cell_ids:
                offer_counts[dm.hour_of_week(o.at)] += 1
        for s in enroute:
            if s.h3_r8 in cell_ids and _is_premium_at(s.begin_at):
                offer_counts[dm.hour_of_week(s.begin_at)] += 1
        pooled = dm.pool_hours(list(zip(offer_counts, exposure, strict=True)))

        for how in range(dm.HOURS_PER_WEEK):
            dow, hour = divmod(how, 24)
            month = (denver_now + timedelta(days=(dow - denver_now.weekday()) % 7)).month
            flights = fb.multipliers(baseline, month=month, dow=dow)[hour]
            flight_mult = flights if zone["key"] == "den" else 1.0 + 0.5 * (flights - 1.0)
            prior = (
                base[how]
                * static
                * dm.clamp(flight_mult, *dm.FLIGHT_RANGE)
                * dm.clamp(ev_mult[how], *dm.EVENT_RANGE)
            )
            y, e = pooled[how]
            est = dm.posterior(prior, y, e)
            # The posterior consumes the POOLED pair; `own_minutes`/`own_offers` report
            # the RAW ones. Pooling sums to exactly 2× the real week, and it is what the
            # driver reads to decide whether to trust a cell at all — an hour he has
            # never been online in has to say so, not borrow half of each neighbour.
            reasons = {
                "flights": round(flight_mult, 2),
                "events": ev_reasons[how],
                "holiday": holidays_by_dow.get(dow),
                "own_minutes": round(exposure[how], 1),
                "own_offers": round(offer_counts[how], 2),
            }
            db.add(
                WeekScore(
                    tenant_id=tenant_id, computed_at=now, zone_key=zone["key"], dow=dow,
                    hour=hour, mean=est.mean, lo=est.lo, hi=est.hi, own_share=est.own_share,
                    reasons=reasons,
                )
            )
            rows += 1
    await db.commit()
    await _cache_clear(tenant_id)
    return {"zones": rows // dm.HOURS_PER_WEEK, "rows": rows, "computed_at": now.isoformat()}


# ── Payload ─────────────────────────────────────────────────────────────────────
async def _private_rides(db: AsyncSession, tenant_id: int, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(Ride).where(
                Ride.tenant_id == tenant_id,
                Ride.scheduled_at >= now,
                Ride.scheduled_at <= now + timedelta(days=7),
                Ride.status.in_([RideStatus.CONFIRMED, RideStatus.ASSIGNED]),
            )
        )
    ).scalars().all()
    return [
        {"id": r.id, "at": r.scheduled_at.isoformat(), "pickup": r.pickup_text}
        for r in rows
    ]


def _block_reasons(grid: list[list[dict | None]], b: dm.Block) -> dict:
    """The covariates that lifted the BLOCK, which is not the same as the ones that
    lifted its first hour.

    The spec asks each block to carry "the covariates that lifted it". Reading
    `grid[dow][start_hour]["reasons"]` answered a different question: an event that
    starts at 20:00 inside an 18:00–22:00 block, or a flight bank that lands on any
    hour but the first, is a reason the block exists and was silently dropped from the
    row the driver reads. Events are unioned in order of first appearance, the flight
    multiplier is the block's peak (the row prints one number, so it must be the one
    worth driving for), and the two own-data figures are summed because over a block
    they are totals. `holiday` is per-day, so any hour of the block carries it.

    start_hour is inclusive and end_hour exclusive, and top_blocks never crosses
    midnight, so every hour in the range belongs to the same day.
    """
    hours = [(grid[b.dow][h] or {}).get("reasons") or {} for h in range(b.start_hour, b.end_hour)]
    if not hours:
        return {}
    events: list[str] = []
    for r in hours:
        for ev in r.get("events") or []:
            if ev not in events:
                events.append(ev)
    return {
        "flights": max((r.get("flights") or 1.0) for r in hours),
        "events": events,
        "holiday": next((r.get("holiday") for r in hours if r.get("holiday")), None),
        "own_minutes": round(sum(r.get("own_minutes") or 0.0 for r in hours), 1),
        "own_offers": round(sum(r.get("own_offers") or 0.0 for r in hours), 2),
    }


async def _own_by_cell(db: AsyncSession, tenant_id: int) -> dict[str, tuple[float, float]]:
    """cell → (open minutes, premium offers) over the whole history.

    The planner only ever asked whether a cell belonged to a zone; this is the first
    place that cares WHICH cell, because "where do I park" cannot be answered at the
    scale of a two-and-a-half mile circle. Deliberately not restricted to a block's
    hours: with a few hundred wait segments in total, an hour-restricted per-cell count
    is empty nearly everywhere, and an empty answer dressed as a specific one is worse
    than an honest general one.
    """
    since = datetime.now(UTC) - timedelta(days=90)
    minutes: dict[str, float] = {}
    offers: dict[str, float] = {}

    segs = (
        await db.execute(
            select(DriverStateSegment).where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.state == EarnerState.OPEN,
                DriverStateSegment.begin_at >= since,
                DriverStateSegment.h3_r8.is_not(None),
            )
        )
    ).scalars().all()
    for s in segs:
        if s.zone_key == "home":
            continue
        minutes[s.h3_r8] = minutes.get(s.h3_r8, 0.0) + (
            s.end_at - s.begin_at
        ).total_seconds() / 60.0

    rows = (
        await db.execute(
            select(OfferEvent).where(
                OfferEvent.tenant_id == tenant_id,
                OfferEvent.product.in_(_PREMIUM),
                OfferEvent.at >= since,
                OfferEvent.h3_r8.is_not(None),
            )
        )
    ).scalars().all()
    for o in rows:
        offers[o.h3_r8] = offers.get(o.h3_r8, 0.0) + 1.0

    return {c: (minutes.get(c, 0.0), offers.get(c, 0.0)) for c in set(minutes) | set(offers)}


async def week_payload(db: AsyncSession, *, tenant_id: int, zone: str | None) -> dict | None:
    zones = [{"key": z["key"], "name": z["name"]} for z in dpl.ZONES]
    keys = {z["key"] for z in dpl.ZONES}
    if zone is not None and zone not in keys:
        return None
    rows = (
        await db.execute(select(WeekScore).where(WeekScore.tenant_id == tenant_id))
    ).scalars().all()
    if not rows:
        await recompute_week(db, tenant_id=tenant_id)
        rows = (
            await db.execute(select(WeekScore).where(WeekScore.tenant_id == tenant_id))
        ).scalars().all()
    if not rows:
        return {"zone": zone, "zone_name": None, "zones": zones, "computed_at": None,
                "grid": [], "top_blocks": [], "private_rides": [], "own_minutes_total": 0,
                "baseline_mean": 0.0}
    if zone is None:
        # Default: the zone with the most of the owner's own minutes, else the first scored.
        by_zone: dict[str, float] = {}
        for r in rows:
            by_zone[r.zone_key] = by_zone.get(r.zone_key, 0.0) + float(
                (r.reasons or {}).get("own_minutes", 0.0)
            )
        zone = max(by_zone, key=by_zone.get)
    cached = await _cache_get(tenant_id, zone)
    if cached is not None:
        return cached
    zrows = [r for r in rows if r.zone_key == zone]
    if not zrows:
        return None
    grid = [[None] * 24 for _ in range(7)]
    ests: list[dm.Estimate] = [None] * dm.HOURS_PER_WEEK  # type: ignore[list-item]
    for r in zrows:
        est = dm.Estimate(r.mean, r.lo, r.hi, r.own_share,
                          (r.reasons or {}).get("own_offers", 0.0),
                          (r.reasons or {}).get("own_minutes", 0.0))
        ests[r.dow * 24 + r.hour] = est
        grid[r.dow][r.hour] = {
            "mean": r.mean, "lo": r.lo, "hi": r.hi, "p15": dm.p_within(r.mean),
            "own_share": r.own_share, "reasons": r.reasons or {},
        }
    blocks = dm.top_blocks(ests) if all(e is not None for e in ests) else []
    # What a block is worth is reported as a ratio against a normal hour, not as a count
    # of offers. The count stacks four multipliers — income, hotels, events, flights —
    # into peaks around 11x the base, and that scale has never been checked against a
    # real week: the owner's own history runs an order of magnitude below it. The ORDER
    # those multipliers produce has been checked and holds, and a ratio is the part of
    # the model that survives being wrong about the scale.
    #
    # Both sides of the ratio come from the model. Dividing a model estimate by a
    # measured rate would be the frame error this feature has already made six times.
    # The median, not the mean, because the mean is inflated by the very peaks in
    # question. Across ALL zones, so the number stays comparable between them — a
    # per-zone baseline would give every zone's best block the same ratio and destroy
    # exactly the comparison the driver is making.
    all_means = sorted(r.mean for r in rows)
    baseline = all_means[len(all_means) // 2] if all_means else 0.0
    now = datetime.now(UTC)
    # Only pay for the spot inputs when there is a block to place. Three reads on a
    # cache miss, none on a hit, and none at all for a zone with nothing to recommend.
    spot_cells: list = []
    spot_events: list[dict] = []
    own_cells: dict[str, tuple[float, float]] = {}
    if blocks:
        spot_cells = (await _zone_cells(db)).get(zone, [])
        spot_events = await _upcoming_events(db, tenant_id, now)
        own_cells = await _own_by_cell(db, tenant_id)
    settings = get_settings()
    den_lot = (
        (settings.DEN_LOT_LAT, settings.DEN_LOT_LNG)
        if settings.DEN_LOT_LAT is not None and settings.DEN_LOT_LNG is not None
        else None
    )
    zone_def = next(z for z in dpl.ZONES if z["key"] == zone)
    places = dpl.load_geocoded()
    if den_lot is not None:
        places = {**places, "DEN Commercial Holding Lot": den_lot}

    def _spot_for(b: dm.Block) -> dict | None:
        return demand_spot.pick_spot(
            zone=zone_def,
            block_events=list(_block_reasons(grid, b).get("events") or []),
            cells=spot_cells,
            own_by_cell=own_cells,
            places=places,
            events=spot_events,
            den_lot=den_lot,
        )

    payload = {
        "zone": zone,
        "zone_name": next(z["name"] for z in zones if z["key"] == zone),
        "zones": zones,
        "computed_at": zrows[0].computed_at.isoformat(),
        "grid": grid,
        "top_blocks": [
            {"dow": b.dow, "start_hour": b.start_hour, "end_hour": b.end_hour,
             "expected_offers": round(b.expected_offers, 2), "mean": b.mean,
             "reasons": _block_reasons(grid, b), "spot": _spot_for(b),
             "lift": round(b.mean / baseline, 1) if baseline > 0 else None}
            for b in blocks
        ],
        "private_rides": await _private_rides(db, tenant_id, now),
        "own_minutes_total": round(sum(e.exposure_min for e in ests if e), 1),
        "baseline_mean": baseline,
    }
    await _cache_set(tenant_id, zone, payload)
    return payload


def etag_for(payload: dict) -> str:
    return '"' + hashlib.sha1(
        f"{PAYLOAD_VERSION}|{payload.get('computed_at')}|{payload.get('zone')}".encode()
    ).hexdigest()[:16] + '"'


# ── Redis (best-effort, same pattern as coach.py) ───────────────────────────────
# Bump when the payload SHAPE changes. Neither the cache key nor the ETag knows anything
# about shape, so a new field is otherwise invisible for up to the 2 h TTL.
#
# v2 -> v3 added `baseline_mean` and `top_blocks[].lift`. Worth recording that this
# constant was introduced and then forgotten within the same afternoon: the next shape
# change shipped without touching it, and the payload came back from Redis missing the
# field it had just gained. A version you have to remember is a version you will forget,
# so the guard that actually works is the test asserting the new field survives a round
# trip — not this line.
PAYLOAD_VERSION = "v3"


def _key_prefix(tenant_id: int) -> str:
    """Every key for a tenant, and the thing the invalidator sweeps.

    The two used to be written out separately, and the moment a version was added
    between `week` and the tenant id the sweep silently stopped matching: a recompute no
    longer refreshed anything, and the driver kept the old week for the length of the
    TTL. One source, so they cannot drift again.
    """
    return f"demand:week:{PAYLOAD_VERSION}:{tenant_id}:"


def _key(tenant_id: int, zone: str) -> str:
    return f"{_key_prefix(tenant_id)}{zone}"


async def _cache_get(tenant_id: int, zone: str) -> dict | None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            raw = await client.get(_key(tenant_id, zone))
        finally:
            await client.aclose()
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning("demand cache get failed: %s", e)
        return None


async def _cache_set(tenant_id: int, zone: str, value: dict) -> None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            await client.set(_key(tenant_id, zone), json.dumps(value), ex=2 * 3600)
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("demand cache set failed: %s", e)


async def _cache_clear(tenant_id: int) -> None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            # The current shape, plus whatever an older release left behind: those
            # would expire on their own, but a rollback would start reading them again.
            keys = await client.keys(f"{_key_prefix(tenant_id)}*")
            keys += await client.keys(f"demand:week:{tenant_id}:*")
            if keys:
                await client.delete(*keys)
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("demand cache clear failed: %s", e)
