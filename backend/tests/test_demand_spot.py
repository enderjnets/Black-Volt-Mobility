"""Where to park during a block. Pure — no DB, no network.

Every assertion here is about a claim a driver will act on by driving somewhere, so the
cases are written as the wrong answers we are trying to avoid: the venue doorway, the
hotel entrance, the cell he drove through once, the middle of a hexagon.
"""
import h3
import pytest

from app.models import HexPrior
from app.services import demand_places as dpl
from app.services import demand_spot as ds

# Real coordinates, because h3 cell membership is the thing under test.
UNION_STATION = (39.7527, -104.9998)
OXFORD_HOTEL = (39.7534, -105.0000)
KIMPTON_MONACO = (39.7466, -104.9958)
COORS_FIELD = (39.7559, -104.9942)
CHERRY_CREEK = (39.7170, -104.9530)
DEN_LOT = (39.8399691, -104.6698651)

LODO_PLACES = {
    "The Oxford Hotel": OXFORD_HOTEL,
    "Kimpton Hotel Monaco Denver": KIMPTON_MONACO,
    "Union Station": UNION_STATION,
}


def _cell(lat: float, lng: float) -> str:
    return h3.latlng_to_cell(lat, lng, 8)


def _prior(lat: float, lng: float, *, affluence=0.0, hotels=0, generators=0) -> HexPrior:
    return HexPrior(
        h3_r8=_cell(lat, lng), affluence=affluence, hotels=hotels,
        generators=generators, den_distance_mi=10.0, zone_key="lodo",
    )


def _zone(key="lodo"):
    return {"key": key, "name": "LoDo / Union Station", "lat": UNION_STATION[0],
            "lng": UNION_STATION[1], "radius_mi": 2.5}


# ── triangulate ─────────────────────────────────────────────────────────────────

def test_a_cluster_returns_the_middle_not_a_doorway():
    """Three hotels within a kilometre: the answer is the point among them. Sitting at
    the centre is walking distance from all three; sitting at the nearest one is
    blocking an entrance."""
    lat, lng, place, near = ds.triangulate(*UNION_STATION, LODO_PLACES)
    assert len(near) >= 2
    assert place is None  # a cluster has no single name
    # Strictly inside the cluster's bounding box, and not equal to any member.
    lats = [p[0] for p in LODO_PLACES.values()]
    lngs = [p[1] for p in LODO_PLACES.values()]
    assert min(lats) <= lat <= max(lats)
    assert min(lngs) <= lng <= max(lngs)
    assert (lat, lng) not in {(round(a, 6), round(b, 6)) for a, b in LODO_PLACES.values()}


def test_a_lone_place_is_that_place():
    only = {"Kimpton Hotel Monaco Denver": KIMPTON_MONACO}
    lat, lng, place, near = ds.triangulate(*KIMPTON_MONACO, only)
    assert (lat, lng) == KIMPTON_MONACO
    assert place == "Kimpton Hotel Monaco Denver"
    assert near == ["Kimpton Hotel Monaco Denver"]


def test_nothing_nearby_keeps_the_point_and_admits_it_has_no_name():
    far = {"Four Seasons Hotel Denver": (39.7486, -104.9962)}
    lat, lng, place, near = ds.triangulate(40.05, -105.30, far)  # up by Boulder
    assert (lat, lng) == (40.05, -105.30)
    assert place is None and near == []


# ── the rules, in order ─────────────────────────────────────────────────────────

def test_an_event_block_waits_near_the_venue_not_at_its_door():
    """A Black SUV at the stadium entrance is in the worst traffic in the city with
    nowhere to stop. The spot has to be a ring out, and it has to name the venue so the
    driver knows why he is being sent there."""
    events = [{"title": "Colorado Rockies vs. Seattle Mariners", "venue_name": "Coors Field",
               "lat": COORS_FIELD[0], "lng": COORS_FIELD[1]}]
    neighbour = h3.grid_ring(_cell(*COORS_FIELD), 1).pop()
    nlat, nlng = h3.cell_to_latlng(neighbour)
    cells = [HexPrior(h3_r8=neighbour, affluence=0.9, hotels=3, generators=1,
                      den_distance_mi=18.0, zone_key="lodo")]

    spot = ds.pick_spot(
        zone=_zone(), block_events=["Colorado Rockies vs. Seattle Mariners"],
        cells=cells, own_by_cell={}, places=LODO_PLACES, events=events, den_lot=DEN_LOT,
    )
    assert spot["source"] == "event"
    assert spot["venue"] == "Coors Field"
    assert (spot["lat"], spot["lng"]) != COORS_FIELD
    assert dpl.haversine_m(spot["lat"], spot["lng"], *COORS_FIELD) < 2500


def test_an_event_the_block_does_not_name_is_not_used():
    """block_events comes from the block's own reasons. An event in the table that did
    not lift this block must not hijack its destination."""
    events = [{"title": "Some other night", "venue_name": "Ball Arena",
               "lat": 39.7487, "lng": -105.0077}]
    cells = [_prior(*CHERRY_CREEK, affluence=0.8)]
    spot = ds.pick_spot(
        zone=_zone(), block_events=["Colorado Rockies vs. Seattle Mariners"],
        cells=cells, own_by_cell={}, places={}, events=events, den_lot=None,
    )
    assert spot["source"] == "income"


def test_den_sends_him_to_the_holding_lot_untriangulated():
    """The lot is already a waiting area and the only coordinate here that was chosen
    for parking a car. Triangulating it toward a terminal would be a downgrade."""
    spot = ds.pick_spot(
        zone={"key": "den", "name": "DEN Airport", "lat": 39.8561, "lng": -104.6737,
              "radius_mi": 4.0},
        block_events=[], cells=[_prior(*CHERRY_CREEK, affluence=1.0)],
        own_by_cell={}, places=LODO_PLACES, events=[], den_lot=DEN_LOT,
    )
    assert spot["source"] == "den_lot"
    # 6 dp is ~11 cm; the lot is stored with 7. Compare at the precision that matters
    # for driving to it, not at the precision the owner happened to paste.
    assert spot["lat"] == pytest.approx(DEN_LOT[0], abs=1e-6)
    assert spot["lng"] == pytest.approx(DEN_LOT[1], abs=1e-6)
    assert spot["place"] is None and spot["near"] == []


def test_his_own_history_outranks_the_model():
    rich = _prior(*CHERRY_CREEK, affluence=1.0, hotels=5)
    worked = _prior(*KIMPTON_MONACO, affluence=0.0)
    spot = ds.pick_spot(
        zone=_zone(), block_events=[], cells=[rich, worked],
        own_by_cell={worked.h3_r8: (600.0, 8.0)},  # 10 h, 8 premium offers
        places={}, events=[], den_lot=None,
    )
    assert spot["source"] == "your_data"
    assert _cell(spot["lat"], spot["lng"]) == worked.h3_r8


def test_one_lucky_offer_in_a_cell_he_drove_through_does_not_win():
    """Without the exposure floor, a cell with a single offer and twenty minutes shows
    an unbeatable offers-per-hour and outranks the place he actually works."""
    passed_through = _prior(*OXFORD_HOTEL)
    spot = ds.pick_spot(
        zone=_zone(), block_events=[],
        cells=[passed_through, _prior(*CHERRY_CREEK, affluence=1.0)],
        own_by_cell={passed_through.h3_r8: (20.0, 1.0)},  # 20 minutes
        places={}, events=[], den_lot=None,
    )
    assert spot["source"] == "income"


def test_the_last_resort_is_the_highest_income_cell():
    """What the owner asked for when nothing else distinguishes a corner: the part of
    the zone where the people who live there earn the most."""
    poor = _prior(*OXFORD_HOTEL, affluence=0.0)
    rich = _prior(*CHERRY_CREEK, affluence=1.0)
    spot = ds.pick_spot(
        zone=_zone(), block_events=[], cells=[poor, rich],
        own_by_cell={}, places={}, events=[], den_lot=None,
    )
    assert spot["source"] == "income"
    assert _cell(spot["lat"], spot["lng"]) == rich.h3_r8


def test_a_zone_with_no_cells_gets_no_spot():
    """Same rule as everywhere else in this feature: when there is nothing to say, the
    screen says nothing rather than inventing a corner."""
    assert ds.pick_spot(
        zone=_zone(), block_events=[], cells=[], own_by_cell={},
        places=LODO_PLACES, events=[], den_lot=None,
    ) is None


def test_the_income_winner_is_stable_between_runs():
    """Ties broken by the h3 index, so the suggestion does not wander hourly."""
    a = _prior(*OXFORD_HOTEL, affluence=0.5)
    b = _prior(*KIMPTON_MONACO, affluence=0.5)
    first = ds.pick_spot(zone=_zone(), block_events=[], cells=[a, b], own_by_cell={},
                         places={}, events=[], den_lot=None)
    second = ds.pick_spot(zone=_zone(), block_events=[], cells=[b, a], own_by_cell={},
                          places={}, events=[], den_lot=None)
    assert (first["lat"], first["lng"]) == (second["lat"], second["lng"])


# ── the geography helpers this rests on ─────────────────────────────────────────

def test_nearest_place_refuses_a_name_that_is_too_far_to_mean_anything():
    assert dpl.nearest_place(*UNION_STATION, LODO_PLACES, max_km=2.0) is not None
    assert dpl.nearest_place(40.05, -105.30, LODO_PLACES, max_km=2.0) is None


def test_centroid_of_two_points_is_between_them():
    lat, lng = dpl.centroid([UNION_STATION, KIMPTON_MONACO])
    assert min(UNION_STATION[0], KIMPTON_MONACO[0]) < lat < max(UNION_STATION[0], KIMPTON_MONACO[0])
    assert lng == pytest.approx((UNION_STATION[1] + KIMPTON_MONACO[1]) / 2, abs=1e-6)
