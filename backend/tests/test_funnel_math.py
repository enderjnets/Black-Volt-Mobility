"""Unit tests for the pure funnel math (no DB, no framework)."""
from app.services import funnel_math as fm


def test_zero_data_uses_neutral_prior():
    r = fm.smoothed_rate(0, 0)
    # Beta(1,1) prior with no data → 0.5, flagged low-data, full-width band.
    assert r.point == 0.5
    assert r.low_data is True
    assert r.low == 0.0 and r.high == 1.0


def test_one_of_one_is_not_one_hundred_percent():
    r = fm.smoothed_rate(1, 1)
    # Raw rate is 100%; smoothing pulls it well below 1 and flags low-data.
    assert 0.5 < r.point < 1.0
    assert r.low_data is True


def test_successes_capped_at_trials():
    r = fm.smoothed_rate(10, 3)  # nonsensical input
    assert r.num == 3 and r.den == 3


def test_wilson_interval_brackets_point_with_more_data():
    r = fm.smoothed_rate(50, 100)
    assert r.low < 0.5 < r.high
    assert r.low_data is False
    # Tighter band than a tiny sample.
    tiny = fm.smoothed_rate(1, 2)
    assert (r.high - r.low) < (tiny.high - tiny.low)


def test_overall_rate_is_product_of_stages():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=20, clients=10)
    expected = rates.pitch.point * rates.contact.point * rates.convert.point
    assert abs(rates.overall_point - expected) < 1e-12
    assert rates.overall_low <= rates.overall_point <= rates.overall_high


def test_projection_scales_with_effort():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=25, clients=10)
    p1 = fm.project(rates=rates, conversations_per_day=10, working_days=5, revenue_per_client=200)
    p2 = fm.project(rates=rates, conversations_per_day=20, working_days=5, revenue_per_client=200)
    # Double the conversations → double the expected clients/revenue.
    assert abs(p2.expected_clients - 2 * p1.expected_clients) < 1e-9
    assert abs(p2.expected_revenue - 2 * p1.expected_revenue) < 1e-9
    assert p1.expected_revenue == p1.expected_clients * 200
    assert p1.expected_clients_low <= p1.expected_clients <= p1.expected_clients_high


def test_required_activity_inverts_projection():
    rates = fm.funnel_rates(conversations=200, pitches=120, contacts=60, clients=30)
    req = fm.required_activity(target_clients=10, rates=rates, working_days=5)
    # Feeding the required conversations back through the projection recovers the
    # target client count.
    p = fm.project(
        rates=rates,
        conversations_per_day=req.conversations_per_day,
        working_days=5,
        revenue_per_client=100,
    )
    assert abs(p.expected_clients - 10) < 1e-6
    # Chained stage requirements are consistent: contacts ≤ pitches ≤ conversations.
    assert req.contacts <= req.pitches <= req.conversations


def test_required_activity_band_order():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=20, clients=8)
    req = fm.required_activity(target_clients=20, rates=rates, working_days=5)
    # Worst-case rates demand more daily conversations than best-case.
    assert (
        req.conversations_per_day_low
        <= req.conversations_per_day
        <= req.conversations_per_day_high
    )


def test_bigger_target_needs_more_conversations():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=20, clients=8)
    small = fm.required_activity(target_clients=5, rates=rates, working_days=5)
    big = fm.required_activity(target_clients=50, rates=rates, working_days=5)
    assert big.conversations > small.conversations


def test_clients_for_revenue():
    assert fm.clients_for_revenue(1000, 250) == 4
    # No earnings history → cannot estimate.
    assert fm.clients_for_revenue(1000, 0) is None
