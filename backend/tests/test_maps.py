"""Maps adapter — simulated mode (deterministic, no network)."""
import os

os.environ["MAPS_SIMULATED"] = "true"

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.services import maps  # noqa: E402


@pytest.mark.asyncio
async def test_route_is_deterministic():
    a = await maps.route("Downtown Denver", "Denver Intl (DEN)")
    b = await maps.route("Downtown Denver", "Denver Intl (DEN)")
    assert a.distance_miles == b.distance_miles
    assert a.duration_minutes == b.duration_minutes
    assert a.simulated is True
    assert 4.0 <= a.distance_miles <= 60.0
    assert a.duration_minutes > 0


@pytest.mark.asyncio
async def test_route_varies_by_endpoints():
    a = await maps.route("Aurora", "Boulder")
    b = await maps.route("Cherry Creek", "Union Station")
    assert (a.distance_miles, a.duration_minutes) != (b.distance_miles, b.duration_minutes)


@pytest.mark.asyncio
async def test_stops_increase_distance():
    direct = await maps.route("Aurora", "Boulder")
    with_stop = await maps.route("Aurora", "Boulder", stops=["Union Station"])
    assert with_stop.distance_miles > direct.distance_miles


@pytest.mark.asyncio
async def test_autocomplete_matches_query():
    out = await maps.autocomplete("denver airport")
    assert out
    assert any("DEN" in s.description or "Denver" in s.description for s in out)


@pytest.mark.asyncio
async def test_missing_endpoint_raises():
    with pytest.raises(maps.MapsError):
        await maps.route("", "Boulder")
