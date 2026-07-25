"""Ride hand-off money split.

When the owner assigns a ride to another driver, the customer still pays Black Volt
through Square. Out of that gross the processor fee comes off first, then an optional
tax reserve the owner keeps, and whatever is left (the NET) is split with the driver by
an agreed percentage.

This module only computes and reports — it moves no money. Square's own fee is not
known until the payment settles, so the fee here is the tenant's configured estimate
(`RateConfig.square_fee_pct` / `square_fee_fixed_cents`) and can be trued up later.

Everything is done in integer CENTS: floats would leak fractions of a cent into a payout
the owner has to settle by hand. Any rounding residue goes to the owner, never the
driver, so `driver + owner == net` holds exactly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Split:
    """Every number in dollars, rounded to cents, and internally consistent:
    `square_fee + tax_reserve + net == gross` and `driver + owner == net`."""

    gross: float
    square_fee: float
    tax_reserve: float
    net: float
    driver_amount: float
    owner_amount: float
    driver_share_pct: int

    def as_dict(self) -> dict:
        return asdict(self)


def _cents(dollars: float) -> int:
    """Dollars → cents, half-up (money rounding, not Python's banker's rounding)."""
    return int((float(dollars) * 100) + (0.5 if dollars >= 0 else -0.5))


def compute(
    fare: float | None,
    *,
    fee_pct: float = 2.9,
    fee_fixed_cents: int = 30,
    tax_pct: float = 0.0,
    driver_pct: int = 80,
) -> Split:
    """Split a ride's fare. A missing/zero fare yields an all-zero split (an
    unpriced ride owes nobody anything) — never an error, this feeds a read endpoint.
    `driver_pct` is clamped to 0..100; the fee is never allowed to exceed the gross,
    so a tiny fare can't produce a negative net."""
    gross_c = max(0, _cents(fare or 0))
    pct = max(0, min(100, int(driver_pct)))
    if gross_c == 0:
        return Split(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, pct)

    fee_c = min(gross_c, _cents(gross_c * max(0.0, fee_pct) / 100 / 100) + max(0, fee_fixed_cents))
    after_fee_c = gross_c - fee_c
    tax_c = min(after_fee_c, _cents(after_fee_c * max(0.0, tax_pct) / 100 / 100))
    net_c = after_fee_c - tax_c

    driver_c = _cents(net_c * pct / 100 / 100)
    driver_c = max(0, min(net_c, driver_c))
    owner_c = net_c - driver_c  # residue lands here, so the parts always sum to net

    return Split(
        gross=gross_c / 100,
        square_fee=fee_c / 100,
        tax_reserve=tax_c / 100,
        net=net_c / 100,
        driver_amount=driver_c / 100,
        owner_amount=owner_c / 100,
        driver_share_pct=pct,
    )
