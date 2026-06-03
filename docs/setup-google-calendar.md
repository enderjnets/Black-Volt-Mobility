# Setup: Google Calendar (scheduled rides → Black Volt calendar)

Scheduled rides are pushed to the **Black Volt Google Calendar**
(`blackvoltmobility@gmail.com`) as real events (title, location, reminder).
A **service account** does the writing; you share your calendar with it. Until
configured, `CALENDAR_SIMULATED=true` makes calendar writes a no-op (the booking
flow still works), and a fake `SIM-EVT-…` id is stored.

## What it does

- Booking a **scheduled** ride (with a date/time) → creates a calendar event.
- Cancelling / no-show → removes the event.
- Best-effort: a calendar/Google outage never blocks a booking.

## 1. Create the service account (Google Cloud Console — your action)

1. https://console.cloud.google.com → project **black-volt-mobility** (same as
   Maps / OAuth).
2. **APIs & Services → Library** → enable **Google Calendar API**.
3. **APIs & Services → Credentials → Create credentials → Service account**.
   Name it `black-volt-calendar`. No roles needed. Create.
4. Open the service account → **Keys → Add key → Create new key → JSON** →
   download the JSON. **Copy the service account email** (looks like
   `black-volt-calendar@black-volt-mobility.iam.gserviceaccount.com`).

## 2. Share your calendar with the service account (your action)

1. In **Google Calendar** (as `blackvoltmobility@gmail.com`) → Settings →
   **Settings for my calendars** → your calendar → **Share with specific people**.
2. Add the **service account email** with permission **"Make changes to events"**.
3. On the same settings page, copy the **Calendar ID** (for the primary calendar
   it's just `blackvoltmobility@gmail.com`).

## 3. Activate (the agent does this with your JSON + calendar id)

On the ROG: put the JSON at `~/Black-Volt-Mobility/secrets/gcal-sa.json`
(gitignored, mounted into the backend at `/secrets`), then in `.env`:

```
CALENDAR_SIMULATED=false
GOOGLE_CALENDAR_ID=blackvoltmobility@gmail.com
GOOGLE_SERVICE_ACCOUNT_FILE=/secrets/gcal-sa.json
CALENDAR_TIMEZONE=America/Denver
```

Rebuild + backfill the existing upcoming rides:

```bash
docker compose up -d --build backend
docker compose exec -T backend python -m app.scripts.sync_calendar
```

New scheduled rides then appear in your calendar instantly. Cancelling removes them.
