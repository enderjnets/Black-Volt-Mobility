"""Flat-rate pricing zones. Pure functions, no DB/network — trivially unit-testable.

A trip whose pickup OR dropoff falls in a named zone is charged that zone's FIXED
flat price (consumed by ``pricing.quote`` via ``RouteFacts.zone_flat``). Zones are
matched by city/place name against the address text — the app only ever has address
strings, no lat/lng (see ``services/maps.py``), so this mirrors how ``pricing.
looks_like_airport`` recognises DEN today.

Matching is done against the **city component** of the address (the part just before
the state/zip), NOT the whole string, so a street or POI name never triggers a zone:
``"Aspen Grove, S Broadway, Littleton, CO"`` matches ``littleton`` (Denver metro),
not ``aspen``.

``ZONES`` is ordered most-specific → broadest; the Denver-metro catch-all is **last**
because the base (Aurora, 6000 S Fraser St) is itself in the metro, so nearly every
ride has a metro endpoint and the farther zones must win first. A ride touching
neither the metro nor any named zone → no match → metered fare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    default_flat: float
    terms: tuple[str, ...]


@dataclass(frozen=True)
class ZoneHit:
    key: str
    name: str
    flat: float


# Ordered = precedence (specific → broad). denver_metro MUST stay last (catch-all).
ZONES: tuple[Zone, ...] = (
    Zone("aspen", "Aspen / Snowmass", 790.0, ("aspen", "snowmass")),
    Zone(
        "vail",
        "Vail / Beaver Creek / Eagle",
        390.0,
        ("vail", "beaver creek", "avon", "edwards", "eagle", "eagle-vail", "gypsum", "minturn"),
    ),
    Zone(
        "summit",
        "Summit County",
        349.0,
        (
            "breckenridge",
            "frisco",
            "dillon",
            "silverthorne",
            "keystone",
            "copper mountain",
            "blue river",
        ),
    ),
    Zone(
        "colorado_springs",
        "Colorado Springs",
        359.0,
        (
            "colorado springs",
            "monument",
            "palmer lake",
            "black forest",
            "fountain",
            "manitou springs",
            "security",
            "widefield",
            "fort carson",
            "cimarron hills",
        ),
    ),
    Zone(
        "fort_collins",
        "Fort Collins / Wellington",
        280.0,
        ("fort collins", "wellington", "windsor", "severance", "timnath", "laporte"),
    ),
    Zone(
        "loveland_greeley",
        "Loveland / Greeley",
        249.0,
        ("loveland", "greeley", "johnstown", "berthoud", "evans", "milliken", "kersey"),
    ),
    Zone("boulder", "Boulder", 190.0, ("boulder", "pine brook hill", "gunbarrel")),
    # Outer/far metro rings — priced above the close-in metro to reflect the longer drive.
    # These MUST precede denver_metro so that on a mixed trip (far pickup → downtown venue)
    # the farther pickup zone wins the price.
    Zone(
        "metro_far",
        "Denver metro — far ring",
        165.0,
        ("castle pines", "castle rock", "parker"),
    ),
    Zone(
        "metro_mid",
        "Denver metro — outer / DTC",
        140.0,
        (
            "greenwood village",
            "denver tech",
            "dtc",
            "centennial",
            "highlands ranch",
            "lone tree",
            "golden",
        ),
    ),
    Zone(
        "denver_metro",
        "Denver metro / DEN airport",
        120.0,
        (
            "denver",
            "aurora",
            "glendale",
            "cherry hills",
            "englewood",
            "littleton",
            "lakewood",
            "wheat ridge",
            "arvada",
            "westminster",
            "thornton",
            "northglenn",
            "commerce city",
            "broomfield",
            "louisville",
            "lafayette",
            "superior",
            "morrison",
            "brighton",
            "denver international",
            "dia",
        ),
    ),
)

DEFAULT_ZONE_PRICES: dict[str, float] = {z.key: z.default_flat for z in ZONES}

# Static descriptor list the dashboard renders its Flat-zones editor from.
ZONE_DESCRIPTORS: list[dict] = [
    {"key": z.key, "name": z.name, "default_flat": z.default_flat} for z in ZONES
]

# A trailing "<state>" or "<state> <zip>" component, e.g. "co" or "co 80016".
_STATE_ZIP = re.compile(r"^[a-z]{2}(\s+\d{5}(-\d{4})?)?$")
_COUNTRY = {"usa", "us", "united states"}


def _city(address: str | None) -> str:
    """Best-effort city/locality of an address for zone matching.

    Google-formatted addresses look like ``"<poi/street>, <city>, <STATE> <zip>,
    USA"``. We drop the country and the trailing state/zip component; the last of
    what remains is the city. Falls back to the whole (comma-less) string.
    """
    parts = [p.strip().lower() for p in (address or "").split(",") if p.strip()]
    if parts and parts[-1] in _COUNTRY:
        parts.pop()
    if parts and _STATE_ZIP.match(parts[-1]):
        parts.pop()
    return parts[-1] if parts else ""


def _zone_keys_for(address: str | None) -> set[str]:
    city = _city(address)
    if not city:
        return set()
    hits: set[str] = set()
    for z in ZONES:
        if any(re.search(rf"\b{re.escape(term)}\b", city) for term in z.terms):
            hits.add(z.key)
    return hits


def match_zone(
    pickup: str | None, dropoff: str | None, prices: dict | None = None
) -> ZoneHit | None:
    """First zone (in ``ZONES`` precedence order) whose term matches the city of
    either endpoint. ``prices`` is a per-tenant override map; missing keys fall back
    to ``default_flat``. Returns ``None`` when neither endpoint is in a zone."""
    keys = _zone_keys_for(pickup) | _zone_keys_for(dropoff)
    if not keys:
        return None
    for z in ZONES:  # ZONES order == precedence
        if z.key in keys:
            flat = (prices or {}).get(z.key, z.default_flat)
            try:
                flat = float(flat)
            except (TypeError, ValueError):
                flat = z.default_flat
            return ZoneHit(key=z.key, name=z.name, flat=flat)
    return None
