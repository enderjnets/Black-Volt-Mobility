"""Ride hand-off money split — pure math, no DB, no network."""
import os

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")

from app.services.earnings import compute  # noqa: E402


def test_owner_example_95_at_80_pct():
    """The owner's own example: a $95 ride charged through Square, 80% to the driver."""
    s = compute(95, fee_pct=2.9, fee_fixed_cents=30, tax_pct=0, driver_pct=80)
    assert s.gross == 95.0
    assert s.square_fee == 3.06  # 2.9% of 95 = 2.755 → 2.76 + 0.30
    assert s.net == 91.94
    assert s.driver_amount == 73.55
    assert s.owner_amount == 18.39


def test_parts_always_sum_exactly():
    """No cent may appear or vanish, at any preset, with or without a tax reserve."""
    for fare in (0.55, 12.34, 95, 100, 187.77, 999.99):
        for pct in (0, 50, 70, 80, 100):
            for tax in (0.0, 8.0, 12.5):
                s = compute(fare, tax_pct=tax, driver_pct=pct)
                assert round(s.square_fee + s.tax_reserve + s.net, 2) == s.gross
                assert round(s.driver_amount + s.owner_amount, 2) == s.net


def test_quick_presets_are_distinct_and_ordered():
    """100 / 80 / 70 / 50 must give the driver strictly less as the share drops."""
    amounts = [compute(100, driver_pct=p).driver_amount for p in (100, 80, 70, 50)]
    assert amounts == sorted(amounts, reverse=True)
    assert len(set(amounts)) == 4


def test_100_pct_leaves_owner_nothing_and_0_pct_leaves_all():
    full = compute(100, driver_pct=100)
    assert full.owner_amount == 0.0 and full.driver_amount == full.net
    none = compute(100, driver_pct=0)
    assert none.driver_amount == 0.0 and none.owner_amount == none.net


def test_tax_reserve_comes_off_after_the_fee():
    """The reserve is a slice of what's left after Square, not of the gross."""
    s = compute(100, fee_pct=2.9, fee_fixed_cents=30, tax_pct=10, driver_pct=100)
    assert s.square_fee == 3.20
    assert s.tax_reserve == 9.68  # 10% of 96.80
    assert s.net == 87.12
    assert s.driver_amount == 87.12


def test_unpriced_ride_is_all_zero():
    for fare in (None, 0, 0.0):
        s = compute(fare)
        assert (s.gross, s.net, s.driver_amount, s.owner_amount) == (0.0, 0.0, 0.0, 0.0)


def test_fee_never_exceeds_gross_so_net_cannot_go_negative():
    """A fare smaller than the fixed fee must not produce a negative payout."""
    s = compute(0.10, fee_pct=2.9, fee_fixed_cents=30)
    assert s.square_fee == 0.10
    assert s.net == 0.0
    assert s.driver_amount == 0.0 and s.owner_amount == 0.0


def test_share_pct_is_clamped():
    assert compute(100, driver_pct=250).driver_share_pct == 100
    assert compute(100, driver_pct=-5).driver_share_pct == 0
