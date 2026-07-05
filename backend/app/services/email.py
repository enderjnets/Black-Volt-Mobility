"""Transactional email via Resend.

`send_email` is the low-level sender: it POSTs to Resend, or LOGS the would-be
email when EMAIL_SIMULATED=true (or no key), so flows work end-to-end in dev.
`send_team_welcome` builds the bilingual driver-onboarding email and never
raises — it returns a status string the API surfaces to the owner.

Black Volt uses its OWN verified sender domain (RESEND_FROM) — never another
product's. Keys live only in `.env`.
"""
from __future__ import annotations

import logging
import time
from html import escape as html_escape
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> dict[str, Any]:
    """Send via Resend, or LOG when EMAIL_SIMULATED=true / no key.

    Returns Resend's response dict (or a synthetic equivalent in simulated mode):
      {"id": "<message id>", "simulated": bool}
    Raises on a live HTTP failure — callers that must not fail wrap this.
    """
    s = get_settings()

    if not s.email_live:
        fake_id = f"resend.SIMULATED_{int(time.time() * 1000)}"
        log.info(
            "Email SIMULATED outbound to=%s subject=%r body_len=%d (would-be id=%s)",
            to, subject, len(body_text), fake_id,
        )
        return {"id": fake_id, "simulated": True}

    body: dict[str, Any] = {
        "from": s.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "text": body_text,
    }
    if body_html:
        body["html"] = body_html

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            RESEND_ENDPOINT,
            json=body,
            headers={
                "Authorization": f"Bearer {s.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            log.error("Resend send failed: status=%d body=%s", resp.status_code, resp.text[:400])
        resp.raise_for_status()
        data = resp.json()
        data.setdefault("simulated", False)
        return data


def _welcome_content(*, name: str | None, login_url: str, lang: str) -> tuple[str, str, str]:
    """(subject, text, html) for the welcome email, in ES or EN."""
    who = (name or "").strip() or ("conductor" if lang == "es" else "driver")
    if lang == "es":
        subject = "Bienvenido a Black Volt Mobility"
        text = (
            f"Hola {who},\n\n"
            "Ya tienes acceso al panel de conductor de Black Volt Mobility.\n"
            "Entra con tu cuenta de Google (este mismo correo):\n\n"
            f"{login_url}\n\n"
            "Nos vemos en la carretera.\n— Black Volt Mobility"
        )
        cta = "Entrar al panel"
        intro = "Ya tienes acceso al panel de conductor de Black Volt Mobility. "\
                "Entra con tu cuenta de Google (este mismo correo)."
        outro = "Nos vemos en la carretera."
    else:
        subject = "Welcome to Black Volt Mobility"
        text = (
            f"Hi {who},\n\n"
            "You now have access to the Black Volt Mobility driver dashboard.\n"
            "Sign in with your Google account (this same email):\n\n"
            f"{login_url}\n\n"
            "See you on the road.\n— Black Volt Mobility"
        )
        cta = "Open the dashboard"
        intro = "You now have access to the Black Volt Mobility driver dashboard. "\
                "Sign in with your Google account (this same email)."
        outro = "See you on the road."

    greeting = ("Hola" if lang == "es" else "Hi")
    # Escape the owner-entered name before embedding it in the HTML email body.
    who_html = html_escape(who)
    html = (
        '<div style="font-family:Inter,Arial,sans-serif;background:#f4f4f5;padding:32px">'
        '<div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:14px;'
        'overflow:hidden;border:1px solid #e4e4e7">'
        '<div style="background:#0A0A0F;padding:24px 28px">'
        '<span style="color:#00E5FF;font-size:18px;font-weight:700;letter-spacing:0.04em">'
        "BLACK VOLT MOBILITY</span></div>"
        '<div style="padding:28px;color:#333333;font-size:15px;line-height:1.6">'
        f"<p style=\"margin:0 0 14px\">{greeting} {who_html},</p>"
        f'<p style="margin:0 0 22px">{intro}</p>'
        f'<a href="{login_url}" style="display:inline-block;background:#00E5FF;color:#0A0A0F;'
        "font-weight:700;text-decoration:none;padding:12px 22px;border-radius:8px;"
        f'font-size:14px">{cta}</a>'
        f'<p style="margin:22px 0 0;color:#666666;font-size:13px">{outro}<br>'
        "— Black Volt Mobility</p>"
        "</div></div></div>"
    )
    return subject, text, html


async def send_team_welcome(*, to: str, name: str | None, lang: str = "en") -> str:
    """Send the driver-onboarding welcome email. Never raises.

    Returns: "sent" (live OK), "simulated" (dev/no-key), or "failed".
    """
    lang = "es" if (lang or "").lower().startswith("es") else "en"
    login_url = get_settings().PUBLIC_DASHBOARD_URL
    subject, text, html = _welcome_content(name=name, login_url=login_url, lang=lang)
    try:
        res = await send_email(to=to, subject=subject, body_text=text, body_html=html)
    except Exception as e:  # network / Resend error must not break member-add
        log.warning("Welcome email to %s failed: %s", to, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"


async def _driver_recipient(db, *, tenant_id: int | None):
    """Active dashboard user for a driver tenant (the ride's notification target).

    Returns the AllowedUser row or None when the tenant has no active user."""
    if not tenant_id:
        return None
    from sqlalchemy import select

    from app.models import AllowedUser

    return (
        await db.execute(
            select(AllowedUser)
            .where(AllowedUser.tenant_id == tenant_id, AllowedUser.active.is_(True))
            .order_by(AllowedUser.id.asc())
        )
    ).scalars().first()


def _fmt_when(scheduled_at, lang: str) -> str:
    if scheduled_at is None:
        return "—"
    return scheduled_at.strftime("%a %b %d, %Y · %I:%M %p")


def _ride_lang(ride) -> str:
    return "es" if str(getattr(ride, "lang", "") or "").lower().startswith("es") else "en"


async def send_driver_new_ride(db, *, ride) -> str:
    """Notify the driver that a new (confirmed) ride landed. Never raises.

    Routed to the driver who owns the ride (`assigned_tenant_id` for a discount
    handoff, else the booking tenant). Returns "sent"|"simulated"|"failed"|"skipped"."""
    driver_tenant_id = getattr(ride, "assigned_tenant_id", None) or ride.tenant_id
    user = await _driver_recipient(db, tenant_id=driver_tenant_id)
    if user is None or not user.email:
        return "skipped"
    lang = _ride_lang(ride)
    when = _fmt_when(ride.scheduled_at, lang)
    route = f"{ride.pickup_text} → {ride.dropoff_text}"
    pax_name = (ride.passenger_name or "").strip() or ("Pasajero" if lang == "es" else "Passenger")
    fare = f"{ride.currency or 'USD'} {ride.fare_total:.2f}" if ride.fare_total else "—"
    flight_label = "Vuelo" if lang == "es" else "Flight"
    flight = f"\n{flight_label}: {ride.flight_number}" if ride.flight_number else ""
    if lang == "es":
        subject = f"Nuevo viaje: {route}"
        text = (
            f"Tienes un nuevo viaje confirmado.\n\n"
            f"Pasajero: {pax_name}\nRecogida: {ride.pickup_text}\nDestino: {ride.dropoff_text}\n"
            f"Cuándo: {when}\nTarifa: {fare}{flight}\n\n"
            f"Revisa los detalles en tu panel.\n— Black Volt Mobility"
        )
    else:
        subject = f"New ride: {route}"
        text = (
            f"You have a new confirmed ride.\n\n"
            f"Passenger: {pax_name}\nPickup: {ride.pickup_text}\nDrop-off: {ride.dropoff_text}\n"
            f"When: {when}\nFare: {fare}{flight}\n\n"
            f"See the details in your dashboard.\n— Black Volt Mobility"
        )
    try:
        res = await send_email(to=user.email, subject=subject, body_text=text)
    except Exception as e:  # notification must never break the booking flow
        log.warning("New-ride email to %s failed: %s", user.email, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"


async def send_driver_ride_cancelled(db, *, ride, refund_pending: bool = False) -> str:
    """Notify the driver a ride was cancelled. Never raises. When refund_pending
    (cancelled <24h with a live payment), prompts the driver to choose the refund."""
    driver_tenant_id = getattr(ride, "assigned_tenant_id", None) or ride.tenant_id
    user = await _driver_recipient(db, tenant_id=driver_tenant_id)
    if user is None or not user.email:
        return "skipped"
    lang = _ride_lang(ride)
    when = _fmt_when(ride.scheduled_at, lang)
    route = f"{ride.pickup_text} → {ride.dropoff_text}"
    if lang == "es":
        subject = f"Viaje cancelado: {route}"
        action = (
            "\n\nEl cliente canceló con menos de 24h. Entra a tu panel para elegir el "
            "reembolso (completo o con tarifa de cancelación)."
            if refund_pending
            else ""
        )
        text = (
            f"Un viaje fue cancelado.\n\nRuta: {route}\nCuándo: {when}{action}"
            "\n\n— Black Volt Mobility"
        )
    else:
        subject = f"Ride cancelled: {route}"
        action = (
            "\n\nThe client cancelled within 24h. Open your dashboard to choose the "
            "refund (full or with a cancellation fee)."
            if refund_pending
            else ""
        )
        text = (
            f"A ride was cancelled.\n\nRoute: {route}\nWhen: {when}{action}"
            "\n\n— Black Volt Mobility"
        )
    try:
        res = await send_email(to=user.email, subject=subject, body_text=text)
    except Exception as e:
        log.warning("Cancellation email to %s failed: %s", user.email, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"


async def notify_owner_chat_escalation(db, *, conversation, client, messages) -> str:
    """Tell the tenant owner a Joules chat needs a human. ``messages`` is the
    recent turns (objects with ``.role`` and ``.body``). Never raises."""
    user = await _driver_recipient(db, tenant_id=conversation.tenant_id)
    if user is None or not user.email:
        return "skipped"
    name = (getattr(client, "name", None) or getattr(client, "email", None) or "A passenger")
    contact_bits = []
    if getattr(client, "email", None):
        contact_bits.append(f"Email: {client.email}")
    if getattr(client, "phone", None):
        contact_bits.append(f"Phone: {client.phone}")
    contact = "\n".join(contact_bits) or "No contact on file."
    transcript_lines = []
    for m in list(messages)[-10:]:
        who = {"user": name, "assistant": "Joules", "owner": "You"}.get(
            getattr(getattr(m, "role", None), "value", getattr(m, "role", "")), "?"
        )
        transcript_lines.append(f"{who}: {m.body}")
    transcript = "\n".join(transcript_lines) or "(no messages)"
    dash = f"{get_settings().PUBLIC_DASHBOARD_URL}/inbox"
    subject = f"Chat escalation from {name}"
    text = (
        f"Joules handed off a chat that needs your attention.\n\n"
        f"{contact}\n\n"
        f"Recent conversation:\n{transcript}\n\n"
        f"Open the full thread here:\n{dash}\n\n— Black Volt Mobility"
    )
    try:
        res = await send_email(to=user.email, subject=subject, body_text=text)
    except Exception as e:
        log.warning("Chat-escalation email to %s failed: %s", user.email, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"


async def notify_owner_new_review(db, *, review) -> str:
    """Tell the tenant owner a new review landed (pending moderation). Never raises."""
    user = await _driver_recipient(db, tenant_id=review.tenant_id)
    if user is None or not user.email:
        return "skipped"
    rating = int(review.rating)
    stars = "★" * rating + "☆" * (5 - rating)
    dash = f"{get_settings().PUBLIC_DASHBOARD_URL}/reviews"
    subject = f"New review ({rating}/5) from {review.author_name}"
    text = (
        f"A new review is waiting for your approval.\n\n"
        f"{stars}  {rating}/5\n"
        f"From: {review.author_name}\n\n"
        f'"{review.body}"\n\n'
        f"Approve or hide it here:\n{dash}\n\n— Black Volt Mobility"
    )
    try:
        res = await send_email(to=user.email, subject=subject, body_text=text)
    except Exception as e:
        log.warning("New-review email to %s failed: %s", user.email, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"


async def send_review_request(
    *, to: str, author_name: str | None, link: str, lang: str = "en"
) -> str:
    """Email a past customer asking for a review (link to the public review form)."""
    lang = "es" if (lang or "").lower().startswith("es") else "en"
    who = (author_name or "").strip()
    if lang == "es":
        subject = "¿Nos dejas una reseña? — Black Volt Mobility"
        greet = f"Hola {who}," if who else "Hola,"
        intro = (
            "Gracias por viajar con Black Volt Mobility. ¿Nos dejas una reseña rápida? "
            "Toma menos de un minuto."
        )
        cta = "Escribir mi reseña"
        outro = "Gracias por tu apoyo."
    else:
        subject = "Mind leaving a review? — Black Volt Mobility"
        greet = f"Hi {who}," if who else "Hi,"
        intro = (
            "Thanks for riding with Black Volt Mobility. Would you leave a quick review? "
            "It takes under a minute."
        )
        cta = "Write my review"
        outro = "Thanks for the support."
    text = f"{greet}\n\n{intro}\n\n{link}\n\n{outro}\n— Black Volt Mobility"
    html = (
        '<div style="font-family:Inter,Arial,sans-serif;background:#f4f4f5;padding:32px">'
        '<div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:14px;'
        'overflow:hidden;border:1px solid #e4e4e7">'
        '<div style="background:#0A0A0F;padding:24px 28px">'
        '<span style="color:#00E5FF;font-size:18px;font-weight:700;letter-spacing:0.04em">'
        "BLACK VOLT MOBILITY</span></div>"
        '<div style="padding:28px;color:#333333;font-size:15px;line-height:1.6">'
        f'<p style="margin:0 0 14px">{html_escape(greet)}</p>'
        f'<p style="margin:0 0 22px">{html_escape(intro)}</p>'
        f'<a href="{link}" style="display:inline-block;background:#00E5FF;color:#0A0A0F;'
        "font-weight:700;text-decoration:none;padding:12px 22px;border-radius:8px;"
        f'font-size:14px">{cta}</a>'
        f'<p style="margin:22px 0 0;color:#666666;font-size:13px">{html_escape(outro)}<br>'
        "— Black Volt Mobility</p>"
        "</div></div></div>"
    )
    try:
        res = await send_email(to=to, subject=subject, body_text=text, body_html=html)
    except Exception as e:
        log.warning("Review-request email to %s failed: %s", to, e)
        return "failed"
    return "simulated" if res.get("simulated") else "sent"
