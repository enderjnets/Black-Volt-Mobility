"""Uber driver data export → our tables.

The ZIP the owner downloads from Uber ("Request your personal Uber data") has changed
format over the years. Three layouts were seen in real exports (research appendix A):

- 2021 (EU naming): `NN - Driver Lifetime Trips.csv`, `NN - Driver Online Offline.csv`,
  `NN - Driver Dispatches Offered and Accepted.csv`, `;`-delimited.
- 2022 (US): `Trip details (Driver).csv`, `,`-delimited, WITH pickup coordinates and a
  `fare_profile` product column.
- 2025 (US): `driver_lifetime_trips-0.csv`, `,`-delimited, 73 columns, product but NO
  coordinates. Whether `Driver Online Offline` ships in the US export is unknown until
  the owner's own ZIP arrives — hence `files_missing` with a consequence per file.

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
    request_at = _parse_ts(_s(row, "request_timestamp_utc", "request_time"), tz) or _parse_ts(
        _s(row, "request_timestamp_local"), tz
    )
    begin_at = _parse_ts(_s(row, "begintrip_timestamp_utc", "begintrip_time"), tz) or _parse_ts(
        _s(row, "begintrip_timestamp_local"), tz
    )
    dropoff_at = _parse_ts(_s(row, "dropoff_timestamp_utc", "dropoff_time"), tz) or _parse_ts(
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
    begin_at = _parse_ts(_s(row, "begin_timestamp_utc"))
    end_at = _parse_ts(_s(row, "end_timestamp_utc"))
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
    start = _parse_ts(_s(row, "start_timestamp_utc"))
    end = _parse_ts(_s(row, "end_timestamp_utc"))
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
