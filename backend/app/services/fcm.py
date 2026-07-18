"""Firebase Cloud Messaging (HTTP v1) sender for native-app push.

Mirrors the Web Push path in ``services/push.py``: one message per registration
token, returning "sent" | "prune" (token dead → delete the row) | "keep"
(transient, retry later). A no-op that returns "keep" when the FCM_* env is unset,
so nothing breaks and no subscription is pruned before creds exist.
"""
from __future__ import annotations

import base64
import json
import logging
import threading

import httpx

from app.config import get_settings

log = logging.getLogger("blackvolt.fcm")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_lock = threading.Lock()
_creds = None  # cached google.oauth2.service_account.Credentials


def _reset_cache() -> None:
    """Test hook: drop the cached credentials."""
    global _creds
    with _lock:
        _creds = None


def _access_token() -> str | None:
    """Service-account OAuth token for FCM, or None when unconfigured. The creds
    object is cached and refreshed under a lock (send() runs in worker threads)."""
    global _creds
    with _lock:
        s = get_settings()
        if not s.FCM_CREDENTIALS_JSON_B64:
            return None
        if _creds is None:
            from google.oauth2 import service_account

            info = json.loads(base64.b64decode(s.FCM_CREDENTIALS_JSON_B64))
            _creds = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
        if not _creds.valid:
            from google.auth.transport.requests import Request as GoogleRequest

            _creds.refresh(GoogleRequest())
        return _creds.token


def send(token: str, title: str, body: str, url: str, tag: str) -> str:
    """Deliver one notification to an FCM registration token. Sync (called via
    asyncio.to_thread, like pywebpush)."""
    s = get_settings()
    if not s.fcm_enabled:
        return "keep"
    try:
        access = _access_token()
        if not access:
            return "keep"
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {"url": url, "tag": tag},
                "android": {"collapse_key": tag, "notification": {"tag": tag}},
                "apns": {"headers": {"apns-collapse-id": tag}},
            }
        }
        r = httpx.post(
            f"https://fcm.googleapis.com/v1/projects/{s.FCM_PROJECT_ID}/messages:send",
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            json=message,
            timeout=10,
        )
        if r.status_code == 200:
            return "sent"
        txt = r.text or ""
        # A dead/invalid token: delete the row so we stop retrying it.
        if r.status_code in (400, 404) and any(
            k in txt for k in ("UNREGISTERED", "INVALID_ARGUMENT", "NOT_FOUND")
        ):
            log.info("fcm prune (status=%s): %s", r.status_code, txt[:200])
            return "prune"
        log.warning("fcm send error (status=%s): %s", r.status_code, txt[:200])
        return "keep"  # transient (403 config, 429, 5xx) — retry next time
    except Exception as e:  # noqa: BLE001
        log.warning("fcm send exception: %s", e)
        return "keep"
