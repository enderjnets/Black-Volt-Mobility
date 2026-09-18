"""The 30-day GPS analytics import (Addendum A, Task 15).

The US Uber export ships no "Online Offline" file, so the trips file (already
parsed by `uber_import`) is the only authority on what the driver was DOING at any
moment: a ping is only "open" (exposure worth scoring) when no trip's
request→dropoff window claims it as busy. GPS pings alone cannot tell waiting from
driving home, so the owner's home radius is excluded from exposure — a driver
open at home is not competing for a fare, and counting it would inflate every
"waits this month" number with hours that were never really available.

`segment_pings`/`locate_trips`/`request_cells`/`top_waits` are pure (bytes/dataclasses
in, dataclasses/dicts out); `import_pings` is the only impure function — it upserts
`driver_state_segments` (source=gps) and backfills `uber_trips.begin_lat/lng`, and
replaces the tenant's gps segments for the coverage window it just parsed so a
monthly re-import (with overlap) never double-counts.
"""
from __future__ import annotations

import bisect
import hashlib
import math
from datetime import datetime, timedelta

import h3
from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import DriverStateSegment, EarnerState, SegmentSource, UberTrip
from app.services import demand_places
from app.services.shift_log import _haversine_m
from app.services.uber_import import ParsedPing, ParsedSegment, ParsedTrip, _cell, _round5, _upsert

DWELL_S = 60
GAP_S = 600
MATCH_S = 120
CANCEL_S = 60
TOP_WAITS = 10
LABEL_KM = 2.0


def coverage(pings: list[ParsedPing]) -> tuple[datetime, datetime] | None:
    if not pings:
        return None
    times = [p.at for p in pings]
    return min(times), max(times)


def _busy_start(t: ParsedTrip) -> datetime:
    """A scheduled ride can be dispatched (`request_at`) after it already began
    (`begin_at`) — the busy window has to start at the earlier of the two, or the
    driver reads as "open" while already driving a passenger."""
    if t.begin_at is not None and t.begin_at < t.request_at:
        return t.begin_at
    return t.request_at


def _busy_end(t: ParsedTrip) -> datetime:
    if t.dropoff_at is not None:
        return t.dropoff_at
    return t.request_at + timedelta(seconds=CANCEL_S)


def _scoped_trips(
    trips: list[ParsedTrip], start: datetime, end: datetime
) -> list[ParsedTrip]:
    return [t for t in trips if t.request_at is not None and start <= t.request_at <= end]


def _non_queued(
    scoped: list[ParsedTrip], busy: list[tuple[datetime, datetime]]
) -> list[ParsedTrip]:
    """Trips whose request did not arrive inside ANOTHER trip's busy window — the
    driver was open, so the offer counts; a queued request does not."""
    out = []
    for i, t in enumerate(scoped):
        if not any(j != i and s <= t.request_at <= e for j, (s, e) in enumerate(busy)):
            out.append(t)
    return out


def _offer_context(
    trips: list[ParsedTrip], start: datetime, end: datetime
) -> tuple[list[ParsedTrip], list[tuple[datetime, datetime]], list[ParsedTrip]]:
    """Shared by `segment_pings` and `request_cells`: trips scoped to the file's
    coverage, their busy windows, and which of those are offers received while
    open — non-queued, and not a scheduled ride whose `begin_at` precedes its
    `request_at` (that ride was already under way, not an offer being waited on)."""
    scoped = _scoped_trips(trips, start, end)
    busy = [(_busy_start(t), _busy_end(t)) for t in scoped]
    non_queued = _non_queued(scoped, busy)
    offers = [t for t in non_queued if t.begin_at is None or t.begin_at >= t.request_at]
    return scoped, busy, offers


def _merge(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not windows:
        return []
    ordered = sorted(windows)
    merged = [ordered[0]]
    for s, e in ordered[1:]:
        ls, le = merged[-1]
        if s <= le:
            if e > le:
                merged[-1] = (ls, e)
        else:
            merged.append((s, e))
    return merged


class _Busy:
    """Sorted, non-overlapping busy windows with a bisect-backed membership test —
    the real file has ~218k pings against ~50 trips, so a linear scan per ping
    would be the slow path."""

    def __init__(self, windows: list[tuple[datetime, datetime]]) -> None:
        self._merged = _merge(windows)
        self._starts = [s for s, _ in self._merged]

    def __call__(self, at: datetime) -> bool:
        idx = bisect.bisect_right(self._starts, at) - 1
        return idx >= 0 and self._merged[idx][0] <= at <= self._merged[idx][1]


def _nearest(
    times: list[datetime], lats: list[float], lngs: list[float], at: datetime, max_s: int
) -> tuple[float, float] | None:
    idx = bisect.bisect_left(times, at)
    best: tuple[float, int] | None = None
    for i in (idx - 1, idx):
        if 0 <= i < len(times):
            d = abs((times[i] - at).total_seconds())
            if d <= max_s and (best is None or d < best[0]):
                best = (d, i)
    if best is None:
        return None
    return lats[best[1]], lngs[best[1]]


def _dedup_key(state: str, begin_at: datetime, end_at: datetime, h3_r8: str | None) -> str:
    raw = f"gps|{state}|{begin_at.isoformat()}|{end_at.isoformat()}|{h3_r8 or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


class _Seg:
    __slots__ = ("cell", "begin", "end", "blat", "blng", "elat", "elng")

    def __init__(self, cell: str, at: datetime, lat: float, lng: float) -> None:
        self.cell = cell
        self.begin = at
        self.end = at
        self.blat = lat
        self.blng = lng
        self.elat = lat
        self.elng = lng

    def extend(self, at: datetime, lat: float, lng: float) -> None:
        self.end = at
        self.elat = lat
        self.elng = lng


def _close(seg: _Seg) -> tuple[str, datetime, datetime, float, float, float, float]:
    return (seg.cell, seg.begin, seg.end, seg.blat, seg.blng, seg.elat, seg.elng)


def _open_runs(labelled: list[tuple[datetime, float, float, bool]]):
    """labelled: (at, lat, lng, is_open) sorted by at. Yields (cell, begin, end,
    blat, blng, elat, elng). A new segment starts when the cell changes and the
    driver then dwells ≥ DWELL_S in it (a shorter excursion is absorbed), or when
    the gap since the last ping exceeds GAP_S."""
    cur: _Seg | None = None
    pend: tuple[str, tuple[datetime, float, float], tuple[datetime, float, float] | None] | None
    pend = None
    prev: tuple[datetime, float, float] | None = None
    for at, lat, lng, is_open in labelled:
        if not is_open:
            if cur:
                yield _close(cur)
            cur = pend = None
            prev = None
            continue
        cell = h3.latlng_to_cell(lat, lng, 8)
        if cur is None or (at - cur.end).total_seconds() > GAP_S:
            if cur:
                yield _close(cur)
            cur = _Seg(cell, at, lat, lng)
            pend = None
        elif cell == cur.cell:
            cur.extend(at, lat, lng)
            pend = None
        else:
            if pend is None or pend[0] != cell:
                pend = (cell, (at, lat, lng), prev)
            if (at - pend[1][0]).total_seconds() >= DWELL_S:
                cur.end, cur.elat, cur.elng = pend[2]
                yield _close(cur)
                cur = _Seg(cell, *pend[1])
                cur.extend(at, lat, lng)
                pend = None
            else:
                cur.extend(at, lat, lng)
        prev = (at, lat, lng)
    if cur:
        yield _close(cur)


def _weights(times: list[datetime]) -> list[float]:
    """Each ping's weight is the gap to the next ping in the whole file, capped
    at GAP_S — the last ping (no next one) weighs 0."""
    n = len(times)
    w = [0.0] * n
    for i in range(n - 1):
        w[i] = min((times[i + 1] - times[i]).total_seconds(), GAP_S)
    return w


def _is_home_majority(
    begin_at: datetime,
    end_at: datetime,
    times: list[datetime],
    lats: list[float],
    lngs: list[float],
    weights: list[float],
    home: tuple[float, float] | None,
    home_radius_m: int,
) -> bool:
    """Time-weighted majority (Addendum A, R1): the segment is "home" when at
    least half of its (weighted) time lies within the home radius, not merely
    where it began — a long stationary run inside one oversized H3 cell can
    begin far from home (approaching) and still spend nearly all its time there."""
    if home is None:
        return False
    lo = bisect.bisect_left(times, begin_at)
    hi = bisect.bisect_right(times, end_at)
    total_w = 0.0
    home_w = 0.0
    for i in range(lo, hi):
        w = weights[i]
        total_w += w
        if _haversine_m(lats[i], lngs[i], home[0], home[1]) <= home_radius_m:
            home_w += w
    return total_w > 0 and (home_w / total_w) >= 0.5


def segment_pings(
    pings: list[ParsedPing],
    trips: list[ParsedTrip],
    *,
    home: tuple[float, float] | None,
    home_radius_m: int,
) -> list[ParsedSegment]:
    cov = coverage(pings)
    if cov is None:
        return []
    start, end = cov
    ordered = sorted(pings, key=lambda p: p.at)
    times = [p.at for p in ordered]
    lats = [p.lat for p in ordered]
    lngs = [p.lng for p in ordered]
    weights = _weights(times)

    scoped, busy_windows, offers = _offer_context(trips, start, end)
    is_busy = _Busy(busy_windows)

    out: list[ParsedSegment] = []

    labelled = [(p.at, p.lat, p.lng, p.online and not is_busy(p.at)) for p in ordered]
    for cell, b_at, e_at, blat, blng, elat, elng in _open_runs(labelled):
        zone_key = "home" if _is_home_majority(
            b_at, e_at, times, lats, lngs, weights, home, home_radius_m
        ) else None
        out.append(
            ParsedSegment(
                dedup_key=_dedup_key("open", b_at, e_at, cell),
                state="open",
                begin_at=b_at,
                end_at=e_at,
                begin_lat=blat,
                begin_lng=blng,
                end_lat=elat,
                end_lng=elng,
                h3_r8=cell,
                zone_key=zone_key,
            )
        )

    for t in offers:
        b_at = t.request_at
        e_at = t.begin_at if t.begin_at is not None else b_at + timedelta(seconds=CANCEL_S)
        pos = _nearest(times, lats, lngs, b_at, MATCH_S)
        cell = _cell(*pos) if pos else None
        out.append(
            ParsedSegment(
                dedup_key=_dedup_key("enroute", b_at, e_at, cell),
                state="enroute",
                begin_at=b_at,
                end_at=e_at,
                begin_lat=pos[0] if pos else None,
                begin_lng=pos[1] if pos else None,
                end_lat=pos[0] if pos else None,
                end_lng=pos[1] if pos else None,
                h3_r8=cell,
                zone_key=None,
            )
        )

    for t in scoped:
        if not t.is_completed or t.begin_at is None or t.dropoff_at is None:
            continue
        b_pos = _nearest(times, lats, lngs, t.begin_at, MATCH_S)
        e_pos = _nearest(times, lats, lngs, t.dropoff_at, MATCH_S)
        cell = _cell(*b_pos) if b_pos else None
        out.append(
            ParsedSegment(
                dedup_key=_dedup_key("ontrip", t.begin_at, t.dropoff_at, cell),
                state="ontrip",
                begin_at=t.begin_at,
                end_at=t.dropoff_at,
                begin_lat=b_pos[0] if b_pos else None,
                begin_lng=b_pos[1] if b_pos else None,
                end_lat=e_pos[0] if e_pos else None,
                end_lng=e_pos[1] if e_pos else None,
                h3_r8=cell,
                zone_key=None,
            )
        )

    return out


def locate_trips(
    pings: list[ParsedPing], trips: list[ParsedTrip]
) -> dict[str, tuple[float, float]]:
    ordered = sorted(pings, key=lambda p: p.at)
    times = [p.at for p in ordered]
    lats = [p.lat for p in ordered]
    lngs = [p.lng for p in ordered]
    out: dict[str, tuple[float, float]] = {}
    for t in trips:
        if t.begin_at is None:
            continue
        pos = _nearest(times, lats, lngs, t.begin_at, MATCH_S)
        if pos is not None:
            out[t.dedup_key] = pos
    return out


def request_cells(pings: list[ParsedPing], trips: list[ParsedTrip]) -> list[str]:
    cov = coverage(pings)
    if cov is None:
        return []
    start, end = cov
    ordered = sorted(pings, key=lambda p: p.at)
    times = [p.at for p in ordered]
    lats = [p.lat for p in ordered]
    lngs = [p.lng for p in ordered]

    _, _, offers = _offer_context(trips, start, end)

    out: list[str] = []
    for t in offers:
        if t.product not in ("black", "black_suv"):
            continue
        pos = _nearest(times, lats, lngs, t.request_at, MATCH_S)
        if pos is not None:
            out.append(_cell(*pos))
    return out


def _places(settings: Settings) -> dict[str, tuple[float, float]]:
    places = dict(demand_places.load_geocoded())
    if settings.DEN_LOT_LAT is not None and settings.DEN_LOT_LNG is not None:
        places["DEN Commercial Holding Lot"] = (settings.DEN_LOT_LAT, settings.DEN_LOT_LNG)
    return places


def top_waits(
    open_segments: list[ParsedSegment],
    premium_cells: list[str],
    *,
    places: dict[str, tuple[float, float]],
    home_cell: str | None,
) -> list[dict]:
    minutes: dict[str, float] = {}
    for s in open_segments:
        if s.h3_r8 is None or s.h3_r8 == home_cell:
            continue
        minutes[s.h3_r8] = minutes.get(s.h3_r8, 0.0) + (
            s.end_at - s.begin_at
        ).total_seconds() / 60.0

    premium_counts: dict[str, int] = {}
    for cell in premium_cells:
        premium_counts[cell] = premium_counts.get(cell, 0) + 1

    south, west, north, east = demand_places.METRO_BBOX
    ranked = sorted(minutes.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_WAITS]

    items: list[dict] = []
    for cell, total_minutes in ranked:
        hours = total_minutes / 60.0
        premium_requests = premium_counts.get(cell, 0)
        per_hour = round(premium_requests / hours, 2) if hours > 0 else 0.0
        clat, clng = h3.cell_to_latlng(cell)

        # Same labeller the waiting-spot picker uses, so a cell never gets two names.
        near = demand_places.nearest_place(clat, clng, places, max_km=LABEL_KM)
        place, distance_km = near if near is not None else (None, None)

        zone_key, zone_name = None, None
        for z in demand_places.ZONES:
            d_mi = _haversine_m(clat, clng, z["lat"], z["lng"]) / 1609.344
            if d_mi <= z["radius_mi"]:
                zone_key, zone_name = z["key"], z["name"]
                break

        outside = not (south <= clat <= north and west <= clng <= east)

        items.append(
            {
                "h3_r8": cell,
                "hours": round(hours, 1),
                "premium_requests": premium_requests,
                "per_hour": per_hour,
                "place": place,
                "distance_km": distance_km,
                "zone_key": zone_key,
                "zone_name": zone_name,
                "outside": outside,
            }
        )
    return items


async def import_pings(
    db: AsyncSession, *, tenant_id: int, pings: list[ParsedPing], trips: list[ParsedTrip]
) -> dict | None:
    if not pings:
        return None
    settings = get_settings()
    start, end = coverage(pings)
    home = None
    if settings.DEMAND_HOME_LAT is not None and settings.DEMAND_HOME_LNG is not None:
        home = (settings.DEMAND_HOME_LAT, settings.DEMAND_HOME_LNG)
    segments = segment_pings(pings, trips, home=home, home_radius_m=settings.DEMAND_HOME_RADIUS_M)

    # Replace the window this file covers — and only that window. Bounded on the left
    # alone, uploading an older export after a newer one deleted everything from the
    # older start onward, newer months included, and the older file cannot put them
    # back. Both straddling edges are trimmed instead of dropped; the trailing trim runs
    # before the delete so the rows it saves no longer satisfy `end_at <= end`.
    await db.execute(
        update(DriverStateSegment)
        .where(
            DriverStateSegment.tenant_id == tenant_id,
            DriverStateSegment.source == SegmentSource.GPS,
            DriverStateSegment.begin_at >= start,
            DriverStateSegment.begin_at <= end,
            DriverStateSegment.end_at > end,
        )
        .values(begin_at=end)
    )
    await db.execute(
        delete(DriverStateSegment).where(
            DriverStateSegment.tenant_id == tenant_id,
            DriverStateSegment.source == SegmentSource.GPS,
            DriverStateSegment.begin_at >= start,
            DriverStateSegment.begin_at <= end,
            or_(
                DriverStateSegment.end_at.is_(None),
                DriverStateSegment.end_at <= end,
            ),
        )
    )
    await db.execute(
        update(DriverStateSegment)
        .where(
            DriverStateSegment.tenant_id == tenant_id,
            DriverStateSegment.source == SegmentSource.GPS,
            DriverStateSegment.begin_at < start,
            DriverStateSegment.end_at > start,
        )
        .values(end_at=start)
    )

    seg_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": s.dedup_key,
            "state": EarnerState(s.state),
            "begin_at": s.begin_at,
            "end_at": s.end_at,
            "begin_lat": _round5(s.begin_lat),
            "begin_lng": _round5(s.begin_lng),
            "end_lat": _round5(s.end_lat),
            "end_lng": _round5(s.end_lng),
            "h3_r8": s.h3_r8,
            "zone_key": s.zone_key,
            "source": SegmentSource.GPS,
        }
        for s in segments
    ]
    await _upsert(db, DriverStateSegment, seg_rows, ("tenant_id", "dedup_key"))

    located = locate_trips(pings, trips)
    trips_located = 0
    for dedup_key, (lat, lng) in located.items():
        res = await db.execute(
            update(UberTrip)
            .where(
                UberTrip.tenant_id == tenant_id,
                UberTrip.dedup_key == dedup_key,
                UberTrip.begin_lat.is_(None),
            )
            .values(begin_lat=_round5(lat), begin_lng=_round5(lng))
        )
        trips_located += res.rowcount or 0

    counts = {"open": 0, "enroute": 0, "ontrip": 0}
    for s in segments:
        counts[s.state] += 1

    home_minutes = sum(
        (s.end_at - s.begin_at).total_seconds() / 60.0
        for s in segments
        if s.state == "open" and s.zone_key == "home"
    )
    open_segments = [s for s in segments if s.state == "open" and s.zone_key != "home"]
    home_cell = _cell(*home) if home is not None else None
    waits = top_waits(
        open_segments, request_cells(pings, trips), places=_places(settings), home_cell=home_cell
    )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": math.ceil((end - start).total_seconds() / 86400),
        "pings": len(pings),
        "skipped_rows": 0,
        "segments": counts,
        "trips_located": trips_located,
        "home_hours": round(home_minutes / 60.0, 1),
        "top_waits": waits,
    }
