"""Web Push delivery (PWA notifications) — VAPID / pywebpush.

Two audiences share one table (``push_subscriptions``):
- **staff** — driver/owner devices; fed by the 7 dashboard-bell events via
  ``notifications.emit`` (hooked there, so call-sites stay untouched).
- **client** — passenger devices; fed by ride events (cancel / refund / pickup
  reminder) from ``api/v1/rides`` and the scheduler.

Delivery contract (mirrors ``notifications.emit`` and the notification emails):
BEST-EFFORT and non-blocking. Request handlers call the ``notify_*`` helpers,
which fire-and-forget a background task on a FRESH session — a push failure (or a
slow/offline push service) can never delay the HTTP response, roll back the
caller's transaction, or raise. The scheduler awaits ``deliver_*`` directly (no
user is waiting on it). Dead endpoints (404/410) are pruned as they surface.

With no VAPID keys configured, every entry point is a silent no-op, so dev/test
builds send nothing and never touch the network.
"""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, PushSubscription
from app.services import fcm

log = logging.getLogger("blackvolt.push")

# Deep-link targets are RELATIVE. Each PWA registers its service worker on its own
# origin (apex for clients, app. for staff), so the SW resolves these against the
# right host with no absolute URL needed server-side.
_CLIENT_TRIPS_URL = "/trips"

# Staff push copy (EN). The dashboard bell itself renders localized text client-side
# from i18n; a push is a static string, so we ship concise EN here. url matches the
# bell's own deep-links (dashboard host).
_STAFF_COPY: dict[str, tuple[str, str, str]] = {
    "ride_new": ("New ride booked", "A new ride just came in.", "/dashboard/rides"),
    "ride_cancelled": ("Ride cancelled", "A ride was cancelled.", "/dashboard/rides"),
    "chat_escalated": ("Chat needs you", "A customer chat was escalated.", "/dashboard/inbox"),
    "chat_message": ("New message", "A customer sent a message.", "/dashboard/inbox"),
    "ride_message": ("New ride message", "A rider messaged you about a ride.", "/dashboard/rides"),
    "review_new": ("New review", "A customer left a review.", "/dashboard/reviews"),
    "discount_redeemed": ("Discount redeemed", "A discount code was redeemed.", "/dashboard/rides"),
    "subscription_payment_failed": (
        "Payment failed",
        "A subscription charge failed.",
        "/dashboard/settings",
    ),
}

# Client push copy, localized by the client/ride language. Body may take a {place}.
_CLIENT_COPY: dict[str, dict[str, tuple[str, str]]] = {
    "ride_cancelled": {
        "en": ("Ride cancelled", "Your ride to {place} was cancelled."),
        "es": ("Viaje cancelado", "Tu viaje a {place} fue cancelado."),
    },
    "refund_full": {
        "en": ("Refund issued", "You've been fully refunded for your cancelled ride."),
        "es": ("Reembolso emitido", "Se te reembolsó por completo tu viaje cancelado."),
    },
    "refund_partial": {
        "en": ("Refund issued", "A partial refund was issued for your cancelled ride."),
        "es": ("Reembolso emitido", "Se emitió un reembolso parcial por tu viaje cancelado."),
    },
    "pickup_reminder": {
        "en": ("Your ride is coming up", "Pickup at {place} soon — we'll be there."),
        "es": ("Tu viaje se acerca", "Recogida en {place} pronto — ahí estaremos."),
    },
    "ride_message": {
        "en": ("Message from your driver", "Open your trip to reply."),
        "es": ("Mensaje de tu chofer", "Abre tu viaje para responder."),
    },
}


def _lang(code: str | None) -> str:
    return "es" if (code or "").lower().startswith("es") else "en"


def _place(text: str | None, lang: str | None = None) -> str:
    """A short, human place label for a push body (first segment of an address)."""
    fallback = "tu destino" if _lang(lang) == "es" else "your destination"
    if not text:
        return fallback
    return text.split(",")[0].strip()[:60] or fallback


# ─── Fire-and-forget entry points (request handlers) ────────────────────────


def notify_staff(tenant_id: int | None, *, kind: str) -> None:
    """Push one of the 7 bell events to a tenant's staff devices. Never raises."""
    if not tenant_id or not get_settings().push_enabled:
        return
    copy = _STAFF_COPY.get(kind)
    if copy is None:
        return
    title, body, url = copy
    _spawn(deliver_to_staff(tenant_id, _payload(title, body, url, tag=f"staff:{kind}")))


def notify_client(
    tenant_id: int | None,
    client_id: int | None,
    *,
    event: str,
    lang: str | None,
    place: str | None = None,
    ride_id: int | None = None,
) -> None:
    """Push a ride event to a passenger's devices. Never raises. When ``ride_id``
    is given the tap opens that ride's chat directly (``/trips?chat=<id>``)."""
    if not tenant_id or not client_id or not get_settings().push_enabled:
        return
    variants = _CLIENT_COPY.get(event)
    if not variants:
        return
    title, body = variants[_lang(lang)]
    body = body.format(place=_place(place, lang))
    url = f"{_CLIENT_TRIPS_URL}?chat={ride_id}" if ride_id else _CLIENT_TRIPS_URL
    _spawn(deliver_to_client(client_id, _payload(title, body, url, tag=f"client:{event}")))


def _payload(title: str, body: str, url: str, *, tag: str) -> dict:
    return {"title": title, "body": body, "url": url, "tag": tag}


def _spawn(coro) -> None:
    """Run a delivery coroutine detached from the request. Best-effort: if there is
    no running loop (shouldn't happen under ASGI), just drop it."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    task = loop.create_task(_guard(coro))
    # Hold a reference so the task isn't GC'd mid-flight (asyncio only keeps weak refs).
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


_PENDING: set = set()


async def _guard(coro) -> None:
    try:
        await coro
    except Exception:  # noqa: BLE001 — a push must never surface anywhere
        log.warning("push delivery failed", exc_info=True)


# ─── Deliverers (own their session; awaited by the scheduler) ───────────────


async def deliver_to_staff(tenant_id: int, payload: dict) -> tuple[int, int]:
    from app.db.base import get_session_factory

    async with get_session_factory()() as db:
        subs = (
            await db.execute(
                select(PushSubscription).where(
                    PushSubscription.tenant_id == tenant_id,
                    PushSubscription.audience == "staff",
                )
            )
        ).scalars().all()
        return await _fanout(db, subs, payload)


async def deliver_to_client(client_id: int, payload: dict) -> tuple[int, int]:
    # client_id is a global PK, so it fully scopes a passenger's devices — no
    # tenant filter needed (and a rider booking under another driver's tenant still
    # gets their push, unlike a tenant-scoped query).
    from app.db.base import get_session_factory

    async with get_session_factory()() as db:
        subs = (
            await db.execute(
                select(PushSubscription).where(
                    PushSubscription.audience == "client",
                    PushSubscription.client_id == client_id,
                )
            )
        ).scalars().all()
        return await _fanout(db, subs, payload)


async def _fanout(
    db: AsyncSession, subs: list[PushSubscription], payload: dict
) -> tuple[int, int]:
    """Send to each subscription; prune the dead ones. Returns (found, sent):
    how many subscriptions existed and how many were actually delivered (a transient
    failure keeps the subscription but does NOT count as delivered)."""
    if not subs:
        return 0, 0
    dead: list[int] = []
    sent = 0
    for sub in subs:
        status = await _send_one(sub, payload)
        if status == "sent":
            sent += 1
        elif status == "prune":
            dead.append(sub.id)
    if dead:
        try:
            await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
    return len(subs), sent


async def _send_one(sub: PushSubscription, payload: dict) -> str:
    """Deliver one push in a worker thread (both channels are sync). Returns:
    - "sent"  — delivered;
    - "prune" — endpoint/token gone, caller should delete the row;
    - "keep"  — transient error, logged, subscription retained.

    Routes by ``sub.platform``: "fcm" → the native app via FCM HTTP v1; anything
    else → Web Push (pywebpush) as before. Every call-site is unchanged."""
    settings = get_settings()
    if sub.platform == "fcm":
        return await asyncio.to_thread(
            fcm.send,
            sub.endpoint,
            payload.get("title", ""),
            payload.get("body", ""),
            payload.get("url", "/"),
            payload.get("tag", "bv"),
        )
    try:
        from pywebpush import webpush

        def _do() -> None:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                timeout=10,
            )

        await asyncio.to_thread(_do)
        return "sent"
    except Exception as e:  # noqa: BLE001
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            return "prune"  # subscription expired/unsubscribed
        log.warning("push send error (endpoint=%s status=%s): %s", sub.endpoint[:60], status, e)
        return "keep"  # transient — retry next time


# ─── Scheduler: passenger pickup reminders ──────────────────────────────────

# How far ahead of pickup to remind, and the interval the job runs on.
REMINDER_LEAD_HOURS = 3


async def send_due_pickup_reminders(db: AsyncSession) -> int:
    """Push a reminder to passengers whose confirmed ride departs within the next
    REMINDER_LEAD_HOURS and hasn't been reminded yet. Idempotent via
    ``rides.pickup_reminder_sent_at``. Returns # reminders queued."""
    if not get_settings().push_enabled:
        return 0
    from datetime import UTC, datetime, timedelta

    from app.models import Ride, RideStatus

    now = datetime.now(UTC)
    horizon = now + timedelta(hours=REMINDER_LEAD_HOURS)
    rides = (
        await db.execute(
            select(Ride).where(
                Ride.status.in_((RideStatus.CONFIRMED, RideStatus.ASSIGNED)),
                Ride.client_id.is_not(None),
                Ride.scheduled_at.is_not(None),
                Ride.scheduled_at > now,
                Ride.scheduled_at <= horizon,
                Ride.pickup_reminder_sent_at.is_(None),
            )
        )
    ).scalars().all()
    if not rides:
        return 0

    # Language per ride: prefer the ride snapshot, fall back to the client's pref.
    n = 0
    for ride in rides:
        lang = ride.lang
        if not lang and ride.client_id:
            client = await db.get(Client, ride.client_id)
            lang = getattr(client, "lang", None)
        title, body = _CLIENT_COPY["pickup_reminder"][_lang(lang)]
        body = body.format(place=_place(ride.pickup_text, lang))
        payload = _payload(title, body, _CLIENT_TRIPS_URL, tag=f"client:pickup:{ride.id}")
        found, sent = await deliver_to_client(ride.client_id, payload)
        # Mark reminded only when it actually went out (sent) OR the passenger has no
        # device subscribed (found == 0 → nothing to retry). A transient failure with
        # a live subscription (found > 0, sent == 0) stays unmarked so the next run
        # retries — a pickup reminder has no email fallback, so we must not drop it.
        if sent > 0 or found == 0:
            ride.pickup_reminder_sent_at = now
            n += 1
        # Commit per ride so a later failure can't un-record earlier successes.
        await db.commit()
    return n
