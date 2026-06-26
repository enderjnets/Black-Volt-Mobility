"""Pure unit tests for the fare engine — no DB, no network."""
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


def test_metered_above_minimum():
    rc = make_rates()
    q = pricing.quote(rc, pricing.RouteFacts(distance_miles=18.4, duration_minutes=28))
    # 12 + 18.4*2.4 (44.16) + 28*0.55 (15.4) = 71.56, above minimum 28.
    assert q["total"] == 71.56
    assert q["is_airport"] is False


def test_minimum_floor_applies_on_short_trip():
    rc = make_rates()
    q = pricing.quote(rc, pricing.RouteFacts(distance_miles=1.0, duration_minutes=4))
    # metered = 12 + 2.4 + 2.2 = 16.6 → floored up to minimum 28.
    assert q["total"] == 28.0
    assert any(line["label"] == "minimum" for line in q["lines"])


def test_airport_flat_floor():
    rc = make_rates()
    q = pricing.quote(
        rc, pricing.RouteFacts(distance_miles=5.0, duration_minutes=12, is_airport=True)
    )
    # metered = 12 + 12 + 6.6 = 30.6 → floored to airport_flat 74.
    assert q["total"] == 74.0
    assert q["is_airport"] is True
    assert any(line["label"] == "airport_flat" for line in q["lines"])


def test_extra_stops_and_group_surcharge():
    rc = make_rates()
    q = pricing.quote(
        rc,
        pricing.RouteFacts(
            distance_miles=18.4, duration_minutes=28, pax=6, extra_stops=1
        ),
    )
    # 71.56 + 15 (one extra stop) + 20 (pax 6 > 4) = 106.56
    assert q["total"] == 106.56


def test_peak_multiplier():
    rc = make_rates()
    q = pricing.quote(
        rc, pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, is_peak=True)
    )
    # 71.56 * 1.4 = 100.18 (rounded)
    assert q["total"] == 100.18
    assert q["is_peak"] is True


def test_peak_disabled_in_config():
    rc = make_rates(peak_enabled=False)
    q = pricing.quote(
        rc, pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, is_peak=True)
    )
    assert q["total"] == 71.56
    assert q["is_peak"] is False


def test_loyalty_discount():
    rc = make_rates()
    q = pricing.quote(
        rc, pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, is_loyalty=True)
    )
    # 71.56 - 10% (7.16) = 64.40
    assert q["total"] == 64.4


def test_is_peak_time_weekend_late():
    fri_late = datetime(2026, 6, 5, 23, 30)  # Friday 23:30
    tue_late = datetime(2026, 6, 2, 23, 30)  # Tuesday 23:30
    assert pricing.is_peak_time(fri_late) is True
    assert pricing.is_peak_time(tue_late) is False
    assert pricing.is_peak_time(None) is False


def test_looks_like_airport():
    assert pricing.looks_like_airport("Downtown Denver", "Denver Intl (DEN)") is True
    assert pricing.looks_like_airport("Cherry Creek", "Union Station") is False


def test_discount_code_overrides_loyalty():
    # When both is_loyalty and discount_pct are set, only discount_code applies (no stacking).
    rc = make_rates()  # loyalty_discount_pct=10.0
    q = pricing.quote(
        rc,
        pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, is_loyalty=True, discount_pct=15.0),
    )
    # subtotal=71.56; code discount=71.56*15/100=10.73; total=60.83
    labels = [line["label"] for line in q["lines"]]
    assert "discount_code" in labels
    assert "loyalty_discount" not in labels
    discount_line = next(line for line in q["lines"] if line["label"] == "discount_code")
    assert discount_line["amount"] == -10.73
    assert discount_line["pct"] == 15.0
    assert q["total"] == 60.83


def test_discount_code_alone_no_loyalty():
    rc = make_rates()
    q = pricing.quote(
        rc,
        pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, discount_pct=10.0),
    )
    labels = [line["label"] for line in q["lines"]]
    assert "discount_code" in labels
    assert "loyalty_discount" not in labels
    assert q["total"] == 64.4  # same math as loyalty at 10%, confirming parity


def test_discount_code_zero_falls_through_to_loyalty():
    rc = make_rates()
    q = pricing.quote(
        rc,
        pricing.RouteFacts(distance_miles=18.4, duration_minutes=28, is_loyalty=True, discount_pct=0.0),
    )
    labels = [line["label"] for line in q["lines"]]
    assert "loyalty_discount" in labels
    assert "discount_code" not in labels
