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
    ride is confirmed and the Payment row is stored AUTHORIZED. For a round trip the
    linked return leg is confirmed too and its fare is included in the charge."""
    # A round-trip's fees ride on the outbound leg; the return leg must be paid THROUGH the
    # outbound (which sums both fares). Refuse to charge a return leg on its own — otherwise
    # a client could authorize just the return id and dodge the outbound fare + surcharges.
    if ride.is_return:
        raise payments_square.PaymentError("pay_via_outbound_leg")
    ret = await _linked_return(db, ride)
    if ret is not None:
        # Round trip: the amount is server-computed from both legs; ignore any client value.
        cents = int(round(((ride.fare_total or 0) + (ret.fare_total or 0)) * 100))
    elif amount is not None:
        cents = amount
    else:
        cents = int(round((ride.fare_total or 0) * 100))
    if cents <= 0:
        raise payments_square.PaymentError("invalid_amount")
    # Event rides are charged in full at booking (captured now), not held — a Square hold
    # expires in ~6 days, which would fail for a concert booked further out.
    is_event = bool((ride.price_breakdown or {}).get("event"))
    res = await payments_square.authorize(
        amount=cents,
        currency=ride.currency or "USD",
        source_id=source_id,
        reference_id=f"ride-{ride.id}",
        note=f"Black Volt ride #{ride.id}",
        capture=is_event,
    )
    now = datetime.now(UTC)
    pay = Payment(
        tenant_id=tenant_id,
        ride_id=ride.id,
        status=PaymentStatus.CAPTURED if is_event else PaymentStatus.AUTHORIZED,
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
    if is_event:
        ride.paid = True
        ride.paid_at = now
    if ret is not None:
        # One card charge covers both legs; mirror the confirmation onto the return leg.
        ret.payment_id = res.square_payment_id
        ret.payment_method = PaymentMethod.SQUARE
        if ret.status in (RideStatus.REQUESTED, RideStatus.QUOTED):
            ret.status = RideStatus.CONFIRMED
        if is_event:
            ret.paid = True
            ret.paid_at = now
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
    if ret is not None:
        await booking.sync_ride_to_calendar(db, ret)
    # Tell the driver a new (paid) ride came in. Best-effort, never raises.
    from app.services import email

    await email.send_driver_new_ride(db, ride=ride)
    return pay


async def _linked_return(db: AsyncSession, ride: Ride) -> Ride | None:
    """The return leg of a round trip (outbound rides carry ``return_ride_id``)."""
    rid = getattr(ride, "return_ride_id", None)
    if not rid:
        return None
    return (
        await db.execute(select(Ride).where(Ride.id == rid))
    ).scalar_one_or_none()


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
            from app.services import booking

            for leg in (ride, await _linked_return(db, ride)):
                if leg is None:
                    continue
                leg.paid = True
                leg.paid_at = datetime.now(UTC)
                leg.payment_method = PaymentMethod.SQUARE
                # Settling a ride whose pickup time has passed closes it.
                booking.complete_if_overdue_paid(leg)
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
    db: AsyncSession,
    *,
    tenant_id: int,
    payment: Payment,
    amount: int | None = None,
    reason: str | None = None,
) -> Payment:
    """Refund a CAPTURED payment. `amount` (cents) refunds a partial amount;
    None refunds the full captured amount. The refunded cents are recorded on
    `payment.refunded_amount` for accounting (kept = amount - refunded_amount)."""
    if payment.status != PaymentStatus.CAPTURED:
        raise payments_square.PaymentError(f"cannot_refund_status:{payment.status.value}")
    refund_cents = payment.amount if amount is None else int(amount)
    if refund_cents <= 0 or refund_cents > payment.amount:
        raise payments_square.PaymentError("invalid_amount")
    res = await payments_square.refund(
        square_payment_id=payment.square_payment_id,
        amount=refund_cents,
        currency=payment.currency,
        reason=reason,
    )
    payment.status = PaymentStatus.REFUNDED
    payment.refunded_amount = refund_cents
    payment.square_refund_id = res.square_refund_id
    await db.commit()
    await db.refresh(payment)
    return payment


async def active_payment_for_ride(
    db: AsyncSession, *, tenant_id: int, ride_id: int
) -> Payment | None:
    """The ride's settleable Square payment (AUTHORIZED hold or CAPTURED charge),
    if any. Cash / pay-on-completion rides have none."""
    return (
        await db.execute(
            select(Payment)
            .where(
                Payment.tenant_id == tenant_id,
                Payment.ride_id == ride_id,
                Payment.status.in_((PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)),
            )
            .order_by(Payment.id.desc())
        )
    ).scalars().first()


async def settle_cancellation(
    db: AsyncSession, *, tenant_id: int, ride: Ride, fee_pct: int
) -> Payment | None:
    """Resolve the money side of a cancelled ride.

    `fee_pct == 0`  → full refund: void the hold (AUTHORIZED) or refund the
    charge (CAPTURED). The rider is made whole.
    `fee_pct in {20, 30}` → the driver keeps that percentage as a cancellation
    fee and the rest is refunded. An uncaptured hold is captured in full first
    (we bypass `capture_payment` so a CANCELLED ride is not flipped to paid/
    completed by its side effects), then the non-fee portion is refunded.

    No settleable payment (cash / pay-on-completion) → no-op, returns None.
    """
    if fee_pct not in (0, 20, 30, 50):
        raise payments_square.PaymentError("invalid_fee_pct")
    # The payment always belongs to the ride's owning tenant (the booker), which
    # can differ from the acting tenant on a discount-handoff ride. Scope the
    # lookup to the ride so the servicing driver's decision still finds it.
    payment = await active_payment_for_ride(db, tenant_id=ride.tenant_id, ride_id=ride.id)
    if payment is None:
        return None
    owner_tid = ride.tenant_id

    if fee_pct == 0:
        if payment.status == PaymentStatus.AUTHORIZED:
            return await cancel_payment(db, tenant_id=owner_tid, payment=payment)
        return await refund_payment(
            db, tenant_id=owner_tid, payment=payment, reason="ride_cancelled"
        )

    amount = payment.amount
    fee_cents = round(amount * fee_pct / 100)
    refund_cents = amount - fee_cents
    if payment.status == PaymentStatus.AUTHORIZED:
        # Capture the full hold WITHOUT capture_payment's ride side effects
        # (the ride is cancelled, not completed), then refund the non-fee part.
        res = await payments_square.capture(square_payment_id=payment.square_payment_id)
        payment.status = PaymentStatus.CAPTURED
        payment.square_payment_id = res.square_payment_id or payment.square_payment_id
        await db.commit()
        await db.refresh(payment)
    # Refund the non-fee portion FIRST; only mark the ride paid once the money
    # has actually settled, so a failed refund leaves a recoverable state
    # (payment CAPTURED, refunded_amount NULL) instead of a ride marked paid.
    result = payment
    if refund_cents > 0:
        result = await refund_payment(
            db, tenant_id=owner_tid, payment=payment, amount=refund_cents, reason="cancellation_fee"
        )
    # The driver collected the cancellation fee.
    ride.paid = True
    ride.paid_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(ride)
    return result
