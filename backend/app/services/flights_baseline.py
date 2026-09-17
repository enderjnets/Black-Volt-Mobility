"""Typical DEN flight banks from BTS On-Time Reporting (free, monthly, ~6-week lag).
Domestic scheduled flights of the large US carriers only — enough for a RELATIVE
hour-of-day multiplier (this hour ÷ the day's mean), which is all Phase 1 uses.
"""
from __future__ import annotations

import csv
import io
import logging
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DenFlightBaseline
from app.services.demand_model import FLIGHT_RANGE, clamp

logger = logging.getLogger("blackvolt.demand.flights")

BTS_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)


def _hour(hhmm: str | None) -> int | None:
    v = (hhmm or "").strip()
    if not v or not v.isdigit():
        return None
    h = int(v) // 100
    return 0 if h == 24 else (h if 0 <= h <= 23 else None)


def bin_rows(rows: Iterable[dict]) -> dict[tuple[int, int, int], dict]:
    counts: dict[tuple[int, int, int], dict] = defaultdict(
        lambda: {"departures": 0.0, "arrivals": 0.0}
    )
    days_seen: dict[tuple[int, int], set[str]] = defaultdict(set)
    for r in rows:
        try:
            d = date.fromisoformat((r.get("FlightDate") or "")[:10])
        except ValueError:
            continue
        key_day = (d.month, d.weekday())
        if r.get("Origin") == "DEN":
            h = _hour(r.get("CRSDepTime"))
            if h is not None:
                counts[(d.month, d.weekday(), h)]["departures"] += 1
                days_seen[key_day].add(d.isoformat())
        if r.get("Dest") == "DEN":
            h = _hour(r.get("CRSArrTime"))
            if h is not None:
                counts[(d.month, d.weekday(), h)]["arrivals"] += 1
                days_seen[key_day].add(d.isoformat())
    out: dict[tuple[int, int, int], dict] = {}
    for (m, dow, h), c in counts.items():
        n = max(1, len(days_seen[(m, dow)]))
        out[(m, dow, h)] = {
            "departures": c["departures"] / n,
            "arrivals": c["arrivals"] / n,
            "days": n,
        }
    return out


def multipliers(baseline: dict[tuple[int, int, int], dict], *, month: int, dow: int) -> list[float]:
    vals = [
        baseline.get((month, dow, h), {}).get("departures", 0.0)
        + baseline.get((month, dow, h), {}).get("arrivals", 0.0)
        for h in range(24)
    ]
    mean = sum(vals) / 24.0
    if mean <= 0:
        return [1.0] * 24
    return [clamp(v / mean, *FLIGHT_RANGE) for v in vals]


def iter_month(year: int, month: int) -> Iterator[dict]:
    """Stream one month of BTS rows (zip ≈ 30 MB) via a temp file; only the five
    columns we need survive."""
    url = BTS_URL.format(year=year, month=month)
    with tempfile.TemporaryFile() as tmp:
        with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                tmp.write(chunk)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                for row in reader:
                    if row.get("Origin") == "DEN" or row.get("Dest") == "DEN":
                        yield {
                            k: row.get(k)
                            for k in ("FlightDate", "Origin", "Dest", "CRSDepTime", "CRSArrTime")
                        }


async def save_baseline(db: AsyncSession, bins: dict, source_period: str) -> int:
    await db.execute(delete(DenFlightBaseline))
    db.add_all(
        DenFlightBaseline(
            month=m, dow=dow, hour=h,
            departures=v["departures"], arrivals=v["arrivals"], source_period=source_period,
        )
        for (m, dow, h), v in bins.items()
    )
    await db.commit()
    return len(bins)


async def load_baseline(db: AsyncSession) -> dict[tuple[int, int, int], dict]:
    rows = (await db.execute(select(DenFlightBaseline))).scalars().all()
    return {
        (r.month, r.dow, r.hour): {"departures": r.departures, "arrivals": r.arrivals, "days": 0}
        for r in rows
    }
