"""Static priors: affluence score, polygon → cells, zone lookup, prior assembly."""
import pytest

from app.services import demand_places as places
from app.services import demand_prior as dp


def test_affluence_score_bounds():
    assert dp.affluence_score(None, None) == 0.0
    assert dp.affluence_score(45000, 0.02) < 0.3
    assert dp.affluence_score(150000, 0.30) == pytest.approx(1.0)
    assert dp.affluence_score(400000, 0.9) == 1.0


def test_cells_for_polygon_covers_a_small_square():
    # ~1.5 km square around Cherry Creek → a handful of res-8 cells (≈0.74 km² each).
    ring = [(39.710, -104.960), (39.710, -104.945), (39.724, -104.945), (39.724, -104.960)]
    cells = dp.cells_for_polygon([ring])
    assert 1 <= len(cells) <= 6
    assert all(len(c) == 15 for c in cells)


def test_zone_for_uses_curated_zones_and_den():
    assert dp.zone_for(39.6425, -104.9550) == "cherry_hills"
    assert dp.zone_for(39.8561, -104.6737) == "den"
    assert dp.zone_for(40.60, -105.10) is None  # Fort Collins: outside every zone


def test_build_priors_counts_places_and_distance():
    ring = [(39.710, -104.960), (39.710, -104.945), (39.724, -104.945), (39.724, -104.960)]
    tracts = [{"income": 150000, "share_200k": 0.30, "rings": [ring]}]
    geocoded = {"Hotel Clio": (39.7176, -104.9532), "Signature APA-South": (39.5700, -104.8500)}
    rows = dp.build_priors(tracts=tracts, places=geocoded)
    assert rows
    cell = next(iter(rows))
    row = rows[cell]
    assert row["affluence"] == pytest.approx(1.0)
    assert row["hotels"] >= 1  # Clio is inside/near the square
    assert row["generators"] == 0  # the FBO is 15+ km away
    assert 15 < row["den_distance_mi"] < 25
    assert row["zone_key"] == "cherry_creek"


def test_curated_lists_have_names_and_addresses():
    for lst in (places.LUXURY_HOTELS, places.FBOS, places.GENERATORS):
        assert lst and all(p["name"] and p["address"] for p in lst)
    assert {z["key"] for z in places.ZONES} >= {"cherry_hills", "greenwood_dtc", "den", "downtown"}


def test_tract_stats_treats_acs_sentinels_as_missing():
    # Normal values: $85k income, 50 of 500 households $200k+.
    income, share = dp._tract_stats("85000", "500", "50")
    assert income == 85000.0
    assert share == pytest.approx(0.1)

    # Income suppressed (-666666666): income is None, share still computes.
    income, share = dp._tract_stats("-666666666", "500", "50")
    assert income is None
    assert share == pytest.approx(0.1)

    # Total suppressed: share can't be computed, even though rich is a number.
    income, share = dp._tract_stats("85000", "-666666666", "50")
    assert income == 85000.0
    assert share is None

    # Both household counts suppressed: no false "100% rich" signal.
    income, share = dp._tract_stats("-666666666", "-666666666", "-666666666")
    assert income is None
    assert share is None

    # Total of zero households: share is None, not a ZeroDivisionError.
    income, share = dp._tract_stats("85000", "0", "0")
    assert income == 85000.0
    assert share is None


def _feature(geoid: str):
    """One TIGERweb GeoJSON polygon, in the shape the service actually returns."""
    return {
        "properties": {"GEOID": geoid},
        "geometry": {
            "type": "Polygon",
            # GeoJSON is (lng, lat); the join flips it.
            "coordinates": [[[-104.960, 39.710], [-104.945, 39.710],
                             [-104.945, 39.724], [-104.960, 39.724]]],
        },
    }


def test_affluence_of_a_real_denver_tract():
    """Tract 1.02, Denver County, ACS 2024: $174,271 median, 708 of 1,691 households
    over $200k. Both halves max out, so this tract is fully affluent. Pinned to real
    numbers because the whole layer read 0.0 in production for months."""
    income, share = dp._tract_stats("174271", "1691", "708")
    assert income == 174271.0
    assert share == pytest.approx(708 / 1691)
    assert dp.affluence_score(income, share) == 1.0


def test_join_tracts_carries_income_onto_the_polygon():
    stats = {"08031000102": (174271.0, 0.42)}
    out = dp._join_tracts([_feature("08031000102")], stats)
    assert len(out) == 1
    assert out[0]["income"] == 174271.0 and out[0]["share_200k"] == 0.42
    # The ring comes back as (lat, lng), which is what cells_for_polygon expects.
    assert out[0]["rings"][0][0] == (39.710, -104.960)


def test_join_tracts_refuses_a_silent_geography_mismatch():
    """The bug this guard exists for: TIGERweb layer 8 returns 12-char block-group ids
    (08031004603'5'), the ACS is keyed by 11-char tract ids, nothing matched, and every
    cell in the metro silently got affluence 0.0 while the build script still reported
    success. A total miss has to be loud."""
    stats = {"08031000102": (174271.0, 0.42)}
    with pytest.raises(RuntimeError) as e:
        dp._join_tracts([_feature("080310046035")], stats)
    msg = str(e.value)
    assert "12 chars" in msg and "11 chars" in msg
    assert "Block Groups" in msg


def test_join_tracts_tolerates_one_tract_the_acs_did_not_return():
    """A partial miss is normal (a tract with no reported income) and must NOT raise —
    only a total miss means the wrong geography."""
    stats = {"08031000102": (174271.0, 0.42)}
    out = dp._join_tracts([_feature("08031000102"), _feature("08031999999")], stats)
    assert len(out) == 2
    assert [r["income"] for r in out] == [174271.0, None]


def test_the_tiger_url_points_at_the_tract_layer():
    """Layer 0 is Census Tracts; layer 8 is Census Block Groups and was the defect."""
    assert dp._TIGER_TRACT_LAYER == 0
    assert dp._TIGER.endswith("Tracts_Blocks/MapServer/0/query")
