"""Flat-rate zone matching: every zone, symmetry, precedence, tricky addresses,
per-tenant price overrides, and the out-of-zone (metered) case.

Pure service test — no DB, no fixtures.
"""

from app.services import zones
from app.services.zones import DEFAULT_ZONE_PRICES, match_zone


def _hit(pickup, dropoff, prices=None):
    return match_zone(pickup, dropoff, prices)


def test_every_zone_matches_its_own_town_from_the_base():
    base = "6000 S Fraser St, Aurora, CO 80016, USA"
    cases = {
        "aspen": "Aspen, CO 81611, USA",
        "vail": "Vail, CO 81657, USA",
        "summit": "Breckenridge, CO 80424, USA",
        "colorado_springs": "Colorado Springs, CO 80903, USA",
        "fort_collins": "Fort Collins, CO 80521, USA",
        "loveland_greeley": "Greeley, CO 80631, USA",
        "boulder": "Boulder, CO 80302, USA",
    }
    for key, dest in cases.items():
        hit = _hit(base, dest)
        assert hit is not None and hit.key == key, dest
        assert hit.flat == DEFAULT_ZONE_PRICES[key]


def test_prices_match_the_owner_map():
    assert DEFAULT_ZONE_PRICES == {
        "aspen": 790.0,
        "vail": 390.0,
        "summit": 349.0,
        "colorado_springs": 359.0,
        "fort_collins": 280.0,
        "loveland_greeley": 249.0,
        "boulder": 190.0,
        "denver_metro": 120.0,
    }


def test_symmetry_either_endpoint():
    a = _hit("Denver, CO, USA", "Aspen, CO, USA")
    b = _hit("Aspen, CO, USA", "Denver, CO, USA")
    assert a and b and a.key == "aspen" and b.key == "aspen"
    assert a.flat == b.flat == 790.0


def test_precedence_farther_zone_beats_metro():
    # Base is in the metro, so origin always carries a metro term; the farther zone must win.
    hit = _hit("Aurora, CO, USA", "Vail, CO 81657, USA")
    assert hit is not None and hit.key == "vail" and hit.flat == 390.0


def test_den_airport_is_metro_120():
    hit = _hit(
        "6000 S Fraser St, Aurora, CO, USA",
        "Denver International Airport (DEN), 8500 Peña Blvd, Denver, CO 80249, USA",
    )
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 120.0


def test_within_metro_local_is_120():
    hit = _hit("Aurora, CO, USA", "Cherry Creek, Denver, CO, USA")
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 120.0


def test_tricky_aspen_grove_is_metro_not_aspen():
    # "Aspen Grove" is a mall in Littleton (metro) — must NOT price as Aspen $790.
    hit = _hit("Aurora, CO, USA", "Aspen Grove, S Broadway, Littleton, CO 80120, USA")
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 120.0


def test_golden_is_metro_not_a_den_substring():
    hit = _hit("Aurora, CO, USA", "Golden, CO 80401, USA")
    assert hit is not None and hit.key == "denver_metro"


def test_out_of_zone_returns_none():
    # Neither endpoint in any zone → metered fare.
    hit = _hit("Grand Junction, CO, USA", "Montrose, CO, USA")
    assert hit is None


def test_comma_less_input_still_matches():
    assert _hit("Aurora CO", "Boulder CO").key == "boulder"


def test_per_tenant_price_override():
    hit = _hit("Denver, CO, USA", "Aspen, CO, USA", prices={"aspen": 850.0})
    assert hit is not None and hit.key == "aspen" and hit.flat == 850.0


def test_override_ignores_unknown_and_bad_values():
    hit = _hit("Denver, CO, USA", "Vail, CO, USA", prices={"vail": "not-a-number"})
    assert hit is not None and hit.key == "vail" and hit.flat == 390.0  # falls back to default


def test_descriptors_cover_all_zones_in_order():
    assert [d["key"] for d in zones.ZONE_DESCRIPTORS] == [z.key for z in zones.ZONES]
    assert zones.ZONE_DESCRIPTORS[-1]["key"] == "denver_metro"  # catch-all last
