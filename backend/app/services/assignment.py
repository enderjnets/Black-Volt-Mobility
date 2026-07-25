"""Ride hand-off: the owner passes a ride to another driver on the team.

The ride NEVER changes owner — `Ride.tenant_id` stays with whoever booked it, so the
customer, the money and the history remain theirs. Assigning only sets
`Ride.assigned_tenant_id`, which the existing ride queries already honour
(`booking.list_rides`/`get_ride` match on either column), so the ride simply shows up in
the assigned driver's dashboard.

What the assigned driver may do is deliberately narrow: work the ride (status changes)
and talk to the owner on the internal channel. Re-assigning, re-pricing and the payout
split stay with the owner — see `can_manage`.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllowedUser, RateConfig, Ride
from app.models.allowed_user import ROLE_DRIVER
from app.services import earnings

logger = logging.getLogger("blackvolt.assignment")


class AssignError(Exception):
    """Carries a stable code the API turns into a 400 detail."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_owner(ride: Ride, tenant_id: int) -> bool:
    return ride.tenant_id == tenant_id


def is_assigned_driver(ride: Ride, tenant_id: int) -> bool:
    return ride.assigned_tenant_id is not None and ride.assigned_tenant_id == tenant_id


def can_manage(ride: Ride, tenant_id: int) -> bool:
    """Owner-only powers: assign/unassign, pricing, the payout split, deletion."""
    return is_owner(ride, tenant_id)


def can_view(ride: Ride, tenant_id: int) -> bool:
    return is_owner(ride, tenant_id) or is_assigned_driver(ride, tenant_id)


async def assignable_drivers(db: AsyncSession, *, tenant_id: int) -> list[AllowedUser]:
    """Team members who can actually take a ride: role `driver`, already signed in at
    least once (so their workspace exists) and not the owner's own tenant."""
    rows = (
        await db.execute(
            select(AllowedUser).where(
                AllowedUser.tenant_id.is_not(None),
                AllowedUser.role == ROLE_DRIVER,
            )
        )
    ).scalars().all()
    return [u for u in rows if u.tenant_id != tenant_id]


async def _defaults(db: AsyncSession, *, tenant_id: int) -> tuple[float, int, float, int]:
    """(fee_pct, fee_fixed_cents, tax_pct, driver_pct) from the owner's RateConfig,
    falling back to the model defaults when the tenant has no config row yet."""
    cfg = (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if cfg is None:
        return 2.9, 30, 0.0, 80
    return (
        float(cfg.square_fee_pct),
        int(cfg.square_fee_fixed_cents),
        float(cfg.tax_reserve_pct),
        int(cfg.default_driver_share_pct),
    )


async def assign(
    db: AsyncSession,
    ride: Ride,
    *,
    owner_tenant_id: int,
    driver_email: str,
    driver_share_pct: int | None = None,
    note: str | None = None,
    by_email: str | None = None,
) -> Ride:
    """Hand `ride` to the team driver with `driver_email`, snapshotting the split so a
    later config change never rewrites this ride's numbers. Raises AssignError."""
    if not can_manage(ride, owner_tenant_id):
        raise AssignError("not_ride_owner")
    email = (driver_email or "").strip().lower()
    if not email:
        raise AssignError("driver_required")
    target = next(
        (u for u in await assignable_drivers(db, tenant_id=owner_tenant_id) if u.email == email),
        None,
    )
    if target is None:
        raise AssignError("driver_not_assignable")

    fee_pct, fee_fixed, tax_pct, default_pct = await _defaults(db, tenant_id=owner_tenant_id)
    pct = default_pct if driver_share_pct is None else int(driver_share_pct)
    if not 0 <= pct <= 100:
        raise AssignError("bad_share_pct")

    ride.assigned_tenant_id = target.tenant_id
    ride.assigned_at = datetime.now(UTC)
    ride.assigned_by_email = (by_email or "")[:254] or None
    ride.assign_note = (note or "").strip()[:400] or None
    ride.driver_share_pct = pct
    ride.square_fee_pct = fee_pct
    ride.square_fee_fixed_cents = fee_fixed
    ride.tax_reserve_pct = tax_pct
    ride.driver_payout_status = "unpaid"
    ride.driver_paid_at = None
    await db.flush()
    logger.info("ride %s assigned to tenant %s (%d%%)", ride.id, target.tenant_id, pct)
    return ride


async def unassign(db: AsyncSession, ride: Ride, *, owner_tenant_id: int) -> Ride:
    """Take the ride back. Clears the split snapshot; the internal thread is kept as a
    record of what was said."""
    if not can_manage(ride, owner_tenant_id):
        raise AssignError("not_ride_owner")
    if ride.assigned_tenant_id is None:
        raise AssignError("not_assigned")
    ride.assigned_tenant_id = None
    ride.assigned_at = None
    ride.assign_note = None
    ride.driver_share_pct = None
    ride.driver_payout_status = "unpaid"
    ride.driver_paid_at = None
    await db.flush()
    return ride


async def set_payout(
    db: AsyncSession,
    ride: Ride,
    *,
    owner_tenant_id: int,
    driver_share_pct: int | None = None,
    paid: bool | None = None,
) -> Ride:
    """Adjust the driver's share, and/or mark what the owner already handed over.
    Marking paid is bookkeeping only — this app never moves money."""
    if not can_manage(ride, owner_tenant_id):
        raise AssignError("not_ride_owner")
    if ride.assigned_tenant_id is None:
        raise AssignError("not_assigned")
    if driver_share_pct is not None:
        if not 0 <= int(driver_share_pct) <= 100:
            raise AssignError("bad_share_pct")
        ride.driver_share_pct = int(driver_share_pct)
    if paid is not None:
        ride.driver_payout_status = "paid" if paid else "unpaid"
        ride.driver_paid_at = datetime.now(UTC) if paid else None
    await db.flush()
    return ride


async def split_for(db: AsyncSession, ride: Ride) -> dict | None:
    """The money breakdown for an assigned ride, using the snapshot taken at assign
    time (never today's config). None when the ride was never handed off."""
    if ride.assigned_tenant_id is None or ride.driver_share_pct is None:
        return None
    fee_pct = ride.square_fee_pct
    fee_fixed = ride.square_fee_fixed_cents
    tax_pct = ride.tax_reserve_pct
    if fee_pct is None or fee_fixed is None or tax_pct is None:  # pre-snapshot row
        fee_pct, fee_fixed, tax_pct, _ = await _defaults(db, tenant_id=ride.tenant_id)
    out = earnings.compute(
        ride.fare_total,
        fee_pct=fee_pct,
        fee_fixed_cents=fee_fixed,
        tax_pct=tax_pct,
        driver_pct=ride.driver_share_pct,
    ).as_dict()
    out["payout_status"] = ride.driver_payout_status
    out["paid_at"] = ride.driver_paid_at.isoformat() if ride.driver_paid_at else None
    return out
