"""Maps adapter: route distance/duration + place autocomplete.

Two modes, chosen by `settings.maps_live`:
- **Live** — Google Maps Platform (Distance Matrix + Places Autocomplete) via httpx.
- **Simulated** — deterministic stub routes/suggestions so the booking flow runs
  end-to-end in dev/demo without billing. Same input → same output (hash-based),
  so tests are stable.

NEVER ship simulated mode with APP_ENV=production (see config + main lifespan warn).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

from app.config import get_settings

_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

_METERS_PER_MILE = 1609.344


class MapsError(RuntimeError):
    pass


@dataclass
class RouteResult:
    distance_miles: float
    duration_minutes: float
    simulated: bool


@dataclass
class PlaceSuggestion:
    description: str
    place_id: str | None


def _seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(p.strip().lower() for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _simulate_route(origin: str, destination: str, stops: list[str] | None) -> RouteResult:
    """Deterministic, plausible Denver-metro route. 4–42 mi, ~2.1 min/mi + traffic."""
    s = _seed(origin, destination, *(stops or []))
    miles = round(4 + (s % 3800) / 100.0, 1)  # 4.0 – 42.0
    if stops:
        miles = round(miles + 3.5 * len(stops), 1)
    minutes = round(miles * 2.1 + (s % 13), 1)  # cruise + jitter
    return RouteResult(distance_miles=miles, duration_minutes=minutes, simulated=True)


async def _live_route(origin: str, destination: str, stops: list[str] | None) -> RouteResult:
    settings = get_settings()
    waypoints = "|".join(["via:" + w for w in stops]) if stops else None
    params = {
        "origins": origin,
        "destinations": destination,
        "units": "imperial",
        "key": settings.GOOGLE_MAPS_API_KEY,
    }
    if waypoints:
        # Distance Matrix has no waypoints; approximate by routing origin→dest and
        # adding a per-stop allowance. (Directions API is used for true multi-stop
        # routing in a later iteration.)
        pass
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(_DISTANCE_MATRIX_URL, params=params)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise MapsError(f"distance_matrix:{data.get('status')}")
    try:
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            raise MapsError(f"element:{el.get('status')}")
        miles = round(el["distance"]["value"] / _METERS_PER_MILE, 1)
        minutes = round(el["duration"]["value"] / 60.0, 1)
    except (KeyError, IndexError) as e:
        raise MapsError("distance_matrix:malformed") from e
    if stops:
        miles = round(miles + 3.5 * len(stops), 1)
        minutes = round(minutes + 7.0 * len(stops), 1)
    return RouteResult(distance_miles=miles, duration_minutes=minutes, simulated=False)


async def route(
    origin: str, destination: str, stops: list[str] | None = None
) -> RouteResult:
    """Distance (miles) + duration (minutes) for origin→[stops]→destination."""
    if not origin or not destination:
        raise MapsError("route:missing_endpoint")
    if get_settings().maps_live:
        try:
            return await _live_route(origin, destination, stops)
        except (httpx.HTTPError, MapsError):
            # Fail soft to a simulated route so a transient maps outage never blocks
            # a booking. The result is flagged simulated=True for transparency.
            return _simulate_route(origin, destination, stops)
    return _simulate_route(origin, destination, stops)


_SIM_PLACES = [
    ("Denver International Airport (DEN), Peña Blvd, Denver, CO", "sim_den"),
    ("Union Station, Wynkoop St, Denver, CO", "sim_union"),
    ("The Ritz-Carlton, Curtis St, Denver, CO", "sim_ritz"),
    ("Cherry Creek Shopping Center, Denver, CO", "sim_cherry"),
    ("Boulder, CO", "sim_boulder"),
    ("Aurora, CO", "sim_aurora"),
    ("6000 S Fraser St, Aurora, CO", "sim_fraser"),
]


def _simulate_autocomplete(query: str) -> list[PlaceSuggestion]:
    q = query.strip().lower()
    if not q:
        return []
    hits = [p for p in _SIM_PLACES if any(tok in p[0].lower() for tok in q.split())]
    pool = hits or _SIM_PLACES
    return [PlaceSuggestion(description=d, place_id=pid) for d, pid in pool[:5]]


async def _live_autocomplete(query: str) -> list[PlaceSuggestion]:
    settings = get_settings()
    params = {
        "input": query,
        "key": settings.GOOGLE_MAPS_API_KEY,
        "components": "country:us",
    }
    async with httpx.AsyncClient(timeout=8.0) as http:
        r = await http.get(_AUTOCOMPLETE_URL, params=params)
    r.raise_for_status()
    data = r.json()
    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        raise MapsError(f"autocomplete:{status}")
    return [
        PlaceSuggestion(description=p.get("description", ""), place_id=p.get("place_id"))
        for p in data.get("predictions", [])
    ]


async def autocomplete(query: str) -> list[PlaceSuggestion]:
    """Place suggestions for an address box."""
    if get_settings().maps_live:
        try:
            return await _live_autocomplete(query)
        except (httpx.HTTPError, MapsError):
            return _simulate_autocomplete(query)
    return _simulate_autocomplete(query)
