"""Curated venue profiles: watchlist matching, completeness, generic fallback."""

import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

from app.services.venue_profiles import (  # noqa: E402
    VENUE_PROFILES,
    get_profile,
    match_venue_key,
)


def test_watchlist_matching():
    assert match_venue_key("Empower Field at Mile High") == "empower_field"
    assert match_venue_key("Red Rocks Amphitheatre") == "red_rocks"
    assert match_venue_key("Ball Arena") == "ball_arena"
    assert match_venue_key("Coors Field") == "coors_field"
    assert match_venue_key("Fiddler's Green Amphitheatre") == "fiddlers_green"
    assert match_venue_key("Larimer Lounge") is None
    assert match_venue_key("") is None


def test_profiles_complete():
    for key, p in VENUE_PROFILES.items():
        for field in ("name", "address", "coords", "dropoff", "pickup", "eats", "parking_pain"):
            assert p.get(field), f"{key}.{field} missing"
        assert isinstance(p["dropoff"], list) and p["dropoff"]
        assert isinstance(p["pickup"], list) and p["pickup"]
        assert isinstance(p["eats"], list) and p["eats"]
        assert isinstance(p["coords"], tuple) and len(p["coords"]) == 2


def test_generic_fallback():
    assert get_profile("nope")["name"] == "the venue"
    assert get_profile(None)["name"] == "the venue"
    assert get_profile("empower_field")["name"] == "Empower Field at Mile High"
