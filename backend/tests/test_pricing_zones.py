"""Fare-engine behaviour for flat-rate zones: a fixed price replaces the metered
calc + floor, peak never applies, and extra-stop / group / discount add-ons still do.
Pure unit tests — no DB, no network.
"""

from datetime import datetime

from app.models.rate_config import RateConfig
from app.services import pricing


def make_rates(**overrides) -> RateConfig:
    rc = RateConfig(
        currency="USD",
        minimum=28.0,
        base=12.0,
        per_mile=2.4,
        per_minute=0.55,
        airport_flat=74.0,
        extra_stop_fee=15.0,
        group_surcharge=20.0,
        group_threshold=4,
        peak_enabled=True,
        peak_multiplier=1.4,
        loyalty_discount_pct=10.0,
    )
    for k, v in overrides.items():
        setattr(rc, k, v)
    return rc


def _zone_facts(**kw):
    base = dict(
        distance_miles=120.0,  # a long route that would meter far above the flat...
        duration_minutes=140.0,
        zone_flat=790.0,
        zone_key="aspen",
        zone_name="Aspen / Snowmass",
    )
    base.update(kw)
    return pricing.RouteFacts(**base)


def test_zone_flat_is_the_exact_total_ignoring_meter():
    q = pricing.quote(make_rates(), _zone_facts())
    assert q["total"] == 790.0
    assert q["zone"] == "aspen"
    assert q["zone_name"] == "Aspen / Snowmass"
    assert q["is_airport"] is False
    labels = [ln["label"] for ln in q["lines"]]
    assert labels == ["zone_flat"]  # no base/distance/time/minimum lines
    assert q["lines"][0]["amount"] == 790.0


def test_zone_flat_ignores_peak_even_on_weekend_night():
    # Sat 23:30 → is_peak_time True, peak_enabled True, but a fixed zone price stays fixed.
    sat_night = datetime(2026, 7, 4, 23, 30)
    q = pricing.quote(make_rates(), _zone_facts(scheduled_at=sat_night))
    assert q["is_peak"] is False
    assert q["total"] == 790.0
    assert all(ln["label"] != "peak" for ln in q["lines"])


def test_zone_flat_still_takes_explicit_peak_override_as_no_op():
    q = pricing.quote(make_rates(), _zone_facts(is_peak=True))
    assert q["is_peak"] is False
    assert q["total"] == 790.0


def test_zone_flat_plus_extra_stops_and_group_and_discount():
    q = pricing.quote(
        make_rates(),
        _zone_facts(extra_stops=2, pax=5, discount_pct=10.0),
    )
    # 790 + 2*15 (stops) + 20 (group, pax 5 > threshold 4) = 840; then -10% = 756.
    assert any(ln["label"] == "extra_stops" and ln["amount"] == 30.0 for ln in q["lines"])
    assert any(ln["label"] == "group_surcharge" and ln["amount"] == 20.0 for ln in q["lines"])
    assert any(ln["label"] == "discount_code" and ln["amount"] == -84.0 for ln in q["lines"])
    assert q["total"] == 756.0


def test_zone_flat_applies_loyalty_discount():
    q = pricing.quote(make_rates(), _zone_facts(is_loyalty=True))
    # 790 - 10% loyalty = 711.
    assert any(ln["label"] == "loyalty_discount" for ln in q["lines"])
    assert q["total"] == 711.0


def test_metered_path_unchanged_when_no_zone():
    q = pricing.quote(
        make_rates(),
        pricing.RouteFacts(distance_miles=18.4, duration_minutes=28),
    )
    assert q["total"] == 71.56  # 12 + 44.16 + 15.4
    assert q["zone"] is None
    assert q["zone_name"] is None
