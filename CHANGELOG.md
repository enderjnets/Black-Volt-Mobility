# Changelog

## v0.9.0 — 2026-06-02 — Real history import + payment methods + Square auto-sync

Import the real business history and support every payment method, not just card.

- **Import** (`app/scripts/import_history.py`): upserts the recurring clients
  (Demetra, Rob, Michelle) and mirrors the real **Square payment history** into
  completed rides + captured payments (real amounts + dates, linked to clients).
  Read-only against Square (never charges); idempotent by `square_payment_id`.
- **Payment methods**: every ride has a `payment_method` (default **cash**) + a
  `paid` flag + `paid_at` (migration `0005_payment_method`). Square authorize/capture
  sets it to `square` automatically; the driver can switch a ride to
  Cash/Venmo/Zelle/Other and toggle paid from the ride detail.
- **Revenue & client spend now count all paid rides** (any method), not only
  captured Square payments.
- **Auto-sync**: a periodic run of the importer pulls new Square charges into the
  dashboard automatically (idempotent). Real-time webhook is a future upgrade.

## v0.8.0 — 2026-06-02 — Phase 4 — Driver dashboard on real data

The driver dashboard now runs on real backend data (was mock) and lets the driver
operate rides.

- **Backend**: `services/dashboard.py` + `GET /dashboard/stats` (today rides,
  revenue from captured payments, next pickup, 7-day bars, totals) and
  `GET /clients` (CRM with ride count, lifetime spend, tier, language). `GET /rides`
  now includes `client_name`; `GET /rides/{id}` includes the client + latest payment.
- **Overview / Rides / Calendar / Clients**: wired to real data with empty states.
  Calendar groups real rides by date on the actual current month.
- **Ride detail drawer**: tap a ride → full trip + client + payment; change status
  (en route → complete → cancel) and **capture the Square payment** when authorized.
- Rates & Insights were already live; Inbox stays mock until Phase 7.

## v0.7.0 — 2026-06-01 — Phase 3 — Square payments

Real card payments on the passenger booking flow, with the full authorize →
capture → refund lifecycle.

- **Frontend**: the `/book` payment step uses the **Square Web Payments SDK**
  (`SquareCard`) to tokenize the card in-browser — card data never touches our
  backend. Falls back to a simulated pay button when Square isn't configured.
- **Backend**: `services/payments_square.py` (async Square SDK, sandbox/prod) +
  `services/payments.py` orchestration + `Payment` model & migration
  `0004_payments`. Endpoints: `POST /payments` (authorize, holds funds),
  `POST /payments/{id}/capture` (staff), `POST /payments/{id}/refund` (staff),
  `GET /payments/config` (public Web SDK config).
- Authorizing a ride confirms it and stores the Square payment id.
- `PAYMENTS_SIMULATED` (default) fakes payment ids so the flow runs without
  Square; **sandbox** is live on the demo (test card `4111 1111 1111 1111`).
- See `docs/setup-square.md`.

## v0.6.0 — 2026-06-01 — Usage analytics (first-party Insights)

Own your usage data: a privacy-first, self-hosted event-tracking system + a driver
Insights dashboard. No third-party trackers; everything lands in our Postgres.

- **Tracking** (`lib/analytics.ts` + `AnalyticsTracker` in the root layout, so it
  covers portal + dashboard): `session_start`, `pageview`, `page_duration`
  (time-on-page via visibility/unload + sendBeacon), the booking funnel
  (`book_start → book_review → book_pay → book_confirmed`), and `sign_in`.
- **Privacy**: pseudonymous — a random `visitor_id` (localStorage) + per-tab
  `session_id`; **no raw IP** is stored; country comes from Cloudflare's
  `CF-IPCountry` header. No consent banner yet (anonymous data).
- **Backend**: `AnalyticsEvent` model + migration `0003_analytics`; `POST /track`
  (open, batched, accepts sendBeacon) and `GET /analytics/summary` (staff).
- **Insights page** (`/dashboard/analytics`): visitors, sessions, pageviews, avg
  time, pageviews-over-time, booking funnel with conversion, top pages, traffic
  sources (UTM + referrers), devices and countries; 7/30/90-day range.
- See `docs/setup-analytics.md`.

## v0.5.1 — 2026-06-01 — Address autocomplete + live fares in booking

Wired the live Google Maps backend (Phase 2) into the booking UI on both surfaces.

- **Address autocomplete**: Pickup/drop-off fields now suggest real addresses from
  Google Places (`/places/autocomplete`) with a debounced dropdown + keyboard nav.
  New reusable `AddressAutocomplete` (hook + dropdown) + web `AddressField`.
- **Live fares**: the passenger `/book` "Review route" step calls `/quote` and shows
  real distance, ETA and fare (replacing the mock $74 / 18.4 mi / 6 min); the amount
  flows into the pay + confirmation steps.
- **Dashboard**: the driver "Add ride" pickup/drop-off get the same autocomplete.
- Frontend-only; no backend changes.

## v0.5.0 — 2026-05-31 — Phase 2 — Booking core (route + pricing engine)

The booking backend: price any trip from its route and the tenant's configurable
fare engine, persist it as a ride, and edit the rates from the dashboard.

- **Models**: `Ride` (route, schedule, fare snapshot, status lifecycle) and
  `RateConfig` (per-tenant fares + surcharges). Both multi-tenant, migration
  `0002_booking`.
- **Pricing engine** (`services/pricing.py`, pure/unit-tested):
  `MAX(floor, base + miles·per_mile + min·per_minute)` + extra-stop, group and
  airport handling, weekend-late peak multiplier, loyalty discount.
- **Maps adapter** (`services/maps.py`): Google Distance Matrix + Places
  Autocomplete, with a deterministic **simulated** fallback (default) so the flow
  runs without billing. Flip live with `MAPS_SIMULATED=false` + a key.
- **API**: `POST /quote`, `GET /places/autocomplete`, `GET/PUT /rate-config`,
  `POST/GET/PATCH /rides`. Tenant-scoped; passengers see only their own rides.
- **Frontend**: Rates editor loads + saves the live engine; Add ride suggests a
  live quote and persists the reservation.
- See `docs/setup-google-maps.md`. 37 backend tests (pricing + maps + API).

## v0.3.0 — 2026-05-30 — Add ride (Manual + Smart) + SMS confirmation

Added the **"Add ride"** screen to the driver dashboard (`/dashboard/add`) plus an
auto-SMS confirmation notice on the passenger booking flow.

- **Manual mode**: bilingual reservation form (client · trip · flight/details) with
  a live reservation preview + suggested DEN flat fare.
- **Smart mode**: drop / paste (⌘V) / upload a screenshot → Claude **vision**
  extracts the details (`window.claude.complete` image block, mock fallback);
  AI-filled fields get a cyan "AI" tag, missing required fields are flagged amber
  with click-to-focus chips and a "found N of M" banner.
- **Confirmation message**: auto-generated SMS in the client's language with a
  send-now (auto) or copy (manual) choice.
- Sidebar "Add ride / Nueva reserva" item + topbar "New ride" both route here.
- Passenger booking confirmed step now shows "Confirmation sent by SMS".

## v0.2.0 — 2026-05-30 — Driver Dashboard kit (from Claude Design)

Implemented the **Driver Dashboard** UI kit as Next.js routes under a `/dashboard`
shell (sidebar + topbar), bilingual (EN default + ES), mock data.

- **Overview** `/dashboard`: KPI cards, AI assistant card, today's rides, weekly bars.
- **Rides** `/dashboard/rides`: filterable list + month/week **Calendar** toggle.
- **Clients** `/dashboard/clients`: CRM table with search + tier badges.
- **Inbox** `/dashboard/inbox`: SMS / AI call / AI chat threads, AI-call summary,
  AI-draft reply (`window.claude.complete` with mock fallback).
- **Rates** `/dashboard/rates`: editable rate engine + peak surge + live fare
  preview + brand-accent picker.
- Sidebar collapses to an icon rail under 900px.

## v0.1.0 — 2026-05-30 — Passenger Web kit (from Claude Design)

Implemented the **Passenger Web** UI kit from the Black Volt Mobility design
system as real Next.js routes, on the brand tokens, bilingual (EN default + ES),
with mock data. Later phases wire each screen to its real API.

- **Foundation**: full design tokens in `globals.css`, shared `Icon` (Lucide
  path data) + primitives (`Button`/`Pill`/`Card`/`Field`/`Toggle`/`Logo`/
  `GoogleG`), expanded i18n dictionaries, EV9 photography + logo assets, branded
  app icon.
- **Routes** under a `(web)` shell (sticky header nav + footer + floating AI
  chat + sign-in modal): `/` landing, `/book` booking flow, `/trips` live
  tracking + flight status, `/d/[slug]` public profile + QR, `/account`.
- AI chat uses `window.claude.complete` when present, else a mock fallback.

## v0.0.1 — 2026-05-29 — Phase 0 Bootstrap

- FastAPI + Next.js 14 + Postgres + Redis + Docker stack.
- Black Volt brand theme, bilingual shell, health endpoint, landing, version modal.
