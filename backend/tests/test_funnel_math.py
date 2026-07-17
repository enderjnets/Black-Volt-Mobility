"""Unit tests for the pure funnel math (no DB, no framework)."""
import json
import math

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


def test_required_activity_zero_conversion_stays_finite():
    # Regression: with no wins yet (0 clients from 30 contacts), the Wilson lower
    # bound of the conversion rate collapses to ~0, so the worst-case overall rate
    # is below the 1e-9 guard. Dividing target by that used to yield float("inf"),
    # which is not JSON serializable and crashed the projection endpoint. Every
    # field must now be finite, and the band must stay correctly ordered.
    rates = fm.funnel_rates(conversations=100, pitches=60, contacts=30, clients=0)
    assert rates.overall_low < 1e-9  # the degenerate condition that triggered the bug
    req = fm.required_activity(target_clients=10, rates=rates, working_days=22)
    values = [
        req.contacts,
        req.pitches,
        req.conversations,
        req.conversations_per_day,
        req.conversations_per_day_low,
        req.conversations_per_day_high,
    ]
    assert all(math.isfinite(v) for v in values)
    assert (
        req.conversations_per_day_low
        <= req.conversations_per_day
        <= req.conversations_per_day_high
    )
    # The whole dataclass must round-trip through strict JSON (no NaN/Infinity).
    json.dumps(values)


def test_bigger_target_needs_more_conversations():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=20, clients=8)
    small = fm.required_activity(target_clients=5, rates=rates, working_days=5)
    big = fm.required_activity(target_clients=50, rates=rates, working_days=5)
    assert big.conversations > small.conversations


def test_clients_for_revenue():
    assert fm.clients_for_revenue(1000, 250) == 4
    # No earnings history → cannot estimate.
    assert fm.clients_for_revenue(1000, 0) is None


# ── coach_insight ─────────────────────────────────────────────────────────────
def test_coach_focus_is_weakest_stage():
    # convert is the worst stage (clients far below contacts) → it's the lever.
    rates = fm.funnel_rates(conversations=100, pitches=80, contacts=60, clients=3)
    ins = fm.coach_insight(
        rates=rates, conversations_per_day=5, working_days=5, revenue_per_client=200
    )
    assert ins.focus_stage == "convert"
    assert ins.focus_rate == min(rates.pitch.point, rates.contact.point, rates.convert.point)


def test_coach_suggested_bumps_current_pace():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=25, clients=10)
    ins = fm.coach_insight(
        rates=rates, conversations_per_day=4, working_days=5, revenue_per_client=150
    )
    assert ins.suggested_per_day >= ins.current_per_day
    assert ins.suggested_per_day >= 3  # never a defeatist target


def test_coach_prob_in_unit_interval_and_rises_with_cadence():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=25, clients=10)
    low = fm.coach_insight(
        rates=rates, conversations_per_day=2, working_days=5, revenue_per_client=150
    )
    high = fm.coach_insight(
        rates=rates, conversations_per_day=2, working_days=5,
        revenue_per_client=150, target_clients=15,
    )
    for ins in (low, high):
        assert 0.0 < ins.prob_at_least_one <= 1.0
    # A higher target → higher suggested cadence → (non-strictly) higher P(≥1).
    assert high.suggested_per_day > low.suggested_per_day
    assert high.prob_at_least_one >= low.prob_at_least_one


def test_coach_band_order_and_revenue():
    rates = fm.funnel_rates(conversations=100, pitches=50, contacts=25, clients=10)
    ins = fm.coach_insight(
        rates=rates, conversations_per_day=6, working_days=5, revenue_per_client=200
    )
    assert ins.expected_clients_low <= ins.expected_clients <= ins.expected_clients_high
    assert ins.expected_revenue_low <= ins.expected_revenue <= ins.expected_revenue_high
    assert abs(ins.expected_revenue - ins.expected_clients * 200) < 1e-6
    assert ins.has_earnings is True


def test_coach_no_earnings_path():
    rates = fm.funnel_rates(conversations=40, pitches=20, contacts=10, clients=2)
    ins = fm.coach_insight(
        rates=rates, conversations_per_day=3, working_days=5, revenue_per_client=0
    )
    assert ins.has_earnings is False
    assert ins.expected_revenue == 0.0


def test_coach_insight_caps_absurd_cadence():
    # A driver with a huge goal would otherwise be told to talk to hundreds of
    # people a day. The suggestion must stay human-reachable and finite, and the
    # projected clients/revenue with it.
    rates = fm.funnel_rates(conversations=200, pitches=20, contacts=10, clients=2)
    ins = fm.coach_insight(
        rates=rates,
        conversations_per_day=4.0,
        working_days=5.0,
        revenue_per_client=75.0,
        target_clients=1000.0,  # absurd goal
    )
    assert ins.suggested_per_day <= fm.COACH_MAX_PER_DAY
    assert ins.suggested_per_day >= ins.current_per_day
    # No inf/nan leaks into the projection.
    for v in (ins.expected_clients, ins.expected_revenue, ins.prob_at_least_one):
        assert v == v and v not in (float("inf"), float("-inf"))


def test_coach_insight_respects_higher_existing_pace():
    # If the driver already works above the cap, don't suggest *less* than they do.
    rates = fm.funnel_rates(conversations=300, pitches=60, contacts=30, clients=10)
    ins = fm.coach_insight(
        rates=rates, conversations_per_day=50.0, working_days=5.0, revenue_per_client=75.0
    )
    assert ins.suggested_per_day >= 50.0
