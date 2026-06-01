# Usage analytics (first-party)

Black Volt tracks how people use the booking site so the owner can improve it —
**without any third-party tracker**. Every event lands in our own Postgres
(`analytics_events`), tenant-scoped, and is surfaced on the driver **Insights**
page (`/dashboard/analytics`).

## What's captured

| Event | When | Fields |
|---|---|---|
| `session_start` | first page of a tab session | referrer, UTM, device, country |
| `pageview` | every route change (portal + dashboard) | path |
| `page_duration` | leaving a page / tab hide / unload | path, duration_ms |
| `book_start` / `book_review` / `book_pay` / `book_confirmed` | booking funnel steps | (fare on confirm) |
| `sign_in` | successful portal sign-in | mode (google/demo) |

Each row also stores: `tenant_id`, `visitor_id`, `session_id`, `client_id`
(if logged in), `role`, `device`, `country`, `created_at`, free-form `props`.

## Privacy

- **Pseudonymous**: `visitor_id` is a random UUID in `localStorage`; `session_id`
  is a random per-tab id. There is **no login required** and **no PII** beyond
  what an authenticated session already carries.
- **No raw IP is ever stored.** Country (ISO-2) is read from Cloudflare's
  `CF-IPCountry` request header only.
- **No consent banner yet** (the data is anonymous). If the SaaS scales to many
  drivers / EU traffic, add a consent gate before `AnalyticsTracker` initializes.

## How it works

- **Frontend**: `frontend/lib/analytics.ts` batches events and sends them via
  `navigator.sendBeacon` (fallback `fetch` keepalive) to `POST /api/v1/track`.
  `frontend/components/bv/AnalyticsTracker.tsx` is mounted once in the root
  layout (`app/layout.tsx`), so it covers both the portal and the dashboard.
- **Backend**: `POST /api/v1/track` (open, ≤50 events/batch) and
  `GET /api/v1/analytics/summary?days=30` (staff only). Model
  `app/models/analytics.py`, aggregation in `app/services/analytics.py`.

## Inspecting the raw data

```bash
# on the ROG
docker exec blackvolt-db psql -U blackvolt -d blackvolt -c \
  "SELECT event_type, count(*) FROM analytics_events GROUP BY event_type ORDER BY 2 DESC;"
```

No configuration or keys are required — analytics is on by default.
