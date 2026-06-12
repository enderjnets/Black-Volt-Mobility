"""Square subscription webhooks → keep the local Subscription row in sync.

Square fires events over the life of a subscription (payment made/failed,
subscription updated/canceled). This module verifies the event signature and
applies the resulting status to our row. It NEVER creates rows (the public
subscribe flow owns creation) and NEVER touches simulated rows.

Security: `verify_signature` reproduces Square's HMAC-SHA256 over
(notification URL + raw body) and compares in constant time. Without BOTH the
signing key and the exact registered URL (`settings.webhooks_live`) every event
is rejected — we never act on an unverified payload."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Subscription, SubscriptionStatus
from app.services.subscriptions_square import _parse_square_date

logger = logging.getLogger("blackvolt.subscriptions")

# Square subscription.status → our status. Anything unknown/missing stays
# PENDING so a surprise value can never silently entitle a tenant.
_WEBHOOK_STATUS_MAP = {
    "ACTIVE": SubscriptionStatus.ACTIVE,
    "PENDING": SubscriptionStatus.PENDING,
    "PAUSED": SubscriptionStatus.PAST_DUE,
    "DEACTIVATED": SubscriptionStatus.CANCELED,
    "CANCELED": SubscriptionStatus.CANCELED,
}

# Invoice events that don't carry a subscription status but move our row.
_INVOICE_PAID = {"invoice.payment_made"}
_INVOICE_FAILED = {"invoice.scheduled_charge_failed", "invoice.payment_failed", "invoice.canceled"}


def verify_signature(*, body: bytes, signature: str) -> bool:
    """True only when the HMAC-SHA256 of (registered URL + body) matches the
    `x-square-hmacsha256` header. Refuses everything unless webhooks_live."""
    settings = get_settings()
    if not settings.webhooks_live:
        return False
    payload = settings.SQUARE_WEBHOOK_URL.encode("utf-8") + body
    digest = hmac.new(
        settings.SQUARE_WEBHOOK_SIGNATURE_KEY.encode("utf-8"), payload, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature or "")


def _object(event: dict) -> dict:
    return ((event or {}).get("data") or {}).get("object") or {}


def _resolve(event: dict) -> tuple[str | None, SubscriptionStatus | None, str | None]:
    """Return (square_subscription_id, new_status, charged_through_date) for the
    event, or (None, …) when it carries nothing we lock onto."""
    etype = (event or {}).get("type") or ""
    obj = _object(event)
    if etype == "subscription.updated" or etype.startswith("subscription."):
        sub = obj.get("subscription") or {}
        sub_id = sub.get("id")
        if etype in ("subscription.canceled", "subscription.deactivated"):
            return sub_id, SubscriptionStatus.CANCELED, None
        status = _WEBHOOK_STATUS_MAP.get((sub.get("status") or "").upper())
        return sub_id, status, sub.get("charged_through_date")
    if etype.startswith("invoice."):
        sub_id = (obj.get("invoice") or {}).get("subscription_id")
        if etype in _INVOICE_PAID:
            return sub_id, SubscriptionStatus.ACTIVE, None
        if etype in _INVOICE_FAILED:
            return sub_id, SubscriptionStatus.PAST_DUE, None
        return sub_id, None, None
    return None, None, None


async def apply_event(db: AsyncSession, *, event: dict) -> str:
    """Sync the local row for a verified event. Idempotent (redelivery-safe) and
    a no-op for unknown ids or simulated rows. Returns a short status string."""
    sub_id, new_status, charged_through = _resolve(event)
    if not sub_id:
        return "ignored"
    row = (
        await db.execute(
            select(Subscription).where(Subscription.square_subscription_id == sub_id)
        )
    ).scalar_one_or_none()
    if row is None or row.simulated:
        return "ignored"

    changed = False
    if new_status is not None and row.status != new_status:
        row.status = new_status
        changed = True
    period_end = _parse_square_date(charged_through)
    if period_end is not None and row.current_period_end != period_end:
        row.current_period_end = period_end
        changed = True

    if changed:
        await db.commit()
        logger.info(
            "webhook applied: sub=%s type=%s status=%s",
            sub_id, (event or {}).get("type"), row.status.value,
        )
    return "applied" if changed else "noop"
