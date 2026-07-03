"""Payments API (Square): authorize at booking, capture on completion, refund.

POST /payments authorizes a card for a ride (passenger pays own ride; staff any).
Capture and refund are staff-only. The frontend gets the public Square config from
GET /payments/config to initialize the Web Payments SDK."""
from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, require_staff, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.models import Client, Payment, PaymentStatus, Ride
from app.services import auth, booking, meta_capi, payments, payments_square

router = APIRouter(tags=["payments"])


def _client_ip(request: Request) -> str | None:
    """Real client IP behind Cloudflare/proxy, for Meta match quality."""
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _schedule_capi_purchase(
    background: BackgroundTasks,
    request: Request,
    db: AsyncSession,
    tenant_id: int,
    ride: Ride,
    pay: Payment,
) -> None:
    """Queue a server-side Meta Purchase for a just-authorized card booking. All
    matchable signal is pulled here (the request + db session won't outlive the
    response); only the network POST runs in the background. Never raises."""
    if pay.status not in (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED):
        return
    # The single Meta pixel belongs to the owner's ad account (like Buffer); block
    # sub-tenant bookings from polluting it. None disables the gate.
    owner = get_settings().OWNER_TENANT_ID
    if owner is not None and tenant_id != owner:
        return
    client = await db.get(Client, ride.client_id) if ride.client_id else None
    background.add_task(
        meta_capi.send_purchase,
        ride_id=ride.id,
        event_time=int(time.time()),
        value=(pay.amount or 0) / 100.0,
        currency=pay.currency or "USD",
        email=getattr(client, "email", None),
        phone=ride.passenger_phone or getattr(client, "phone", None),
        first_name=getattr(client, "first_name", None),
        last_name=getattr(client, "last_name", None),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        fbp=request.cookies.get("_fbp"),
        fbc=request.cookies.get("_fbc"),
    )


class AuthorizeBody(BaseModel):
    ride_id: int
    source_id: str = Field(min_length=1)  # Web Payments SDK token (nonce)
    amount: int | None = Field(default=None, ge=1)  # cents; default = ride fare


class RefundBody(BaseModel):
    reason: str | None = None


def _payment_out(p: Payment) -> dict:
    return {
        "id": p.id,
        "ride_id": p.ride_id,
        "status": p.status.value if isinstance(p.status, PaymentStatus) else p.status,
        "amount": p.amount,
        "currency": p.currency,
        "square_payment_id": p.square_payment_id,
        "square_refund_id": p.square_refund_id,
        "simulated": p.simulated,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/payments/config")
async def payments_config():
    """Public Square config for the frontend Web Payments SDK."""
    s = get_settings()
    return {
        "enabled": True,
        "live": s.payments_live,
        "env": s.SQUARE_ENV,
        "application_id": s.SQUARE_APPLICATION_ID or None,
        "location_id": s.SQUARE_LOCATION_ID or None,
    }


@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def authorize_payment(
    body: AuthorizeBody,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=body.ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if payload.get("role") == auth.ROLE_PASSENGER and ride.client_id != payload.get("cid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        pay = await payments.authorize_for_ride(
            db, tenant_id=tenant_id, ride=ride, source_id=body.source_id, amount=body.amount
        )
    except payments_square.PaymentError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
    await _schedule_capi_purchase(background, request, db, tenant_id, ride, pay)
    return _payment_out(pay)


@router.post("/payments/{payment_id}/capture")
async def capture_payment(
    payment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    pay = await payments.get_payment(db, tenant_id=tenant_id, payment_id=payment_id)
    if pay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment_not_found")
    try:
        pay = await payments.capture_payment(db, tenant_id=tenant_id, payment=pay)
    except payments_square.PaymentError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return _payment_out(pay)


@router.post("/payments/{payment_id}/refund")
async def refund_payment(
    payment_id: int,
    body: RefundBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    pay = await payments.get_payment(db, tenant_id=tenant_id, payment_id=payment_id)
    if pay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment_not_found")
    try:
        pay = await payments.refund_payment(
            db, tenant_id=tenant_id, payment=pay, reason=body.reason
        )
    except payments_square.PaymentError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return _payment_out(pay)


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    tenant_id = await resolve_tenant_id(db, payload)
    pay = await payments.get_payment(db, tenant_id=tenant_id, payment_id=payment_id)
    if pay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment_not_found")
    return _payment_out(pay)
