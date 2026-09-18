"""Where to physically park and wait during a top block.

The Week tab answers *when*. This answers *where to stand*, and that is a different
question with a different failure mode. The best cell by score can be the middle of a
highway — an H3 res-8 cell is a 530 m hexagon and its centre is a point on a map, not a
kerb. The front door of the highest-scoring hotel is somewhere a Black SUV gets moved on
from. So every rule here returns a waiting *area*, triangulated between the places that
make it worth waiting in, rather than a single doorway.

The rules fire in order and the winner reports which one it was, because a driver
deciding whether to trust the suggestion needs to know whether it came from his own
history or from a census table. That distinction is the whole difference between
evidence and assumption, and it belongs on the screen.
"""
from __future__ import annotations

import h3

from app.models import HexPrior
from app.services import demand_model as dm
from app.services import demand_places as dpl

# Places this close to each other are one waiting area you can drive between.
CLUSTER_KM = 1.0
# Past this a place name stops describing where you actually are.
LABEL_KM = 2.0
# Below an hour you have not waited somewhere, you have parked there once. Without this
# a single lucky offer in a cell you passed through would outrank the lot you live in.
MIN_OWN_HOURS = 1.0
# k-ring 2 ≈ 1 km around the venue: close enough that the ping reaches you before the
# rider walks out, far enough that you are not in the queue leaving the garage.
EVENT_RING = 2


def cell_centre(cell: str) -> tuple[float, float]:
    """H3 index → (lat, lng), wrapped because the bare call is easy to get backwards."""
    lat, lng = h3.cell_to_latlng(cell)
    return (lat, lng)


def triangulate(
    lat: float, lng: float, places: dict[str, tuple[float, float]]
) -> tuple[float, float, str | None, list[str]]:
    """Turn a point into somewhere worth sitting, and say what it sits between.

    Two or more curated places within a kilometre are a cluster, and the centre of that
    cluster beats any one of its members: it is walking distance from all of them
    instead of blocking one entrance. A lone place is that place. Nothing nearby leaves
    the point where it was, named by whatever is close enough to mean something, and the
    caller is expected to present that as an area rather than an address.
    """
    near = dpl.places_within(lat, lng, places, km=CLUSTER_KM)
    if len(near) >= 2:
        picked = near[:3]
        clat, clng = dpl.centroid([(la, ln) for _, la, ln in picked])
        return clat, clng, None, [n for n, _, _ in picked]
    if len(near) == 1:
        name, plat, plng = near[0]
        return plat, plng, name, [name]
    label = dpl.nearest_place(lat, lng, places, max_km=LABEL_KM)
    return lat, lng, (label[0] if label else None), []


def _spot(
    lat: float,
    lng: float,
    source: str,
    places: dict[str, tuple[float, float]],
    *,
    venue: str | None = None,
    triangulated: bool = True,
) -> dict:
    if triangulated:
        lat, lng, place, near = triangulate(lat, lng, places)
    else:
        place, near = None, []
    return {
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "source": source,
        "place": place,
        "near": near,
        "venue": venue,
    }


def _best_own_cell(
    cell_ids: set[str], own_by_cell: dict[str, tuple[float, float]]
) -> str | None:
    """The cell where his own waiting has actually paid, or None if none has earned it.

    Ranked by premium offers per open hour, not by hours: sitting somewhere for fifty
    hours proves habit, not demand. The h3 index breaks ties so the answer does not
    wander between recomputes.
    """
    ranked = [
        (offers / (minutes / 60.0), cell)
        for cell, (minutes, offers) in own_by_cell.items()
        if cell in cell_ids and minutes >= MIN_OWN_HOURS * 60.0 and offers > 0
    ]
    if not ranked:
        return None
    return max(ranked, key=lambda t: (t[0], t[1]))[1]


def _best_prior_cell(cells: list[HexPrior]) -> HexPrior | None:
    """The cell the static model likes most — which, now that the census layer works, is
    mostly household income, plus luxury hotels and demand generators nearby."""
    if not cells:
        return None
    return max(
        cells,
        key=lambda c: (
            dm.prior_rate(1.0, affluence=c.affluence, hotels=c.hotels, generators=c.generators),
            c.h3_r8,
        ),
    )


def pick_spot(
    *,
    zone: dict,
    block_events: list[str],
    cells: list[HexPrior],
    own_by_cell: dict[str, tuple[float, float]],
    places: dict[str, tuple[float, float]],
    events: list[dict],
    den_lot: tuple[float, float] | None,
) -> dict | None:
    """Pick one waiting area for one block. First rule that fires wins.

    `own_by_cell` is cell → (open minutes, premium offers) over the whole history, not
    this block's hours: with a few hundred wait segments in total, an hour-restricted
    per-cell count is empty almost everywhere. Whatever renders this must therefore say
    "where you wait in this zone" and must not imply the hours matched.
    """
    cell_ids = {c.h3_r8 for c in cells}

    # 1. An event is the strongest reason a block exists, and the only one that names a
    #    street corner by itself. But not the venue door: no parking, worst traffic, and
    #    the rider is walking out anyway. Sit a ring out, preferring a cell he has
    #    worked before.
    if block_events:
        ev = next(
            (
                e
                for e in events
                if e.get("title") in block_events
                and e.get("lat") is not None
                and e.get("lng") is not None
            ),
            None,
        )
        if ev is not None:
            venue_cell = h3.latlng_to_cell(ev["lat"], ev["lng"], 8)
            ring = h3.grid_disk(venue_cell, EVENT_RING)
            own = _best_own_cell(set(ring) & cell_ids, own_by_cell)
            if own is not None:
                lat, lng = cell_centre(own)
            else:
                known = [c for c in cells if c.h3_r8 in ring]
                best = _best_prior_cell(known)
                lat, lng = cell_centre(best.h3_r8) if best is not None else (ev["lat"], ev["lng"])
            return _spot(lat, lng, "event", places, venue=ev.get("venue_name") or ev.get("title"))

    # 2. The DEN holding lot is exempt from triangulation: it is already a waiting area,
    #    and it is the one coordinate in this system chosen for parking a car rather than
    #    geocoded from a street address.
    if zone.get("key") == "den" and den_lot is not None:
        return _spot(den_lot[0], den_lot[1], "den_lot", places, triangulated=False)

    # 3. His own history beats any model that has never sat in a car.
    own = _best_own_cell(cell_ids, own_by_cell)
    if own is not None:
        lat, lng = cell_centre(own)
        return _spot(lat, lng, "your_data", places)

    # 4. Nothing else to go on: the highest-income part of the zone, which is what the
    #    owner asked for and what the census layer exists to answer.
    best = _best_prior_cell(cells)
    if best is None:
        return None
    lat, lng = cell_centre(best.h3_r8)
    return _spot(lat, lng, "income", places)
