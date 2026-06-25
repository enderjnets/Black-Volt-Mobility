"""Passenger profile completeness + serialization.

A profile is "complete" once it has the data Google can't give us and that a
booking needs: first name, last name, and a phone the driver can reach. Shared
by the /me/profile endpoints and the auth session payloads so the frontend can
decide whether to show the onboarding gate.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import Client

# Max length of the free-text ride note (may contain allergy info → treated as PII;
# never logged). Kept here so the API and the frontend stay in sync.
RIDE_NOTES_MAX = 500


class RidePreferences(BaseModel):
    """Validated shape of a client's standing ride preferences.

    Each dimension is single-select with a "no_pref" default so an unset client
    reads as fully neutral. Unknown keys are rejected (ignored) rather than stored.
    """

    model_config = ConfigDict(extra="forbid")

    conversation: Literal["chat", "quiet", "no_pref"] = "no_pref"
    temperature: Literal["cooler", "warmer", "no_pref"] = "no_pref"
    music: Literal["none", "soft", "driver_choice", "no_pref"] = "no_pref"
    luggage_help: bool = False
    pet: bool = False
    notes: str = ""

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > RIDE_NOTES_MAX:
            raise ValueError(f"notes exceeds {RIDE_NOTES_MAX} characters")
        return v


def normalize_ride_preferences(
    stored: dict | None, patch: dict | None = None
) -> dict:
    """Merge a partial ``patch`` onto ``stored`` prefs, fill defaults, and validate.

    Only known keys survive (unknown keys in either input are dropped before
    validation, so a hostile body can't smuggle extra fields into the JSONB).
    Raises ``pydantic.ValidationError`` / ``ValueError`` on an invalid enum value
    or an overlong note — the caller maps that to HTTP 422.
    """
    known = RidePreferences.model_fields
    merged: dict = {}
    for src in (stored or {}, patch or {}):
        if not isinstance(src, dict):
            continue
        merged.update({k: v for k, v in src.items() if k in known})
    return RidePreferences(**merged).model_dump()


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
        # Always normalized (defaults filled) so the frontend never sees a partial dict.
        "ride_preferences": normalize_ride_preferences(client.ride_preferences),
        "profile_complete": is_complete(client),
    }
