"""Payment orchestration: persist Payment rows + drive the Square adapter +
move the ride through its lifecycle. Tenant-scoped."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentMethod, PaymentStatus, Ride, RideStatus
from app.services import discounts, payments_square

_logger = logging.getLogger("blackvolt.payments")


async def get_payment(db: AsyncSession, *, tenant_id: int, payment_id: int) -> Payment | None:
    return (
        await db.execute(
            select(Payment).where(Payment.tenant_id == tenant_id, Payment.id == payment_id)
        )
    ).scalar_one_or_none()


async def authorize_for_ride(
    db: AsyncSession, *, tenant_id: int, ride: Ride, source_id: str, amount: int | None = None
) -> Payment:
    """Authorize a card for a ride (Web SDK token = source_id). On success the
    ride is confirmed and the Payment row is stored AUTHORIZED."""
    cents = amount if amount is not None else int(round((ride.fare_total or 0) * 100))
    if cents <= 0:
        raise payments_square.PaymentError("invalid_amount")
    res = await payments_square.authorize(
        amount=cents,
        currency=ride.currency or "USD",
        source_id=source_id,
        reference_id=f"ride-{ride.id}",
        note=f"Black Volt ride #{ride.id}",
    )
    pay = Payment(
        tenant_id=tenant_id,
        ride_id=ride.id,
        status=PaymentStatus.AUTHORIZED,
        amount=cents,
        currency=ride.currency or "USD",
        square_payment_id=res.square_payment_id,
        simulated=res.simulated,
    )
    db.add(pay)
    ride.payment_id = res.square_payment_id
    ride.payment_method = PaymentMethod.SQUARE  # card via Square
    if ride.status in (RideStatus.REQUESTED, RideStatus.QUOTED):
        ride.status = RideStatus.CONFIRMED
    await db.commit()
    await db.refresh(pay)
    # Atomic discount redemption: claim flag + increment in one transaction.
    # Payment durability (commit above) is guaranteed before touching discount state.
    # Uses DB-level conditional UPDATE as the idempotency gate — race- and crash-safe.
    if ride.discount_code_id:
        try:
            status = await discounts.redeem_for_ride(db, ride.id, ride.discount_code_id)
            if status == "already":
                _logger.debug("discount already claimed for ride %s; skipping", ride.id)
        except Exception:  # noqa: BLE001
            _logger.exception("discount redemption failed for ride %s; ignoring", ride.id)
    # The ride is now CONFIRMED (the card authorized) — push it to the driver's
    # calendar. Unpaid QUOTED drafts never reach this point, so the calendar event
    # is only created once payment succeeds. Best-effort (never raises).
    from app.services import booking

    await booking.sync_ride_to_calendar(db, ride)
    return pay


async def capture_payment(db: AsyncSession, *, tenant_id: int, payment: Payment) -> Payment:
    if payment.status != PaymentStatus.AUTHORIZED:
        raise payments_square.PaymentError(f"cannot_capture_status:{payment.status.value}")
    res = await payments_square.capture(square_payment_id=payment.square_payment_id)
    payment.status = PaymentStatus.CAPTURED
    if res.square_payment_id:
        payment.square_payment_id = res.square_payment_id
    # Mark the ride settled (paid by Square).
    if payment.ride_id:
        ride = (
            await db.execute(select(Ride).where(Ride.id == payment.ride_id))
        ).scalar_one_or_none()
        if ride:
            ride.paid = True
            ride.paid_at = datetime.now(UTC)
            ride.payment_method = PaymentMethod.SQUARE
            # Settling a ride whose pickup time has passed closes it.
            from app.services import booking

            booking.complete_if_overdue_paid(ride)
    await db.commit()
    await db.refresh(payment)
    return payment


async def cancel_payment(db: AsyncSession, *, tenant_id: int, payment: Payment) -> Payment:
    if payment.status != PaymentStatus.AUTHORIZED:
        raise payments_square.PaymentError(f"cannot_cancel_status:{payment.status.value}")
    await payments_square.cancel(square_payment_id=payment.square_payment_id)
    payment.status = PaymentStatus.CANCELED
    await db.commit()
    await db.refresh(payment)
    return payment


async def refund_payment(
    db: AsyncSession, *, tenant_id: int, payment: Payment, reason: str | None = None
) -> Payment:
    if payment.status != PaymentStatus.CAPTURED:
        raise payments_square.PaymentError(f"cannot_refund_status:{payment.status.value}")
    res = await payments_square.refund(
        square_payment_id=payment.square_payment_id,
        amount=payment.amount,
        currency=payment.currency,
        reason=reason,
    )
    payment.status = PaymentStatus.REFUNDED
    payment.square_refund_id = res.square_refund_id
    await db.commit()
    await db.refresh(payment)
    return payment
