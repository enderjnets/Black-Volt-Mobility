"""Square Subscriptions adapter: customer → card-on-file → subscription.

Two modes (settings.payments_live — the same gate as one-off payments):
- **Live** — the async Square SDK (sandbox or production by SQUARE_ENV).
- **Simulated** — default; returns fake ids (`SIMCUST-…`, `SIMCARD-…`, `SIMSUB-…`)
  so the driver-onboarding flow works end-to-end without Square. NEVER ship
  simulated with APP_ENV=production.

This module NEVER touches the ride one-off payment flow (payments_square.py)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings

logger = logging.getLogger("blackvolt.subscriptions")


class SubscriptionError(RuntimeError):
    """`public_code` is the ONLY detail safe to return to the unauthenticated
    caller; the full message (Square status + body) is log-only."""

    public_code = "subscription_failed"

    def __init__(self, message: str, *, public_code: str | None = None):
        super().__init__(message)
        if public_code is not None:
            self.public_code = public_code


@dataclass
class CustomerResult:
    square_customer_id: str
    simulated: bool


@dataclass
class CardResult:
    square_card_id: str
    simulated: bool


@dataclass
class SubscriptionResult:
    square_subscription_id: str
    status: str  # ACTIVE | ...
    current_period_end: datetime | None
    simulated: bool


def _client():
    """Async Square client for the configured environment, or None when simulated."""
    settings = get_settings()
    if not settings.payments_live:
        return None
    from square import AsyncSquare
    from square.environment import SquareEnvironment

    env = (
        SquareEnvironment.PRODUCTION
        if settings.SQUARE_ENV == "production"
        else SquareEnvironment.SANDBOX
    )
    return AsyncSquare(token=settings.SQUARE_ACCESS_TOKEN, environment=env)


async def create_customer(*, email: str) -> CustomerResult:
    client = _client()
    if client is None:
        return CustomerResult(
            square_customer_id=f"SIMCUST-{uuid.uuid4().hex[:18]}", simulated=True
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.customers.create(
            idempotency_key=str(uuid.uuid4()), email_address=email
        )
    except ApiError as e:
        raise SubscriptionError(
            f"square_customer:{e.status_code}:{e.body}", public_code="square_customer"
        ) from e
    return CustomerResult(square_customer_id=resp.customer.id, simulated=False)


async def create_card(*, customer_id: str, source_id: str) -> CardResult:
    """Store the tokenized card (Web Payments SDK nonce) on file for recurring
    billing."""
    client = _client()
    if client is None:
        return CardResult(square_card_id=f"SIMCARD-{uuid.uuid4().hex[:18]}", simulated=True)
    from square.core.api_error import ApiError

    try:
        resp = await client.cards.create(
            idempotency_key=str(uuid.uuid4()),
            source_id=source_id,
            card={"customer_id": customer_id},
        )
    except ApiError as e:
        raise SubscriptionError(
            f"square_card:{e.status_code}:{e.body}", public_code="square_card"
        ) from e
    return CardResult(square_card_id=resp.card.id, simulated=False)


async def create_subscription(
    *, plan_variation_id: str, customer_id: str, card_id: str, location_id: str
) -> SubscriptionResult:
    client = _client()
    if client is None:
        return SubscriptionResult(
            square_subscription_id=f"SIMSUB-{uuid.uuid4().hex[:18]}",
            status="ACTIVE",
            current_period_end=None,
            simulated=True,
        )
    from square.core.api_error import ApiError

    try:
        resp = await client.subscriptions.create(
            idempotency_key=str(uuid.uuid4()),
            location_id=location_id,
            plan_variation_id=plan_variation_id,
            customer_id=customer_id,
            card_id=card_id,
        )
    except ApiError as e:
        raise SubscriptionError(
            f"square_subscription:{e.status_code}:{e.body}", public_code="square_subscription"
        ) from e
    s = resp.subscription
    return SubscriptionResult(
        square_subscription_id=s.id,
        status=s.status or "ACTIVE",
        current_period_end=None,
        simulated=False,
    )
