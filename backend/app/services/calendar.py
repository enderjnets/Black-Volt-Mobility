"""Google Calendar adapter: push scheduled rides to the Black Volt calendar.

Two modes (settings.calendar_live):
- **Live** — Google Calendar API via a service account that has been shared on
  the Black Volt calendar (`GOOGLE_CALENDAR_ID`) with "make changes to events".
- **Simulated** — default; returns a fake event id so the booking flow works
  without Google. Calendar writes are best-effort and never block a booking.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from app.config import get_settings

logger = logging.getLogger("blackvolt.calendar")

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_service_cache = None


class CalendarError(RuntimeError):
    pass


def _service():
    """Cached Google Calendar v3 service, or None when simulated/unconfigured."""
    global _service_cache
    settings = get_settings()
    if not settings.calendar_live:
        return None
    if _service_cache is not None:
        return _service_cache
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
    )
    _service_cache = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service_cache


def upsert_event(
    *,
    summary: str,
    description: str,
    location: str,
    start: datetime,
    duration_min: int,
    event_id: str | None = None,
) -> str | None:
    """Create or update a calendar event. Returns the event id (or a simulated
    one). Returns None and logs on failure — never raises to the caller."""
    settings = get_settings()
    svc = _service()
    if svc is None:
        return event_id or f"SIM-EVT-{uuid.uuid4().hex[:18]}"
    tz = settings.CALENDAR_TIMEZONE
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": (start + timedelta(minutes=duration_min)).isoformat(), "timeZone": tz},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
    }
    try:
        cal = settings.GOOGLE_CALENDAR_ID
        if event_id:
            ev = svc.events().patch(calendarId=cal, eventId=event_id, body=body).execute()
        else:
            ev = svc.events().insert(calendarId=cal, body=body).execute()
        return ev.get("id")
    except Exception as e:  # network / auth / API — best-effort
        logger.warning("calendar upsert failed: %s", e)
        return event_id


def delete_event(event_id: str | None) -> None:
    """Remove a calendar event (no-op when simulated). Best-effort."""
    if not event_id or event_id.startswith("SIM-EVT-"):
        return
    svc = _service()
    if svc is None:
        return
    try:
        svc.events().delete(
            calendarId=get_settings().GOOGLE_CALENDAR_ID, eventId=event_id
        ).execute()
    except Exception as e:
        logger.warning("calendar delete failed: %s", e)


def build_ride_event(
    *,
    client_name: str | None,
    pickup: str,
    dropoff: str,
    fare: float | None,
    flight: str | None,
    phone: str | None,
    notes: str | None,
) -> dict:
    """Compose the summary/description/location for a ride event."""
    name = client_name or "Guest"
    parts = [f"{pickup}  →  {dropoff}"]
    if flight:
        parts.append(f"Flight {flight}")
    if fare:
        parts.append(f"Fare ${round(fare)}")
    if phone:
        parts.append(f"Phone {phone}")
    if notes:
        parts.append(notes)
    return {
        "summary": f"Black Volt · {name}",
        "description": "\n".join(parts),
        "location": pickup,
    }
