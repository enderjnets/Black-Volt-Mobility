"""Meta Conversions API (server-side ad measurement).

Sends booking conversions straight to Meta's Graph API so the ad algorithm can
optimize for *bookers*, not clickers — the browser Pixel loses a large share of
events to iOS/ad-blockers, and server events fill that gap. Every server event
carries an `event_id` shared with the browser Pixel so Meta deduplicates the two.

PII (email/phone/name) is SHA-256 hashed per Meta's normalization spec before it
leaves the box; raw values are never sent. The access token is a SECRET and lives
only in the VPS `.env` (never committed). Fail-soft: this never raises into the
booking path — a measurement POST must not break a payment.
"""
from __future__ import annotations

import hashlib
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

# The passenger-facing origin the /book flow is served from (apex, not the app.
# dashboard host). Only used as event_source_url metadata for match quality.
EVENT_SOURCE_URL = "https://blackvoltmobility.com/book"


def purchase_event_id(ride_id: int) -> str:
    """Stable id shared by the browser Pixel and this server event so Meta
    collapses the pair into one conversion."""
    return f"purchase_{ride_id}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return _sha256(e) if e and "@" in e else None


def _hash_phone(phone: str | None) -> str | None:
    """Meta wants E.164 digits only (country code + number, no +/spaces)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:  # bare US number → prepend country code
        digits = "1" + digits
    return _sha256(digits)


def _hash_name(name: str | None) -> str | None:
    n = (name or "").strip().lower()
    return _sha256(n) if n else None


def _user_data(
    *,
    email: str | None,
    phone: str | None,
    first_name: str | None,
    last_name: str | None,
    client_ip: str | None,
    user_agent: str | None,
    fbp: str | None,
    fbc: str | None,
) -> dict:
    ud: dict = {}
    if (em := _hash_email(email)) is not None:
        ud["em"] = [em]
    if (ph := _hash_phone(phone)) is not None:
        ud["ph"] = [ph]
    if (fn := _hash_name(first_name)) is not None:
        ud["fn"] = [fn]
    if (ln := _hash_name(last_name)) is not None:
        ud["ln"] = [ln]
    # IP + UA are NOT hashed (Meta matches them raw); fbp/fbc come from Pixel cookies.
    if client_ip:
        ud["client_ip_address"] = client_ip
    if user_agent:
        ud["client_user_agent"] = user_agent
    if fbp:
        ud["fbp"] = fbp
    if fbc:
        ud["fbc"] = fbc
    return ud


async def send_purchase(
    *,
    ride_id: int,
    event_time: int,
    value: float,
    currency: str = "USD",
    email: str | None = None,
    phone: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    fbp: str | None = None,
    fbc: str | None = None,
) -> dict:
    """Send one Purchase to the Conversions API. Never raises; returns a small
    result dict {sent, simulated, [status]}. No-ops (simulated) unless the CAPI is
    fully configured and enabled (`settings.capi_live`)."""
    s = get_settings()
    if not s.capi_live:
        return {"sent": False, "simulated": True}

    ud = _user_data(
        email=email,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        client_ip=client_ip,
        user_agent=user_agent,
        fbp=fbp,
        fbc=fbc,
    )
    if not ud:
        # No matchable signal at all — sending would be wasted and lower match rate.
        log.warning("meta_capi: skipping purchase ride=%s (no user_data)", ride_id)
        return {"sent": False, "simulated": False, "status": "no_user_data"}

    event: dict = {
        "event_name": "Purchase",
        "event_time": event_time,
        "event_id": purchase_event_id(ride_id),
        "action_source": "website",
        "event_source_url": EVENT_SOURCE_URL,
        "user_data": ud,
        "custom_data": {"currency": currency.upper(), "value": round(float(value), 2)},
    }
    body: dict = {"data": [event]}
    if s.META_TEST_EVENT_CODE:
        body["test_event_code"] = s.META_TEST_EVENT_CODE
    # Access token goes in the POST body, NOT the URL query, so it can never leak
    # into a logged request URL if httpx raises.
    body["access_token"] = s.META_CAPI_ACCESS_TOKEN

    url = f"https://graph.facebook.com/{s.META_GRAPH_VERSION}/{s.META_PIXEL_ID}/events"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
        if resp.status_code >= 400:
            log.error(
                "meta_capi purchase failed ride=%s status=%d body=%s",
                ride_id,
                resp.status_code,
                resp.text[:400],
            )
            return {"sent": False, "simulated": False, "status": resp.status_code}
        return {"sent": True, "simulated": False, "status": resp.status_code}
    except Exception as e:  # noqa: BLE001 — measurement must never break booking
        log.error("meta_capi purchase error ride=%s: %s", ride_id, e)
        return {"sent": False, "simulated": False, "status": "error"}
