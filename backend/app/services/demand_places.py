"""Curated premium-demand generators for the Denver metro. Code constant like
venue_profiles.py: a short list the owner reviews, no per-request cost.

Coordinates come from `data/demand_places.json`, produced once by
`python -m app.scripts.geocode_places` (OpenStreetMap Nominatim, ODbL) — never from
Google Places, whose policy forbids storing anything but place_id.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.services.uber_research import TARGET_ZONES

DEN_TERMINAL = (39.8561, -104.6737)
METRO_BBOX = (39.50, -105.35, 40.10, -104.60)  # south, west, north, east
_DATA = Path(__file__).resolve().parents[2] / "data" / "demand_places.json"

LUXURY_HOTELS: list[dict] = [
    {"name": "Four Seasons Hotel Denver", "address": "1111 14th St, Denver, CO 80202"},
    {"name": "The Ritz-Carlton, Denver", "address": "1881 Curtis St, Denver, CO 80202"},
    {"name": "The Brown Palace Hotel", "address": "321 17th St, Denver, CO 80202"},
    {"name": "The Oxford Hotel", "address": "1600 17th St, Denver, CO 80202"},
    {"name": "The Crawford Hotel", "address": "1701 Wynkoop St, Denver, CO 80202"},
    {"name": "Limelight Hotel Denver", "address": "1600 Wewatta St, Denver, CO 80202"},
    {"name": "Thompson Denver", "address": "1616 Market St, Denver, CO 80202"},
    {"name": "Kimpton Hotel Monaco Denver", "address": "1717 Champa St, Denver, CO 80202"},
    {"name": "Le Méridien Denver Downtown", "address": "1475 California St, Denver, CO 80202"},
    {"name": "Populus", "address": "240 14th St, Denver, CO 80202"},
    {"name": "Hotel Clio", "address": "150 Clayton Ln, Denver, CO 80206"},
    {"name": "Halcyon, a hotel in Cherry Creek", "address": "245 Columbine St, Denver, CO 80206"},
    {"name": "Clayton Hotel & Members Club", "address": "233 Clayton St, Denver, CO 80206"},
    {"name": "Kimpton Claret Hotel", "address": "6985 E Chenango Ave, Denver, CO 80237"},
    {"name": "The Inverness Denver", "address": "200 Inverness Dr W, Englewood, CO 80112"},
    {"name": "Omni Interlocken Hotel", "address": "500 Interlocken Blvd, Broomfield, CO 80021"},
    {"name": "Gaylord Rockies Resort", "address": "6700 N Gaylord Rockies Blvd, Aurora, CO 80019"},
    {"name": "St Julien Hotel & Spa", "address": "900 Walnut St, Boulder, CO 80302"},
]

FBOS: list[dict] = [
    {"name": "Signature APA-South", "address": "Centennial Airport, Englewood, CO"},
    {"name": "Signature APA-North", "address": "7425 S Peoria Cir, Englewood, CO 80112"},
    {"name": "Modern Aviation Centennial", "address": "7800 S Peoria St, Englewood, CO 80112"},
    {"name": "Denver jetCenter", "address": "Centennial Airport, Englewood, CO"},
    {"name": "Signature BJC", "address": "11755 Airport Way, Broomfield, CO 80021"},
    {"name": "Sheltair BJC", "address": "11705 Airport Way, Broomfield, CO 80021"},
    {"name": "Signature Aviation DEN", "address": "7850 N Peña Blvd, Denver, CO 80249"},
]

GENERATORS: list[dict] = [
    {"name": "Cherry Creek Shopping Center", "address": "3000 E 1st Ave, Denver, CO 80206"},
    {"name": "Denver Tech Center", "address": "Denver Tech Center, Greenwood Village, CO"},
    {"name": "Union Station Denver", "address": "1701 Wynkoop St, Denver, CO 80202"},
    {"name": "Colorado Convention Center", "address": "700 14th St, Denver, CO 80202"},
    {"name": "Anschutz Medical Campus", "address": "13001 E 17th Pl, Aurora, CO 80045"},
    {"name": "Cherry Hills Country Club",
     "address": "4125 S University Blvd, Cherry Hills Village, CO 80113"},
    {"name": "Denver Country Club", "address": "1700 E 1st Ave, Denver, CO 80218"},
    {"name": "Belleview Station", "address": "4900 S Newport St, Denver, CO 80237"},
    {"name": "Park Meadows", "address": "Park Meadows Mall, Lone Tree, CO"},
    {"name": "Empower Field at Mile High", "address": "1701 Bryant St, Denver, CO 80204"},
    {"name": "Ball Arena", "address": "1000 Chopper Cir, Denver, CO 80204"},
    {"name": "Coors Field", "address": "2001 Blake St, Denver, CO 80205"},
]

# Zones = the research's affluent origins (uber_research.TARGET_ZONES) + the two
# places the owner actually waits at. radius_mi decides which cells roll up to a zone.
ZONES: list[dict] = [
    {"key": z["key"], "name": z["name"], "lat": z["lat"], "lng": z["lng"], "radius_mi": 2.5}
    for z in TARGET_ZONES
] + [
    {"key": "den", "name": "DEN Airport", "lat": DEN_TERMINAL[0], "lng": DEN_TERMINAL[1],
     "radius_mi": 4.0},
    {"key": "downtown", "name": "Downtown Denver", "lat": 39.7392, "lng": -104.9903,
     "radius_mi": 1.5},
]


def load_geocoded() -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {k: (float(v["lat"]), float(v["lng"])) for k, v in raw.items()}


# ── Geography ───────────────────────────────────────────────────────────────────
# Places are the only thing in this system that can turn a coordinate into a sentence
# a driver understands, so the lookups live beside the list rather than inside whoever
# happens to need them first.

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def places_within(
    lat: float, lng: float, places: dict[str, tuple[float, float]], *, km: float
) -> list[tuple[str, float, float]]:
    """(name, lat, lng) for every curated place within `km`, nearest first."""
    out = [
        (name, plat, plng, haversine_m(lat, lng, plat, plng))
        for name, (plat, plng) in places.items()
        if haversine_m(lat, lng, plat, plng) <= km * 1000.0
    ]
    out.sort(key=lambda t: (t[3], t[0]))
    return [(n, la, ln) for n, la, ln, _ in out]


def nearest_place(
    lat: float, lng: float, places: dict[str, tuple[float, float]], *, max_km: float = 2.0
) -> tuple[str, float] | None:
    """The closest curated place and its distance in km, or None if all are further
    than `max_km`. Past a couple of kilometres a name stops describing where you are."""
    if not places:
        return None
    name, (plat, plng) = min(
        places.items(), key=lambda kv: haversine_m(lat, lng, kv[1][0], kv[1][1])
    )
    d_km = haversine_m(lat, lng, plat, plng) / 1000.0
    return (name, round(d_km, 2)) if d_km <= max_km else None


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """The middle of a small cluster of places.

    A plain mean of lat/lng, not a projected centroid: over the ~1 km cluster this is
    ever asked about, the difference is a few centimetres, and the answer is a kerb to
    wait at rather than a survey marker. Sitting between four hotels beats sitting in
    the doorway of one of them, which is where a "nearest place" answer would park you.
    """
    n = len(points)
    if n == 0:
        raise ValueError("centroid of no points")
    return (round(sum(p[0] for p in points) / n, 6), round(sum(p[1] for p in points) / n, 6))
