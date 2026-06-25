"""Passenger profile completeness + serialization.

A profile is "complete" once it has the data Google can't give us and that a
booking needs: first name, last name, and a phone the driver can reach. Shared
by the /me/profile endpoints and the auth session payloads so the frontend can
decide whether to show the onboarding gate.
"""
from __future__ import annotations

from app.models import Client


def is_complete(client: Client) -> bool:
    return bool(client.first_name) and bool(client.last_name) and bool(client.phone)


def normalize_lang(v: str | None) -> str | None:
    """Coerce any language input (incl. "Spanish"/"español") to EN|ES for storage.
    None or blank stays None (no preference)."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    return "ES" if s.startswith(("es", "sp")) else "EN"


def serialize(client: Client) -> dict:
    return {
        "first_name": client.first_name,
        "last_name": client.last_name,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "home_address": client.home_address,
        "sms_consent": client.sms_consent,
        "email_consent": client.email_consent,
        # lowercased for the frontend i18n which uses "en"/"es"; None = no preference.
        "lang": client.lang.lower() if client.lang else None,
        "profile_complete": is_complete(client),
    }
