"""Payment orchestration: persist Payment rows + drive the Square adapter +
move the ride through its lifecycle. Tenant-scoped."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentMethod, PaymentStatus, Ride, RideStatus
from app.services import payments_square


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
