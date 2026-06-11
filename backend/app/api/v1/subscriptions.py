"""Subscriptions API (Square): a driver subscribes to a SaaS plan.

POST /subscriptions is PUBLIC — a brand-new driver has no session yet when they
subscribe from the landing. The secret Square token never reaches the frontend;
the page only uses the public app/location id from GET /payments/config and sends
the tokenized card (source_id) here. This never touches the ride payment flow."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models import Subscription, SubscriptionStatus
from app.services import subscriptions, subscriptions_square

logger = logging.getLogger("blackvolt.api.subscriptions")

router = APIRouter(tags=["subscriptions"])


class SubscribeBody(BaseModel):
    plan_key: str = Field(min_length=1)
    source_id: str = Field(min_length=1)  # Web Payments SDK token (nonce)
    # Plain str (not EmailStr) to avoid the email-validator dependency; a basic
    # shape check is enough — Square is the source of truth for deliverability.
    email: str = Field(min_length=3)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        # Lowercase like every other email in the app (auth.py, team.py) — the
        # (email, plan_key) idempotency key depends on one canonical form.
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email")
        return v


def _out(s: Subscription) -> dict:
    return {
        "status": s.status.value if isinstance(s.status, SubscriptionStatus) else s.status,
        "subscription_id": s.square_subscription_id,
        "simulated": s.simulated,
    }


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscribeBody,
    db: AsyncSession = Depends(get_db),
):
    try:
        sub = await subscriptions.subscribe(
            db, plan_key=body.plan_key, email=body.email, source_id=body.source_id
        )
    except subscriptions.InvalidPlanError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=e.public_code
        ) from e
    except subscriptions_square.SubscriptionError as e:
        # Full message (Square status + body) is log-only; the anonymous caller
        # gets the stable public code, nothing more.
        logger.error("subscribe failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=e.public_code
        ) from e
    return _out(sub)
