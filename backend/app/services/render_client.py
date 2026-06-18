"""Hybrid render bridge → BitTrader.

Black Volt generates the light parts of a post (script/caption/hashtags) and
offloads the heavy video render (Hailuo + TTS + ffmpeg) to a separate BitTrader
worker. This module is the thin client for that handoff.

Stage 1 ships SIMULATED only: `submit()` returns immediately with a sentinel
asset so the whole owner-approval flow is demoable with zero external setup. The
live path (Stage 2) POSTs the script to the BitTrader render endpoint; BitTrader
renders and POSTs the finished mp4 back to our HMAC-signed `/social/webhooks/
render` callback, which writes it under the public /media mount (closing
BitTrader's "needs a public URL" gap for Meta/TikTok).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets

import httpx

from app.config import get_settings

logger = logging.getLogger("blackvolt.social.render")

# Sentinel media path for a simulated render — the frontend recognises the
# scheme and shows a "simulated render" placeholder instead of a real <video>.
SIMULATED_MEDIA = "simulated://sample.mp4"


def _job_id() -> str:
    return f"job_{secrets.token_hex(8)}"


async def submit(*, tenant_id: int, post_id: int, script: dict) -> dict:
    """Request a render. Returns a dict describing the outcome:

    - simulated → {"job_id", "status": "rendered", "media_path", "cover_path",
      "simulated": True} (asset is ready immediately).
    - live (Stage 2) → {"job_id", "status": "render_requested", "simulated": False}
      and the real asset arrives later via the signed callback.

    Never raises for a simulated render; a live submit failure raises so the
    caller can mark the post failed.
    """
    settings = get_settings()
    job_id = _job_id()
    if not settings.social_render_live:
        return {
            "job_id": job_id,
            "status": "rendered",
            "media_path": SIMULATED_MEDIA,
            "cover_path": None,
            "simulated": True,
        }

    # Live: hand the script to the BitTrader worker. It renders asynchronously and
    # calls back our signed webhook with the mp4 — we only kick it off here. The
    # outbound request is HMAC-signed with the shared key so the worker only ever
    # renders for us (the same key it signs the callback with).
    payload = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "post_id": post_id,
        "script": script,
        "callback_url": settings.SOCIAL_RENDER_CALLBACK_URL,
    }
    body = json.dumps(payload).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(settings.SOCIAL_RENDER_SIGNING_KEY.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                settings.SOCIAL_RENDER_URL,
                content=body,
                headers={"Content-Type": "application/json", "x-bv-render-signature": sig},
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error("social render submit failed job=%s: %s", job_id, e)
        raise
    return {"job_id": job_id, "status": "render_requested", "simulated": False}
