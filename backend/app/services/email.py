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
