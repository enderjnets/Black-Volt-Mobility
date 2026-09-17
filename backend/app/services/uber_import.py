"""Uber driver data export → our tables.

The ZIP the owner downloads from Uber ("Request your personal Uber data") has changed
format over the years. Three layouts were seen in real exports (research appendix A):

- 2021 (EU naming): `NN - Driver Lifetime Trips.csv`, `NN - Driver Online Offline.csv`,
  `NN - Driver Dispatches Offered and Accepted.csv`, `;`-delimited.
- 2022 (US): `Trip details (Driver).csv`, `,`-delimited, WITH pickup coordinates and a
  `fare_profile` product column.
- 2025 (US): `driver_lifetime_trips-0.csv`, `,`-delimited, 73 columns, product but NO
  coordinates. Confirmed against the owner's own export (17-Sep-2026): the US ZIP ships
  NO `Driver Online Offline` and NO `Dispatches` file — hence `files_missing` with a
  consequence per file — but it does ship `driver_app_analytics-0.csv` (30 days of
  geolocated app pings with an online flag; not parsed here). In that layout every
  `*_utc` column is a NAIVE timestamp ("2024-12-20 00:16:28") that IS UTC, and the
  matching `*_local` column is the row's `timezone`; `_utc()` below reads `*_utc` as UTC.

`parse_zip` is pure (bytes → dataclasses) and fully unit-tested; `import_export`
(Task 5) does the idempotent upsert. Nothing here executes or writes anything from the
archive: only `.csv` members are read, in memory, under a size cap.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DemandImport,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    SegmentSource,
    UberProduct,
    UberTrip,
)

logger = logging.getLogger("blackvolt.demand.import")

MAX_ZIP_BYTES = 50 * 1024 * 1024

# kind → consequence shown to the owner when the file is absent.
KNOWN_FILES: dict[str, str] = {
    "trips": "No trips file: nothing to learn about your products, hours or airport runs.",
    "online_offline": (
        "Driver Online Offline.csv not present: waiting locations will come only from "
        "your logs and the 30-day GPS file; request a new export monthly."
    ),
    "dispatches": (
        "Dispatches file not present: the hour-of-week offer rate starts from your trips "
        "instead of real offer counts."
    ),
}

_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("online_offline", re.compile(r"driver online offline", re.I)),
    ("dispatches", re.compile(r"dispatches offered and accepted", re.I)),
    (
        "trips",
        re.compile(
            r"(driver lifetime trips|driver_lifetime_trips|trip details \(driver\))", re.I
        ),
    ),
]


class ImportError_(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


@dataclass
class ParsedTrip:
    dedup_key: str
    product: str
    product_raw: str | None
    request_at: datetime | None
    begin_at: datetime | None
    dropoff_at: datetime | None
    begin_lat: float | None
    begin_lng: float | None
    city: str | None
    is_airport: bool
    is_scheduled: bool
    status: str | None
    is_completed: bool
    fare_total: float | None
    surge_multiplier: float | None
    distance_mi: float | None
    duration_s: int | None


@dataclass
class ParsedSegment:
    dedup_key: str
    state: str
    begin_at: datetime
    end_at: datetime | None
    begin_lat: float | None
    begin_lng: float | None
    end_lat: float | None
    end_lng: float | None


@dataclass
class ParsedWindow:
    dedup_key: str
    window_start: datetime
    window_end: datetime
    minutes_online: float
    minutes_active: float
    dispatches: int
    rejections: int
    accepts: int
    expireds: int
    completed_trips: int


@dataclass
class ParsedExport:
    trips: list[ParsedTrip] = field(default_factory=list)
    segments: list[ParsedSegment] = field(default_factory=list)
    windows: list[ParsedWindow] = field(default_factory=list)
    files_found: list[str] = field(default_factory=list)
    files_missing: list[dict] = field(default_factory=list)
    skipped_rows: int = 0


# ── Field helpers ───────────────────────────────────────────────────────────────
def normalize_product(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "other"
    if "suv" in s:
        return "black_suv"
    if "black" in s or "premier" in s:
        return "black"
    if "comfort" in s:
        return "comfort"
    if "xl" in s:
        return "xl"
    if "green" in s:
        return "x"
    if s in {"uberx", "x", "green", "uberx share", "uber x"} or s.startswith("uberx"):
        return "x"
    return "other"


_TS_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S %z UTC",
    "%Y-%m-%d %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_ts(value: str | None, tz_name: str | None = None) -> datetime | None:
    """ISO-ish timestamps from the export. 'Z'/offset → UTC; naive → `tz_name`
    (default America/Denver) then UTC."""
    v = (value or "").strip()
    if not v:
        return None
    for fmt in _TS_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if fmt.endswith("Z") or "%z" in fmt:
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        try:
            tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("America/Denver")
        except Exception:
            tz = ZoneInfo("America/Denver")
        return dt.replace(tzinfo=tz).astimezone(UTC)
    raise ValueError(f"bad timestamp: {v!r}")


def _f(row: dict, *keys: str) -> float | None:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def _i(row: dict, *keys: str) -> int | None:
    v = _f(row, *keys)
    return int(v) if v is not None else None


def _b(row: dict, *keys: str) -> bool:
    for k in keys:
        v = (row.get(k) or "").strip().lower()
        if v:
            return v in {"true", "1", "yes", "t"}
    return False


def _s(row: dict, *keys: str) -> str | None:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return None


def _utc(row: dict, *keys: str) -> datetime | None:
    """`*_utc` columns (and the 2022 `*_time` ones) are UTC even when written without a
    zone; never localize them to the row's `timezone`."""
    return _parse_ts(_s(row, *keys), "UTC")


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def _reader(text: str) -> csv.DictReader:
    head = text.split("\n", 1)[0]
    delim = ";" if head.count(";") > head.count(",") else ","
    return csv.DictReader(io.StringIO(text), delimiter=delim)


# ── Row parsers ─────────────────────────────────────────────────────────────────
def _trip(row: dict) -> ParsedTrip:
    tz = _s(row, "timezone")
    # 2021/2025 layouts carry *_utc; the 2022 layout has request_time etc. in UTC.
    request_at = _utc(row, "request_timestamp_utc", "request_time") or _parse_ts(
        _s(row, "request_timestamp_local"), tz
    )
    begin_at = _utc(row, "begintrip_timestamp_utc", "begintrip_time") or _parse_ts(
        _s(row, "begintrip_timestamp_local"), tz
    )
    dropoff_at = _utc(row, "dropoff_timestamp_utc", "dropoff_time") or _parse_ts(
        _s(row, "dropoff_timestamp_local"), tz
    )
    product_raw = _s(row, "product_type_name", "global_product_name", "fare_profile")
    fare = _f(row, "original_fare_usd", "original_fare_local", "fare")
    distance = _f(row, "trip_distance_miles", "distance")
    duration = _i(row, "trip_duration_seconds", "duration")
    status = _s(row, "status")
    completed_raw = _s(row, "is_completed")
    is_completed = (
        _b(row, "is_completed")
        if completed_raw
        else (status or "").lower() == "completed"
    )
    return ParsedTrip(
        dedup_key=_key(request_at, begin_at, fare, distance),
        product=normalize_product(product_raw),
        product_raw=product_raw[:80] if product_raw else None,
        request_at=request_at,
        begin_at=begin_at,
        dropoff_at=dropoff_at,
        begin_lat=_f(row, "begintrip_latitude"),
        begin_lng=_f(row, "begintrip_longitude"),
        city=(_s(row, "city_name") or None),
        is_airport=_b(row, "is_airport_trip"),
        is_scheduled=_b(row, "is_scheduled_trip"),
        status=status[:30] if status else None,
        is_completed=is_completed,
        fare_total=fare,
        surge_multiplier=_f(row, "surge_multiplier"),
        distance_mi=distance,
        duration_s=duration,
    )


def _segment(row: dict) -> ParsedSegment:
    state = (_s(row, "earner_state") or "").lower()
    if state not in {"open", "enroute", "ontrip", "offline"}:
        raise ValueError(f"unknown earner_state {state!r}")
    begin_at = _utc(row, "begin_timestamp_utc")
    end_at = _utc(row, "end_timestamp_utc")
    if begin_at is None:
        raise ValueError("segment without begin")
    return ParsedSegment(
        dedup_key=_key(state, begin_at, end_at),
        state=state,
        begin_at=begin_at,
        end_at=end_at,
        begin_lat=_f(row, "begin_lat"),
        begin_lng=_f(row, "begin_lng"),
        end_lat=_f(row, "end_lat"),
        end_lng=_f(row, "end_lng"),
    )


def _window(row: dict) -> ParsedWindow:
    start = _utc(row, "start_timestamp_utc")
    end = _utc(row, "end_timestamp_utc")
    if start is None or end is None:
        raise ValueError("window without bounds")
    return ParsedWindow(
        dedup_key=_key(start, end),
        window_start=start,
        window_end=end,
        minutes_online=_f(row, "minutes_online") or 0.0,
        minutes_active=_f(row, "minutes_active") or 0.0,
        dispatches=_i(row, "dispatches") or 0,
        rejections=_i(row, "rejections") or 0,
        accepts=_i(row, "accepts") or 0,
        expireds=_i(row, "expireds") or 0,
        completed_trips=_i(row, "completed_trips") or 0,
    )


def _kind_of(name: str) -> str | None:
    base = name.rsplit("/", 1)[-1]
    if base.startswith("._") or not base.lower().endswith(".csv"):
        return None
    for kind, pat in _KIND_PATTERNS:
        if pat.search(base):
            return kind
    return None


# ── Entry point ─────────────────────────────────────────────────────────────────
def parse_zip(data: bytes) -> ParsedExport:
    if len(data) > MAX_ZIP_BYTES:
        raise ImportError_("too_large")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportError_("not_a_zip") from e
    out = ParsedExport()
    seen_kinds: set[str] = set()
    any_csv = False
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".csv"):
                any_csv = True
            kind = _kind_of(info.filename)
            if kind is None:
                continue
            out.files_found.append(info.filename.rsplit("/", 1)[-1])
            seen_kinds.add(kind)
            text = z.read(info).decode("utf-8-sig", errors="replace")
            parsers = {
                "trips": _trip,
                "online_offline": _segment,
                "dispatches": _window,
            }
            targets = {
                "trips": out.trips,
                "online_offline": out.segments,
                "dispatches": out.windows,
            }
            parser = parsers[kind]
            target = targets[kind]
            for row in _reader(text):
                try:
                    target.append(parser(row))
                except Exception:
                    out.skipped_rows += 1
    if not any_csv:
        raise ImportError_("no_csv")
    for kind, consequence in KNOWN_FILES.items():
        if kind not in seen_kinds:
            out.files_missing.append({"kind": kind, "consequence": consequence})
    return out


# ── Persistence ─────────────────────────────────────────────────────────────────
def _round5(v: float | None) -> float | None:
    return None if v is None else round(v, 5)


async def _upsert(db: AsyncSession, table, rows: list[dict], conflict: tuple[str, ...]) -> int:
    """INSERT … ON CONFLICT DO NOTHING in chunks; returns rows actually inserted."""
    inserted = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        if not chunk:
            continue
        stmt = pg_insert(table).values(chunk).on_conflict_do_nothing(index_elements=list(conflict))
        res = await db.execute(stmt)
        inserted += res.rowcount or 0
    return inserted


async def import_export(db: AsyncSession, *, tenant_id: int, data: bytes) -> dict:
    parsed = parse_zip(data)
    trip_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": t.dedup_key,
            "product": UberProduct(t.product),
            "product_raw": t.product_raw,
            "request_at": t.request_at,
            "begin_at": t.begin_at,
            "dropoff_at": t.dropoff_at,
            "begin_lat": _round5(t.begin_lat),
            "begin_lng": _round5(t.begin_lng),
            "city": t.city,
            "is_airport": t.is_airport,
            "is_scheduled": t.is_scheduled,
            "status": t.status,
            "is_completed": t.is_completed,
            "fare_total": t.fare_total,
            "surge_multiplier": t.surge_multiplier,
            "distance_mi": t.distance_mi,
            "duration_s": t.duration_s,
        }
        for t in parsed.trips
    ]
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
            "h3_r8": _cell(s.begin_lat, s.begin_lng),
            "source": SegmentSource.EXPORT,
        }
        for s in parsed.segments
    ]
    win_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": w.dedup_key,
            "window_start": w.window_start,
            "window_end": w.window_end,
            "minutes_online": w.minutes_online,
            "minutes_active": w.minutes_active,
            "dispatches": w.dispatches,
            "rejections": w.rejections,
            "accepts": w.accepts,
            "expireds": w.expireds,
            "completed_trips": w.completed_trips,
        }
        for w in parsed.windows
    ]
    t_ins = await _upsert(db, UberTrip, trip_rows, ("tenant_id", "dedup_key"))
    s_ins = await _upsert(db, DriverStateSegment, seg_rows, ("tenant_id", "dedup_key"))
    w_ins = await _upsert(db, DispatchWindow, win_rows, ("tenant_id", "dedup_key"))

    dates = [t.begin_at or t.request_at for t in parsed.trips if (t.begin_at or t.request_at)]
    by_product: dict[str, int] = {}
    for t in parsed.trips:
        by_product[t.product] = by_product.get(t.product, 0) + 1
    summary = {
        "files_found": parsed.files_found,
        "files_missing": parsed.files_missing,
        "skipped_rows": parsed.skipped_rows,
        "trips": {
            "inserted": t_ins,
            "skipped": len(trip_rows) - t_ins,
            "date_min": min(dates).isoformat() if dates else None,
            "date_max": max(dates).isoformat() if dates else None,
            "by_product": by_product,
        },
        "segments": {"inserted": s_ins, "skipped": len(seg_rows) - s_ins},
        "windows": {"inserted": w_ins, "skipped": len(win_rows) - w_ins},
    }
    db.add(DemandImport(tenant_id=tenant_id, summary=summary))
    await db.commit()
    return summary


async def last_import(db: AsyncSession, *, tenant_id: int) -> dict | None:
    row = (
        await db.execute(
            select(DemandImport)
            .where(DemandImport.tenant_id == tenant_id)
            .order_by(DemandImport.at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {"at": row.at.isoformat(), **row.summary}


def _cell(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    try:
        import h3

        return h3.latlng_to_cell(lat, lng, 8)
    except Exception:
        return None
