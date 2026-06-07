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
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings

logger = logging.getLogger("blackvolt.calendar")

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_service_cache = None

# Default reminders per the pickup protocol: popup 2h and 1h before the event
# start (= the driver's house-departure time for the house→house block).
_DEFAULT_REMINDERS = [
    {"method": "popup", "minutes": 120},
    {"method": "popup", "minutes": 60},
]


def _fmt_local(dt: datetime, tz: str) -> str:
    """Wall-clock pickup time in the calendar's timezone, e.g. '3:30 AM'.
    Naive datetimes are treated as UTC (how the booking layer stores them)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local = dt.astimezone(ZoneInfo(tz))
    return local.strftime("%I:%M %p").lstrip("0")


class CalendarError(RuntimeError):
    pass


def _credentials(settings):
    """Calendar credentials: prefer OAuth user creds (can invite attendees),
    fall back to the service account (cannot invite). Refreshes an expired OAuth
    access token in place (the refresh_token persists)."""
    if settings.GOOGLE_OAUTH_TOKEN_FILE:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(
            settings.GOOGLE_OAUTH_TOKEN_FILE, _SCOPES
        )
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        return creds
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
    )


def _service():
    """Cached Google Calendar v3 service, or None when simulated/unconfigured."""
    global _service_cache
    settings = get_settings()
    if not settings.calendar_live:
        return None
    if _service_cache is not None:
        return _service_cache
    from googleapiclient.discovery import build

    creds = _credentials(settings)
    _service_cache = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service_cache


def _event_body(
    *,
    summary: str,
    description: str,
    location: str,
    start: datetime,
    end: datetime,
    tz: str,
    attendees: list[str] | None,
    reminders: list[dict] | None,
) -> dict:
    """Compose the Google Calendar event body (pure — no API calls)."""
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "reminders": {
            "useDefault": False,
            "overrides": reminders if reminders is not None else _DEFAULT_REMINDERS,
        },
    }
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]
    return body


def upsert_event(
    *,
    summary: str,
    description: str,
    location: str,
    start: datetime,
    end: datetime,
    tz: str | None = None,
    attendees: list[str] | None = None,
    reminders: list[dict] | None = None,
    event_id: str | None = None,
) -> str | None:
    """Create or update a house→house calendar event spanning [start, end].
    Returns the event id (or a simulated one). Returns the prior id and logs on
    failure — never raises to the caller."""
    settings = get_settings()
    svc = _service()
    if svc is None:
        return event_id or f"SIM-EVT-{uuid.uuid4().hex[:18]}"
    body = _event_body(
        summary=summary,
        description=description,
        location=location,
        start=start,
        end=end,
        tz=tz or settings.CALENDAR_TIMEZONE,
        attendees=attendees,
        reminders=reminders,
    )
    try:
        cal = settings.GOOGLE_CALENDAR_ID
        # sendUpdates="all" so attendees (dispatcher + driver) are notified; the
        # protocol notes that modifying attendees on an existing event can fail,
        # so the full attendee list is re-sent on every patch.
        if event_id:
            ev = svc.events().patch(
                calendarId=cal, eventId=event_id, body=body, sendUpdates="all"
            ).execute()
        else:
            ev = svc.events().insert(calendarId=cal, body=body, sendUpdates="all").execute()
        return ev.get("id")
    except Exception as e:  # network / auth / API — best-effort
        logger.warning("calendar upsert failed: %s", e)
        # Drop the cached service so the next call rebuilds it — recovers after a
        # rotated OAuth token (e.g. re-consent) without a process restart.
        global _service_cache
        _service_cache = None
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
    pickup_time: datetime | None = None,
    tz: str = "America/Denver",
) -> dict:
    """Compose the summary/description/location for a ride event, per the pickup
    protocol: title `🚗 Pickup [Client] [real pickup time] — [Origin] → [Dest]`,
    with the real pickup time also in the description so the block's house→house
    span is never confused with the actual pickup."""
    name = client_name or "Guest"
    when = f" {_fmt_local(pickup_time, tz)}" if pickup_time else ""
    route = f"{pickup} → {dropoff}"
    summary = f"🚗 Pickup {name}{when} — {route}"

    parts = []
    if pickup_time:
        parts.append(f"Pickup{when}")
    parts.append(route)
    if flight:
        parts.append(f"Flight {flight}")
    if fare:
        parts.append(f"Fare ${round(fare)}")
    if phone:
        parts.append(f"Phone {phone}")
    if notes:
        parts.append(notes)
    return {
        "summary": summary,
        "description": "\n".join(parts),
        "location": pickup,
    }
