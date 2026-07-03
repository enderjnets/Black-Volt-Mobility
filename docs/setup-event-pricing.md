# Event pricing & competitive research — setup

This covers the per-event pricing added in **v0.65.0**: event/night/wait fees, round-trip
booking, and the Uber competitive-research tool. Everything works out of the box; the only
optional piece is the live price scraper.

## What's automatic

- **Event fees.** Set them per event in the dashboard (`/dashboard/events` → Events tab →
  *Event pricing*): event fee, night fee + cutoff, wait fee/hour, expected show length.
  Any ride whose pickup **or** dropoff is the venue, on the event's date, gets these fees —
  no matter how it was booked.
- **Round trip.** Customers book it from the event page or `/book` (round-trip toggle). One
  prepaid Square charge covers both legs. The dashboard suggests a total; you can override it
  in the *Round trip price* field (leave blank to use the suggestion).
- **Night fee** applies automatically when the show is expected to let out at/after the
  cutoff (default `21:00`, Denver time).

## Tuning the Uber Black formula (no deploy)

The research tool estimates Uber fares from published Denver rates when the live scraper
isn't running. Adjust these in the VPS `.env` and restart the backend:

```
UBER_BLACK_BASE=15
UBER_BLACK_PER_MILE=5
UBER_BLACK_PER_MINUTE=0.55
UBER_BLACK_BOOKING_FEE=3
UBER_BLACK_MINIMUM=35
UBER_SUV_MULTIPLIER=1.25
```

Re-check these against Uber's current Denver Black pricing every few months.

## Optional: live price scout (Playwright)

The `pricing-scout` container reads live Uber prices from uber.com. It's **off by default**
(heavy image, and uber.com may block a datacenter IP). Research works without it via the
formula above — the scout only upgrades "estimate" rows to "live".

To enable it:

1. Pick a strong shared secret and put it in the VPS `.env` (never commit it):
   ```
   PRICING_SCOUT_SECRET=<random-secret>
   PRICING_SCOUT_URL=http://pricing-scout:8100/scrape
   ```
2. Build and start the profile-gated service:
   ```
   docker compose --profile scout up -d --build pricing-scout
   ```
3. Restart the backend so it picks up the new env: `docker compose up -d backend`.

The scout is internal-network only, holds no Uber credentials, and never raises — if a scrape
fails for any reason (captcha, layout change, IP block), that origin silently falls back to
the formula. Rows in the research table are marked `●` (live) or `○` (estimate).

To turn it off again, clear `PRICING_SCOUT_URL` in `.env` and restart the backend; you can
stop the container with `docker compose --profile scout down`.

## Migration

`0038_event_pricing` adds the pricing columns to `events` and the round-trip linkage
(`return_ride_id`, `is_return`) to `rides`. It runs with `alembic upgrade head` on deploy.
