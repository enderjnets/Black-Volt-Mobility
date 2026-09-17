"""Pure-math tests for the 'Where to wait' model. No DB, no network."""
import math
from datetime import UTC, date, datetime

import pytest

from app.services import demand_model as dm


def test_hour_of_week_is_denver_local_monday_zero():
    # 2026-09-14 is a Monday. 06:00 UTC = 00:00 MDT.
    assert dm.hour_of_week(datetime(2026, 9, 14, 6, 0, tzinfo=UTC)) == 0
    # Sunday 23:00 MDT = Monday 05:00 UTC.
    assert dm.hour_of_week(datetime(2026, 9, 14, 5, 0, tzinfo=UTC)) == 167


def test_dst_days_have_23_and_25_hours():
    assert len(dm.local_hour_starts(date(2026, 3, 8))) == 23   # spring forward
    assert len(dm.local_hour_starts(date(2026, 11, 1))) == 25  # fall back
    assert len(dm.local_hour_starts(date(2026, 9, 17))) == 24


def test_prior_rate_bounds_and_direction():
    base = 0.03
    flat = dm.prior_rate(base, affluence=0.0, hotels=0, generators=0)
    assert flat == pytest.approx(base * 0.5)  # affluence 0 → ×0.5
    rich = dm.prior_rate(base, affluence=1.0, hotels=6, generators=20)
    assert rich > flat
    # Every multiplier is clamped: absurd inputs cannot explode the rate.
    crazy = dm.prior_rate(base, affluence=99, hotels=999, generators=999,
                          flight_mult=99, event_mult=99, weather_mult=99)
    assert crazy <= base * 2.5 * 2.5 * 2.0 * 3.0 * 3.0 * 1.5 + 1e-9


def test_posterior_with_no_data_is_the_prior():
    e = dm.posterior(prior=0.02, offers=0, exposure_min=0)
    assert e.mean == pytest.approx(0.02)
    assert e.own_share == 0.0
    assert e.lo <= e.mean <= e.hi


def test_posterior_converges_to_observed_rate():
    # 600 offers in 6,000 minutes = 0.1/min, far above a 0.02 prior.
    e = dm.posterior(prior=0.02, offers=600, exposure_min=6000)
    assert abs(e.mean - 0.1) < 0.01
    assert e.own_share > 0.9


def test_ten_minutes_barely_move_the_prior():
    e = dm.posterior(prior=0.02, offers=1, exposure_min=10)
    assert abs(e.mean - 0.02) / 0.02 < 0.10
    assert e.own_share < 0.02


def test_gamma_quantile_orders_and_median_near_mean():
    lo = dm.gamma_quantile(20, 1000, 0.1)
    mid = dm.gamma_quantile(20, 1000, 0.5)
    hi = dm.gamma_quantile(20, 1000, 0.9)
    assert lo < mid < hi
    assert abs(mid - 0.02) / 0.02 < 0.05


def test_p_within():
    assert dm.p_within(0.0) == 0.0
    assert dm.p_within(0.1, 15) == pytest.approx(1 - math.exp(-1.5))


def test_pool_hours_is_circular_and_half_weighted():
    vals = [(0.0, 0.0)] * 168
    vals[0] = (4.0, 100.0)
    pooled = dm.pool_hours(vals)
    assert pooled[0] == (4.0, 100.0)
    assert pooled[1] == (2.0, 50.0)
    assert pooled[167] == (2.0, 50.0)
    assert pooled[2] == (0.0, 0.0)


def _grid(hot: set[int], hot_rate: float = 0.1, cold_rate: float = 0.01) -> list[dm.Estimate]:
    return [
        dm.Estimate(mean=hot_rate if h in hot else cold_rate, lo=0, hi=1, own_share=0.5,
                    offers=0, exposure_min=0)
        for h in range(168)
    ]


def test_top_blocks_respects_min_hours_and_threshold():
    # Tuesday 04-07 (3h) and Friday 20-21 (1h) hot.
    hot = {24 + 4, 24 + 5, 24 + 6, 4 * 24 + 20}
    blocks = dm.top_blocks(_grid(hot), threshold=0.05, min_hours=2)
    assert len(blocks) == 1
    b = blocks[0]
    assert (b.dow, b.start_hour, b.end_hour) == (1, 4, 7)
    assert b.expected_offers == pytest.approx(0.1 * 60 * 3)


def test_top_blocks_default_threshold_is_top_quartile():
    hot = set(range(0, 42))  # 25% of the week hot
    blocks = dm.top_blocks(_grid(hot), min_hours=2, limit=10)
    assert blocks and all(b.mean >= 0.1 for b in blocks)


def test_bridge_rule():
    assert dm.bridge_worth_it(40, 35, here_mean=0.01, dest_mean=0.03)
    assert not dm.bridge_worth_it(30, 35, here_mean=0.01, dest_mean=0.03)  # too cheap
    assert not dm.bridge_worth_it(40, 35, here_mean=0.02, dest_mean=0.025)  # not 1.5× better
    assert not dm.bridge_worth_it(None, 35, here_mean=0.01, dest_mean=0.03)


def test_travel_penalty_fraction():
    assert dm.travel_penalty_fraction(0) == 0.0
    # 10 cells × 531 m = 5.31 km ≈ 3.3 mi at 25 mph ≈ 7.9 min of a 15-min window.
    f = dm.travel_penalty_fraction(10)
    assert 0.5 < f < 0.6
    assert dm.travel_penalty_fraction(100) == 1.0
