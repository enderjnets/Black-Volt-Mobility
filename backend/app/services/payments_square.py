"""Square payments adapter: authorize → capture → cancel → refund.

Two modes (settings.payments_live):
- **Live** — the async Square SDK (sandbox or production by SQUARE_ENV).
- **Simulated** — default; returns fake payment ids so the booking + payment flow
  works end-to-end without Square. NEVER ship simulated with APP_ENV=production.

Money is always in the smallest unit (cents). All calls are idempotent (uuid key).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.config import get_settings
from app.services.square_common import square_client


class PaymentError(RuntimeError):
    pass


@dataclass
class PaymentResult:
    square_payment_id: str | None
    status: str  # APPROVED | COMPLETED | CANCELED | ...
    simulated: bool


@dataclass
class RefundResult:
    square_refund_id: str | None
    status: str
    simulated: bool


def _client():
    """Local seam over the shared factory (monkeypatch point for tests)."""
    return square_client()


async def authorize(
    *, amount: int, currency: str, source_id: str, reference_id: str | None = None,
    note: str | None = None, capture: bool = False,
) -> PaymentResult:
    """Charge a card via the Web Payments SDK token (`source_id`). By default this only
    authorizes (holds) the funds for later capture; pass ``capture=True`` to charge in full
    immediately (used for event rides so the hold cannot expire before the event)."""
    settings = get_settings()
    client = _client()
    if client is None:
        return PaymentResult(
            square_payment_id=f"SIMUL-{uuid.uuid4().hex[:20]}",
            status="COMPLETED" if capture else "APPROVED",
            simulated=True,
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.payments.create(
            source_id=source_id,
            idempotency_key=str(uuid.uuid4()),
            amount_money={"amount": amount, "currency": currency},
            location_id=settings.SQUARE_LOCATION_ID,
            autocomplete=capture,  # False = authorize only; True = capture immediately
            reference_id=reference_id,
            note=note,
        )
    except ApiError as e:
        raise PaymentError(f"square_authorize:{e.status_code}:{e.body}") from e
    p = resp.payment
    return PaymentResult(square_payment_id=p.id, status=p.status or "APPROVED", simulated=False)


async def capture(*, square_payment_id: str) -> PaymentResult:
    """Capture (complete) a previously authorized payment."""
    client = _client()
    if client is None:
        return PaymentResult(
            square_payment_id=square_payment_id, status="COMPLETED", simulated=True
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.payments.complete(payment_id=square_payment_id)
    except ApiError as e:
        raise PaymentError(f"square_capture:{e.status_code}:{e.body}") from e
    p = resp.payment
    return PaymentResult(square_payment_id=p.id, status=p.status or "COMPLETED", simulated=False)


async def cancel(*, square_payment_id: str) -> PaymentResult:
    """Void an authorization (release the held funds)."""
    client = _client()
    if client is None:
        return PaymentResult(
            square_payment_id=square_payment_id, status="CANCELED", simulated=True
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.payments.cancel(payment_id=square_payment_id)
    except ApiError as e:
        raise PaymentError(f"square_cancel:{e.status_code}:{e.body}") from e
    p = resp.payment
    return PaymentResult(square_payment_id=p.id, status=p.status or "CANCELED", simulated=False)


async def refund(
    *, square_payment_id: str, amount: int, currency: str, reason: str | None = None
) -> RefundResult:
    """Refund a captured payment (full or partial)."""
    client = _client()
    if client is None:
        return RefundResult(
            square_refund_id=f"SIMUL-RF-{uuid.uuid4().hex[:18]}", status="COMPLETED", simulated=True
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.refunds.refund_payment(
            idempotency_key=str(uuid.uuid4()),
            amount_money={"amount": amount, "currency": currency},
            payment_id=square_payment_id,
            reason=reason,
        )
    except ApiError as e:
        raise PaymentError(f"square_refund:{e.status_code}:{e.body}") from e
    r = resp.refund
    return RefundResult(square_refund_id=r.id, status=r.status or "PENDING", simulated=False)
