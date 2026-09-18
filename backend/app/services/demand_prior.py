"""Static per-cell priors: where the money lives (Census ACS), where it sleeps
(luxury hotels), what generates premium trips (FBOs, offices, venues) and how far
DEN is. Rebuilt by `app.scripts.build_demand_priors`; read by demand.py.
"""
from __future__ import annotations

import logging
import math

import h3
import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import HexPrior
from app.services import demand_places as dpl

logger = logging.getLogger("blackvolt.demand.prior")

# Denver metro counties (FIPS): Adams, Arapahoe, Boulder, Broomfield, Denver, Douglas, Jefferson.
METRO_COUNTIES = ["001", "005", "013", "014", "031", "035", "059"]
_CENSUS = "https://api.census.gov/data/2024/acs/acs5"
_VARS = "NAME,B19013_001E,B19001_001E,B19001_017E"
_HOTEL_RING = 2      # res-8 k-ring 2 ≈ 1 km
_GENERATOR_RING = 3  # ≈ 1.5 km


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def affluence_score(median_income: float | None, share_200k: float | None) -> float:
    """0..1. Median income of $150k or a 30% share of $200k+ households each count as
    'fully affluent'; the two halves add."""
    inc = clamp01((median_income or 0.0) / 150000.0)
    share = clamp01((share_200k or 0.0) / 0.30)
    return clamp01(0.5 * inc + 0.5 * share)


def cells_for_polygon(rings: list[list[tuple[float, float]]]) -> set[str]:
    """Rings are lists of (lat, lng); first = outer, rest = holes."""
    outer, holes = rings[0], rings[1:]
    poly = h3.LatLngPoly(outer, *holes)
    return set(h3.polygon_to_cells(poly, 8))


def _miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def zone_for(lat: float, lng: float) -> str | None:
    best, best_d = None, 1e9
    for z in dpl.ZONES:
        d = _miles(lat, lng, z["lat"], z["lng"])
        if d <= z["radius_mi"] and d < best_d:
            best, best_d = z["key"], d
    return best


def build_priors(
    *, tracts: list[dict], places: dict[str, tuple[float, float]]
) -> dict[str, dict]:
    """Pure assembly. `tracts`: [{"income", "share_200k", "rings"}]. `places`: name → (lat, lng)."""
    rows: dict[str, dict] = {}
    for t in tracts:
        score = affluence_score(t.get("income"), t.get("share_200k"))
        for cell in cells_for_polygon(t["rings"]):
            rows[cell] = {"affluence": score, "hotels": 0, "generators": 0}
    hotel_names = {p["name"] for p in dpl.LUXURY_HOTELS}
    for name, (lat, lng) in places.items():
        centre = h3.latlng_to_cell(lat, lng, 8)
        is_hotel = name in hotel_names
        ring = _HOTEL_RING if is_hotel else _GENERATOR_RING
        for cell in h3.grid_disk(centre, ring):
            row = rows.setdefault(cell, {"affluence": 0.0, "hotels": 0, "generators": 0})
            row["hotels" if is_hotel else "generators"] += 1
    for cell, row in rows.items():
        lat, lng = h3.cell_to_latlng(cell)
        row["den_distance_mi"] = round(_miles(lat, lng, *dpl.DEN_TERMINAL), 2)
        row["zone_key"] = zone_for(lat, lng)
    return rows


def _num(v: str | float | None) -> float | None:
    """Census ACS cells use large negative sentinels (e.g. -666666666) for
    'not computed'/suppressed values; treat those and blanks as missing."""
    if v in (None, ""):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n < 0 else n


def _tract_stats(
    raw_income: str | float | None,
    raw_total: str | float | None,
    raw_rich: str | float | None,
) -> tuple[float | None, float | None]:
    """(income, share_200k) from one ACS row's raw cell values, sentinel-safe."""
    income = _num(raw_income)
    total = _num(raw_total)
    rich = _num(raw_rich)
    share = (rich / total) if (total and rich is not None) else None
    return income, share


async def fetch_census(counties: list[str] | None = None) -> list[dict]:
    """ACS 5-year 2020-2024 tract rows + TIGERweb tract polygons for the metro counties.
    Returns [{"geoid", "income", "share_200k", "rings"}]. Needs CENSUS_API_KEY."""
    key = get_settings().CENSUS_API_KEY
    if not key:
        raise RuntimeError("CENSUS_API_KEY is not set")
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0) as http:
        for county in counties or METRO_COUNTIES:
            r = await http.get(
                _CENSUS,
                params={
                    "get": _VARS,
                    "for": "tract:*",
                    "in": f"state:08 county:{county}",
                    "key": key,
                },
            )
            r.raise_for_status()
            header, *data = r.json()
            idx = {h: i for i, h in enumerate(header)}
            stats: dict[str, tuple[float | None, float | None]] = {}
            for row in data:
                geoid = f"08{row[idx['county']]}{row[idx['tract']]}"
                stats[geoid] = _tract_stats(
                    row[idx["B19013_001E"]], row[idx["B19001_001E"]], row[idx["B19001_017E"]]
                )
            g = await http.get(
                "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
                "Tracts_Blocks/MapServer/8/query",
                params={
                    "where": f"STATE='08' AND COUNTY='{county}'",
                    "outFields": "GEOID",
                    "f": "geojson",
                    "outSR": "4326",
                },
            )
            g.raise_for_status()
            for feat in g.json().get("features", []):
                geoid = feat["properties"]["GEOID"]
                geom = feat["geometry"]
                polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
                inc, share = stats.get(geoid, (None, None))
                for poly in polys:
                    rings = [[(lat, lng) for lng, lat in ring] for ring in poly]
                    out.append({"geoid": geoid, "income": inc, "share_200k": share, "rings": rings})
    return out


async def save_priors(db: AsyncSession, rows: dict[str, dict]) -> int:
    await db.execute(delete(HexPrior))
    db.add_all(
        HexPrior(
            h3_r8=cell,
            affluence=r["affluence"],
            hotels=r["hotels"],
            generators=r["generators"],
            den_distance_mi=r["den_distance_mi"],
            zone_key=r["zone_key"],
        )
        for cell, r in rows.items()
    )
    await db.commit()
    return len(rows)
