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
        "vail": 349.0,
        "summit": 299.0,
        "colorado_springs": 229.0,
        "fort_collins": 199.0,
        "loveland_greeley": 169.0,
        "boulder": 165.0,
        "metro_far": 165.0,
        "metro_mid": 140.0,
        "denver_metro": 110.0,
    }


def test_symmetry_either_endpoint():
    a = _hit("Denver, CO, USA", "Aspen, CO, USA")
    b = _hit("Aspen, CO, USA", "Denver, CO, USA")
    assert a and b and a.key == "aspen" and b.key == "aspen"
    assert a.flat == b.flat == 790.0


def test_precedence_farther_zone_beats_metro():
    # Base is in the metro, so origin always carries a metro term; the farther zone must win.
    hit = _hit("Aurora, CO, USA", "Vail, CO 81657, USA")
    assert hit is not None and hit.key == "vail" and hit.flat == 349.0


def test_den_airport_is_metro_110():
    hit = _hit(
        "6000 S Fraser St, Aurora, CO, USA",
        "Denver International Airport (DEN), 8500 Peña Blvd, Denver, CO 80249, USA",
    )
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 110.0


def test_within_metro_local_is_110():
    hit = _hit("Aurora, CO, USA", "Cherry Creek, Denver, CO, USA")
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 110.0


def test_tricky_aspen_grove_is_metro_not_aspen():
    # "Aspen Grove" is a mall in Littleton (metro) — must NOT price as Aspen $790.
    hit = _hit("Aurora, CO, USA", "Aspen Grove, S Broadway, Littleton, CO 80120, USA")
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 110.0


def test_golden_is_metro_not_a_den_substring():
    # Golden is a mid-ring metro zone (not the close-in denver_metro, and not a "den" match).
    hit = _hit("Aurora, CO, USA", "Golden, CO 80401, USA")
    assert hit is not None and hit.key == "metro_mid"


def test_metro_tiers_by_uber_black_benchmark():
    # Rings follow the Uber Black →DEN benchmark (2026-07), not distance from the base:
    # a town leaves the $110 core only while Black clears ~$140 for its airport run.
    assert _hit("Aurora, CO", "Cherry Hills Village, CO").key == "denver_metro"
    assert _hit("Aurora, CO", "Greenwood Village, CO").key == "denver_metro"  # Black ~$112
    assert _hit("Aurora, CO", "Parker, CO").key == "denver_metro"  # Black ~$123
    assert _hit("Aurora, CO", "Brighton, CO").key == "denver_metro"  # Black ~$87 (near DEN)
    assert _hit("Aurora, CO", "Broomfield, CO").key == "denver_metro"  # Black ~$112
    assert _hit("Aurora, CO", "Highlands Ranch, CO").key == "metro_mid"  # Black ~$162
    assert _hit("Aurora, CO", "Castle Pines, CO").key == "metro_mid"  # Black ~$155
    assert _hit("Aurora, CO", "Morrison, CO").key == "metro_mid"  # Red Rocks town
    assert _hit("Aurora, CO", "Castle Rock, CO").key == "metro_far"  # Black ~$175


def test_dtc_and_lone_tree_are_core():
    # The DTC SEO page advertises the core rate — these terms must stay in denver_metro.
    assert _hit("Denver Tech Center, Greenwood Village, CO", "Denver, CO").key == "denver_metro"
    assert _hit("Aurora, CO", "DTC Blvd, Denver Tech, CO").key == "denver_metro"
    assert _hit("Aurora, CO", "Hyatt Regency, DTC, CO").key == "denver_metro"
    assert _hit("Aurora, CO", "Lone Tree, CO").key == "denver_metro"


def test_base_street_pinned_to_core_regardless_of_city_label():
    # Google labels the base street as Aurora OR Centennial depending on the day; the
    # marker pin must make both price as the core, independent of Centennial's ring.
    for label in ("Aurora", "Centennial"):
        hit = _hit(f"6000 S Fraser St, {label}, CO 80016, USA", "Boulder, CO, USA")
        assert hit is not None and hit.key == "boulder"  # farther zone still wins
        hit = _hit(f"6000 S Fraser St, {label}, CO 80016, USA", "Wash Park, Denver, CO, USA")
        assert hit is not None and hit.key == "denver_metro" and hit.flat == 110.0


def test_base_address_centennial_label_is_core_110():
    # Google formats the Aurora 80016 base as "Centennial, CO" — it must price as the
    # $110 core, not the outer ring (regression: owner's own base→DEN quoted $140).
    hit = _hit(
        "6000 S Fraser St, Centennial, CO 80016, USA",
        "Denver International Airport (DEN), 8500 Peña Blvd, Denver, CO 80249, USA",
    )
    assert hit is not None and hit.key == "denver_metro" and hit.flat == 110.0


def test_far_pickup_beats_close_dropoff():
    # A far-ring pickup to a downtown venue prices at the farther zone (precedence).
    hit = _hit("Castle Rock, CO", "1701 Bryant St, Denver, CO")
    assert hit is not None and hit.key == "metro_far" and hit.flat == 165.0


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
    assert hit is not None and hit.key == "vail" and hit.flat == 349.0  # falls back to default


def test_descriptors_cover_all_zones_in_order():
    assert [d["key"] for d in zones.ZONE_DESCRIPTORS] == [z.key for z in zones.ZONES]
    assert zones.ZONE_DESCRIPTORS[-1]["key"] == "denver_metro"  # catch-all last
