"""One-off: register the Square webhook subscription for driver subscriptions.

Validates the desired event types against the live list, creates the webhook
pointing at the driver host, and writes the returned signature key to a file
(NOT stdout) so it can be moved into .env without exposing it. Prints only
non-secret confirmation (id, url, events) plus a short fingerprint.

    docker exec blackvolt-backend python -m app.scripts.provision_square_webhook

Env: PAYMENTS_SIMULATED=false + token with webhook management scope.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid

from app.services.square_common import square_client

NOTIFICATION_URL = "https://driver.blackvoltmobility.com/api/v1/webhooks/square"
SIG_OUT = "/tmp/bv_webhook_sig"  # noqa: S108 — container-local, removed after copy
WANT = [
    "subscription.created",
    "subscription.updated",
    "invoice.payment_made",
    "invoice.scheduled_charge_failed",
    "invoice.canceled",
]


async def main() -> None:
    client = square_client()
    if client is None:
        raise SystemExit("square_client() is None — needs PAYMENTS_SIMULATED=false + token")

    listed = await client.webhooks.event_types.list()
    available = set(listed.event_types or [])
    missing = [w for w in WANT if w not in available]
    if missing:
        raise SystemExit(f"event types not available in this account: {missing}")

    resp = await client.webhooks.subscriptions.create(
        idempotency_key=str(uuid.uuid5(uuid.NAMESPACE_URL, "blackvolt:webhook:driver-subs-v1")),
        subscription={
            "name": "Black Volt driver subscriptions",
            "event_types": WANT,
            "notification_url": NOTIFICATION_URL,
        },
    )
    sub = resp.subscription
    key = sub.signature_key or ""
    with open(SIG_OUT, "w") as fh:
        fh.write(key)

    fp = hashlib.sha256(key.encode()).hexdigest()[:12] if key else "<none>"
    print(f"webhook id: {sub.id}")
    print(f"url: {sub.notification_url}")
    print(f"enabled: {sub.enabled}")
    print(f"events: {sub.event_types}")
    print(f"signature_key: len={len(key)} fp={fp} (written to {SIG_OUT})")


if __name__ == "__main__":
    asyncio.run(main())
