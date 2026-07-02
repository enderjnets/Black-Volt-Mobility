# Featured events — setup

The events module scans big Denver events daily, lets the owner approve them into public
landing pages, and auto-drafts social posts. It runs on two free developer API keys.

## API keys

Both keys go in the **gitignored `.env`** (never commit them). With neither key the daily
scan is a harmless no-op and the dashboard shows an empty state.

### Ticketmaster Discovery  ✅ already provisioned
- App **`enderjnets-App`** at <https://developer.ticketmaster.com> (Approved: 5000 req/day,
  5 req/s — far above one scan/day).
- Env var: `TICKETMASTER_API_KEY` (the app's **Consumer Key**).
- Covers Ticketmaster venues (Empower Field, Ball Arena, Coors Field, Fiddler's Green) and,
  in practice, many Red Rocks shows too.

### SeatGeek  ⏳ still to create (recommended)
- Create a free app at <https://seatgeek.com/account/develop> → copy the **Client ID**.
- Env var: `SEATGEEK_CLIENT_ID`.
- SeatGeek is the broadest source and reliably includes Red Rocks (sold via AXS). Until it's
  added the scanner runs Ticketmaster-only, which already covers the main watchlist venues.

## Config knobs (optional, in `.env`)
| Var | Default | Meaning |
| --- | --- | --- |
| `EVENTS_MIN_SCORE` | `0.6` | Keep non-watchlist events only if SeatGeek popularity ≥ this (0–1). |
| `EVENTS_SCAN_ENABLED` | `true` | Set `false` to disable the daily job. |
| `EVENTS_BASE_LAT` / `EVENTS_BASE_LNG` | Aurora base | Origin for the "X mi from base" ranking. |

## Applying keys
1. Add the vars to `.env` at the repo root (compose reads them via `${VAR:-default}`).
2. `docker compose up -d backend` (recreates the container so it picks up the new env).
3. In the dashboard → **Events**, click **Scan now** to populate suggestions immediately;
   otherwise the scheduler runs daily at 06:00 America/Denver.

## Before launch (owner)
- Review the curated venue copy in `backend/app/services/venue_profiles.py` (drop-off/pickup
  spots, nearby bars & restaurants) and tweak any wording.
- Approve your first event (e.g. **Ed Sheeran — Empower Field 2026**) and confirm the public
  page, the home "Upcoming events" strip, and the two drafted social posts in **Social**.
