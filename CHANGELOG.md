# Changelog

## v0.21.0 — 2026-06-08 — Multi-driver onboarding (Phase A): access list + per-driver workspaces

Lets the owner invite friends (other drivers) to use the platform for feedback. Mirrors Eko AI Realtors' allow-list-gated sign-in, adapted to multi-tenant (each driver = their own tenant). Phase B (per-driver Square OAuth) is next.

**Access list (DB-backed).** New `allowed_users` table (migration `0011_allowed_users`): `email` (unique), `role` (`admin` super-admin / `driver`), `active` toggle, `tenant_id` (filled on first sign-in), `name`, `added_by`. `services/auth.resolve_user_access` resolves a verified Google email with precedence env `GOOGLE_ADMIN_EMAILS` → active `allowed_users` row → denied. Bootstrap admins are seeded + pinned (immutable) on startup (`_seed_admin_users`).

**Allow-list-gated Google sign-in + auto-provisioning.** `POST /auth/login/google`: an allow-listed (active) email signs in as the **owner of their own tenant**, which is **auto-provisioned on first login** (`tenancy.create_tenant_for` → fresh tenant + default RateConfig, unique slug). Non-listed / deactivated emails fall back to passenger (the dashboard rejects them). The owner password login is the super-admin master key. Sessions carry an `adm` flag; `me` exposes `is_admin`.

**Admin Team panel.** New `GET/POST/PATCH/DELETE /api/v1/team` (mounted under a new `require_admin` dep) to list, add, activate/deactivate, and remove drivers — with lockout guards (env-pinned admins immutable, can't deactivate/remove the last admin). Frontend: `components/bv/dash/Team.tsx` + `/dashboard/team` route + `lib/team.ts`; the **Team** nav item (sidebar + mobile More sheet) shows only for `is_admin`; the shell header now shows the real signed-in identity + role. New i18n keys (`dash.nav.team`, `dash.role.*`, `dash.team.*`) in EN + ES.

**Isolation.** Every query already scopes by `resolve_tenant_id`; with each driver's token carrying their own `tid`, drivers see only their own rides/clients/stats/settings. Covered by a dedicated isolation test (driver A never sees tenant B's data).

128 backend tests pass (new `test_team_onboarding.py`: gating, auto-provision, isolation, inactive-denied, Team CRUD + last-admin guard); `ruff` + `tsc` + `next lint` clean; no autogenerate drift. Production env already had `AUTH_ENABLED=true` + `GOOGLE_CLIENT_ID` + `GOOGLE_ADMIN_EMAILS`.

## v0.20.2 — 2026-06-08 — Dashboard real metrics: revenue, next-pickup countdown, weekly earnings

The owner reported three wrong/placeholder dashboard figures. Decisions: revenue = **paid** rides only, attributed to the **ride's service day** (`scheduled_at`, fallback `created_at`). No cost model → "profit" = gross paid fares.

**1. "Revenue today" was wrong ($480 with 0 rides today).** `stats()` counted `paid AND date(paid_at)==today`, so old rides marked paid today inflated it. Now: `paid AND date(coalesce(scheduled_at, created_at))==today` (`backend/app/services/dashboard.py`).

**2. "Next pickup" only showed `HH:MM`.** Now shows a countdown (`fmtCountdown` → "5d 2h" / "2h 30m" / "12m" / "Now") as the value, with the date + time + client as the sub (reusing `fmtWhen`). Backend already returned `next_pickup.at`.

**3. "This week" chart was rolling-7-days of ride counts.** Now it's the current **Monday→Sunday** week, graphing **earnings** (sum of paid fares per service day), with a new `week_total` shown above the chart. Empty state when the week's total is $0.

Also removed the fabricated `+18%` / `+2 vs yesterday` KPI sub-deltas. New i18n keys `dash.next.now`, `dash.week.total` (EN+ES). Frontend: `Overview.tsx`, `lib/dashboard.ts` (`DashStats.week[].revenue` + `week_total`). 121 backend tests pass (added a paid-revenue test; `test_stats_shape` updated for the new shape); `tsc` + `next lint` clean. No migration.

## v0.20.1 — 2026-06-08 — Fix: dashboard "Today's rides" no longer shows old completed rides

The owner reported the dashboard's **Today's rides** panel showing rides that weren't from today.

Root cause (reproduced live): on a day with **no rides scheduled**, `Overview` (`frontend/components/bv/dash/Overview.tsx`) fell back to `const pick = (todays.length ? todays : rides).slice(0, 6)` — with `todays` empty it listed **all** rides ascending by `scheduled_at`, i.e. the 6 **oldest completed** rides (weeks ago), under the "Today's rides" title.

- When there are rides today → show the full day (unchanged), titled **Today's rides**.
- When there are none → show the next **upcoming** rides instead (future + still-open status, excluding completed/cancelled/no-show), titled **Upcoming rides** / **Próximos viajes**. Never the old completed ones.
- New i18n key `dash.upcomingRides` (EN + ES). Frontend-only, no backend, no migration.

## v0.20.0 — 2026-06-08 — Wider client names, smart route prefill, one-tap Navigate

Three driver-facing UX improvements requested by the owner.

**1. Rides list — Client column rebalanced (not truncated).** The desktop grid's Client
column was a fixed `130px`, so long names got an ellipsis (v0.19.1). The owner wanted the
opposite: more room for the name. The shared `RideRow` grid (`Overview.tsx`) and the header
(`Rides.tsx`) now use `minmax(150px, 1.2fr) minmax(0, 1.4fr) …` — Client is flexible and ~2–3×
wider, Route shrinks to give it the space. Ellipsis stays only as a fallback for extreme names.

**2. Add ride — smart route prefill (hybrid) + Swap.** Picking a client from the name
autocomplete now also prefills the route, without overwriting anything already typed:
- **pickup** = the client's saved `home_address` if set, else the most-frequent non-airport
  address in their ride history.
- **drop-off** = the most-frequent airport-like address in their history, else
  Denver International (DEN) by default for a brand-new client.
- Inference is computed in the frontend from the existing `GET /clients/{id}` history
  (`inferRoute` in `lib/dashboard.ts`) — no new endpoint.
- A **Swap** button flips pickup ↔ drop-off in one tap (return trip).

**3. Clients — saved Home address.** New nullable `clients.home_address` column
(migration `0010_client_home_address`), editable on the client profile (`ClientDetail`),
surfaced in `client_detail`, and accepted by `ClientCreate`/`ClientPatch`. Feeds the prefill above.

**4. Rides — one-tap Navigate to pickup.** A Navigate button (in each upcoming/active row —
desktop nav column + mobile card — and in the ride detail drawer) opens the maps app with
driving directions to the pickup via a universal Google Maps URL (`lib/maps.ts`), so the
driver never types the address. Works on phone (native app) and desktop (web).

Backend: 1 nullable column + migration, no data change. Frontend: shared `RideRow`, `AddRide`,
`ClientDetail`, new `lib/maps.ts`. i18n EN+ES for the new labels. 120 backend tests pass
(was 119 + a `home_address` round-trip test); `tsc` + `next lint` clean; no autogenerate drift.

## v0.19.1 — 2026-06-08 — Fix: long client names no longer overlap the route

The owner reported that a very long client name overflowed its column and overlapped the
adjacent **Route** info (pickup → drop-off). It happened in both `/dashboard/rides` and the
main dashboard's "today's rides", which share the same `RideRow` component
(`frontend/components/bv/dash/Overview.tsx`).

Root cause: the client-name cell used `white-space: nowrap` without
`overflow: hidden` + `text-overflow: ellipsis`, so a long name spilled out of its fixed
130px column (desktop) / pushed the fare (mobile card) into the route space.

- Truncate the client name with an ellipsis in both the desktop grid row and the mobile
  card (matches the repo's standard inline truncation pattern).
- Secondary: the desktop route pickup (`{r.from}`) was pinned with `flex-shrink: 0`; it now
  shrinks + truncates like the drop-off, so a row with two long addresses degrades cleanly.

CSS-only change to a shared component — no backend, no migration, no i18n.

## v0.19.0 — 2026-06-08 — Clients saved automatically + name autocomplete + CRUD

The owner reported that adding a ride with a new client never saved that client to the
CRM. Root cause: `booking.create_ride` only stored `passenger_name`/`passenger_phone` as
loose text on the ride and left `client_id = NULL` — the person never became a `Client`
row, so they never appeared in Clients or accrued rides/spend. (The clients that did show
up only existed via passenger-portal Google sign-in.)

Three connected changes:

- **Persist on create** — new `find_or_create_client_by_contact` (in
  `backend/app/services/tenancy.py`): when a ride is created without a `client_id` but with
  a name/phone, get-or-create a real `Client` (match by digits-only phone first, else exact
  name when no phone), fill missing fields without overwriting, and link the ride. Runs in
  the same transaction as the ride (`flush` → ride insert → one `commit`), so no orphan.
- **Name autocomplete** — `GET /clients/search` (tenant-scoped, ILIKE on name/phone/email,
  capped at 50 candidates → top 8 by ride count). Frontend `useClientSuggest` hook +
  dropdown (`ClientAutocomplete.tsx`) on the Add ride Full-name field (Manual + Smart):
  picking a client fills phone + language and links `client_id`; editing the name clears the
  link so a brand-new name becomes a new client.
- **CRUD** — `POST /clients` (Add-client modal on the Clients page) and
  `DELETE /clients/{id}` (delete from the client profile). Delete **preserves ride history**:
  it backfills `passenger_name`/`passenger_phone` onto each ride that lacks them, detaches
  `client_id`, then removes the client — rides and revenue survive.

TDD: 11 new tests in `backend/tests/test_client_persist.py` (persist+dedup, search,
create, delete-preserves-history, staff-only); full suite 119 passing. Frontend `tsc` +
`next lint` clean. Verified end-to-end with Playwright on the local stack (autocomplete
pick fills phone, create+delete round-trip, count 42→41 after delete). Multi-tenant
scoping and FastAPI route ordering (`/clients/search` before `/clients/{id}`) reviewed.

## v0.18.1 — 2026-06-07 — Responsive: dashboard looks like a phone app on any screen

On an unfolded Galaxy Z Fold (~884px, under the 900px breakpoint) the dashboard showed
the mobile bottom-tab layout but the content stretched edge-to-edge (very wide form
fields) — "not like a phone app". Fix is CSS-only in `frontend/app/globals.css`'s
`@media (max-width: 899px)`:

- `.bv-mobile-pad` is now a centered app column (`flex: 0 1 720px !important; margin-inline:
  auto`) instead of `flex:1` edge-to-edge. Normal phones (<720px) still fill the width;
  desktop (≥900px, with sidebar) is unchanged.
- `.bv-mobile-pad * { min-width: 0 }` kills horizontal scrolling on phones: `min-width:auto`
  on flex/grid items (e.g. the Add ride 2-column field rows like Date | Pickup time) was
  resolving to min-content and overflowing the viewport. On non-flex/grid elements this is
  already 0, so it only affects the items that would otherwise overflow.

Verified with Playwright at 884px (centered column) and 390px (full width, 0 horizontal
overflow). No PWA manifest was ever present, so this was a responsive-layout fix, not PWA.

## v0.18.0 — 2026-06-07 — Calendar OAuth: pickups post again + real invites

Since v0.16.0 **no new pickup landed on the `blackvoltmobility@gmail.com` calendar**.
Root cause (confirmed in prod logs): adding Margie+Ender as `attendees` made Google
reject the whole event — `403 forbiddenForServiceAccounts: "Service accounts cannot
invite attendees without Domain-Wide Delegation of Authority."` (a service account on
a personal Gmail cannot invite). v0.16.0's caveat understated it: it broke sync entirely.

- **Fix + graceful degradation** (`config.calendar_can_invite`, `booking.sync_ride_to_calendar`):
  attendees are only attached when OAuth owner creds are configured. Without OAuth the
  event is created **without** attendees (no 403) — so pickups post again immediately.
- **OAuth owner credentials** (`config.GOOGLE_OAUTH_TOKEN_FILE`, `calendar._credentials`):
  when an authorized-user token for `blackvoltmobility@gmail.com` is mounted, the backend
  acts as the owner and **invites Margie + Ender per event** (`sendUpdates="all"`), with the
  cached service auto-refreshing the access token. One-time setup via the new
  `app/scripts/calendar_oauth_setup.py` (consent screen must be **"In production"** so the
  refresh token doesn't expire after 7 days). `calendar_live` now accepts OAuth **or** SA.
- **Reminders** are now **popup 120 and 60 minutes** before the event start — i.e. 2h and 1h
  before the driver's house-departure time (the house→house block already subtracts the
  deadhead from `DISPATCH_ADDRESS` = 6000 S Fraser St).
- **Self-heal**: a failed calendar call drops the cached service so a rotated OAuth token is
  picked up without a restart. Setup script asserts a `refresh_token` was issued; `.gitignore`
  hardened against committing `gcal-oauth.json` / `client_secret*.json`.
- Backfill the rides that failed under the 403: `docker compose exec -T backend python -m app.scripts.sync_calendar`.

## v0.17.0 — 2026-06-06 — Overdue rides: confirm the pickup happened

A scheduled ride whose pickup time has passed no longer lingers as "Upcoming".

- **Backend**: `_ride_out` exposes a derived `overdue` flag (`booking.is_overdue`:
  scheduled in the past + still active). Paid rides whose time has passed
  auto-complete: `booking.complete_if_overdue_paid` fires on payment capture
  (`payments.capture_payment`) and on the manual paid toggle (`patch_ride`), and
  `booking.reconcile_overdue_paid` is a lazy idempotent sweep run at the top of
  `list_rides` for rides settled in advance. Manual completion of an unpaid past
  ride already worked via `PATCH status=completed`.
- **Frontend**: an amber "Overdue" `StatusPill` (new `RideUiStatus` member, fed by
  `RideRow.overdue` through `apiToUiRide`) shows in the rides list — but filtering
  still uses the underlying bucket, so overdue rides stay under "Upcoming". The
  ride detail shows an overdue notice and a one-tap **"Confirm pickup completed"**
  button (`changeStatus("completed")`, skipping the en-route step). New i18n keys
  `dash.status.overdue`, `dash.ride.confirmPickup`, `dash.ride.overdueNotice` (EN/ES).

## v0.16.0 — 2026-06-06 — Manual update + pickup-protocol calendar events

A saved ride can now be edited **by hand**, and every scheduled ride lands on Google
Calendar shaped like the dispatch **pickup protocol** (house→house block, real pickup
time in the title, dispatcher + driver invited).

- **Frontend**: the ride detail gains a **"Manual update"** button beside "Smart
  update". It opens the same editable form (`RideDetail.tsx` `mode === "manual"`,
  reusing the Smart review render, `EditField`, `changesFrom`, `previewRideUpdate`
  and `applyUpdate`) pre-filled with the ride's current values, skipping the
  screenshot/AI capture step. Edits re-quote the fare, surface scheduling
  conflicts, and on apply re-sync the calendar via the existing
  `PATCH /v1/rides/{id}` → `sync_ride_to_calendar`. New i18n key
  `dash.ride.manualUpdate` (EN/ES).
- **Backend (calendar, pickup protocol)**:
  - Event title `🚗 Pickup [Client] [real pickup time] — [Origin] → [Destination]`
    with the real pickup time also in the description (`calendar.build_ride_event`).
  - **House→house block**: `booking.sync_ride_to_calendar` now spans
    `pickup − deadhead(base→pickup)` to `pickup + trip + return(dropoff→base) +
    buffer`, deadhead/return measured with Google Maps (`booking._deadhead_window`
    + pure `house_to_house_window`). Falls back to the passenger trip when no
    dispatch base is set.
  - Attendees (`CALENDAR_INVITEES`) added with `sendUpdates="all"`; reminders are
    now **popup 30 and 60 min** before (`calendar.upsert_event` rebuilt around an
    explicit `[start, end]` window + pure `_event_body`).
  - New config: `DISPATCH_ADDRESS`, `CALENDAR_INVITEES`, `CALENDAR_BLOCK_BUFFER_MIN`.
- **Deferred** (separate work): Gmail draft to the dispatcher, Google Sheets CRM
  row, and the client confirmation message.
- **Caveat**: a service account on a personal Gmail calendar records attendees but
  may not email invites without domain-wide delegation; `sendUpdates="all"` + the
  full attendee list are re-sent on every patch.

## v0.15.1 — 2026-06-06 — Fix: public "Your Driver" link 404'd (slug regression)

After v0.15.0 wired the public profile to a live `GET /tenants/{slug}` lookup, the
web nav "Your Driver", the mobile tab bar, and the landing CTA still pointed at the
old demo URL `/d/ender` — a slug that doesn't exist — so they rendered
"Profile not found." (the real tenant slug is `black-volt`).

- **Fix**: single source of truth `PUBLIC_PROFILE_SLUG = "black-volt"` in
  `lib/tenant.ts`; `WebShell.tsx`, `ClientTabBar.tsx`, `Landing.tsx` and the
  `Profile` default now use it. The tenant slug itself is unchanged (it's the
  tenancy fallback key).
- **Quality**: a genuinely unknown profile slug now shows a branded not-found
  block with a "Book a ride" CTA instead of bare text.
- Frontend-only; no backend/DB change.

## v0.15.0 — 2026-06-05 — Settings: brand & public profile editor (live)

The dashboard Settings page is now a real editor backed by the Tenant, and the
public profile at `/d/{slug}` renders the owner's actual data.

- **Backend**: new `GET/PUT /tenant/settings` (staff-only, tenant-scoped) edit
  the brand/profile fields; `POST /tenant/logo` + `/tenant/photo` accept image
  uploads validated by **magic-byte sniffing** (not the client content-type),
  capped at 5 MB, written under `media/tenants/{tenant_id}/` with a
  server-generated versioned filename (no path traversal, no cross-tenant write).
  Public `GET /tenants/{slug}` returns a profile-safe payload (no email, no
  Square token, no ids) with computed `rides_total` (completed) + `years_active`.
  New Tenant columns `bio, website, brand_color, logo_path, photo_path, rating,
  since_year` (migration `0009_tenant_settings`). `/media` is served by a
  StaticFiles mount (Next.js `/media/*` rewrite → backend; Docker named volume
  `blackvolt-media` persists uploads). Tests in `test_tenant_api.py`.
- **Frontend**: `Settings.tsx` editor (mirrors the Rates layout) — business
  profile fields, brand accent swatches + custom color, logo/hero uploaders with
  preview, Save (dirty/saved/error states), read-only Square + notifications
  status cards, and a "View public profile" link. `Profile.tsx` now fetches
  `GET /tenants/{slug}` and renders real brand/stats with loading + not-found
  states. `lib/tenant.ts` client helpers. i18n EN+ES (`dash.settings.*`).

## v0.14.0 — 2026-06-05 — Client detail (CRM): tap a client to view + edit + act

Client rows in the Clients section are now tappable and open a full detail drawer.

- **Backend**: `GET /clients/{id}` (`dashboard.client_detail`) returns the profile
  + stats (rides_count, lifetime_spend, tier, last_ride_at, member-since) + the
  client's full ride history. `PATCH /clients/{id}` (`update_client`, `ClientPatch`)
  edits name/phone/email/language (lang reuses the EN/ES normalizer). New
  `Client.lang` preferred-language column (migration `0008_client_lang`), preferred
  over the ride-derived language. Both staff-only, tenant-scoped (no cross-tenant
  leakage). Tests in `test_clients_api.py`.
- **Frontend**: `ClientDetail.tsx` drawer (mirrors RideDetail) — profile header +
  tier, 2×2 stats, inline-editable profile with Save, and the ride history (each
  ride opens its own RideDetail). "New ride for this client" opens `/dashboard/add`
  pre-filled (name/phone/lang via query params). Client rows are now clickable;
  search also matches phone/email. i18n EN+ES (`dash.client.*`).

## v0.13.1 — 2026-06-04 — Smart extraction reads the right pickup date

A Demetra ride added "for today" landed on **Jul 4**: the vision model returned
`"date": "Jul 4"` — it had grabbed a date from the flight itinerary, not the
pickup day. (The ride showed in the list but not on June's calendar because it
was a month ahead.)

- `smart._prompt()` now anchors `EXTRACT_PROMPT` to **today's date** (driver
  timezone, `CALENDAR_TIMEZONE`) and tells the model the `date` is the customer's
  PICKUP date — resolving relative dates ("today/tomorrow/this Friday",
  "hoy/mañana/viernes") and picking the nearest sensible date when only a day is
  given. No model/provider change.

## v0.13.0 — 2026-06-04 — Reservations that silently failed now save (422 + false success)

A ride added for a client never appeared: `POST /rides` returned **422** (the AI
extracted "United Airlines UA 2766" — over the 20-char `flight_number` limit) but
`AddRide.submit` swallowed the error and showed "Reservation created" anyway.

- **Backend tolerates real/AI data**: `flight_number` limit 20→**40** (model +
  `RideCreate`/`RideEdit`; migration `0007_flight_len` widens the column). `lang`
  is **normalized** to `EN`/`ES` via a validator instead of failing when the AI
  returns "Spanish"/"English". `smart._coerce` also normalizes lang + trims flight,
  and `EXTRACT_PROMPT` now asks for the flight **code** only and a 2-letter lang.
- **No more false success**: `AddRide.submit` only shows the success screen when a
  real ride id comes back; otherwise it surfaces the actual error (the FastAPI
  `detail`, with 422 arrays normalized to a readable string via `fmtApiDetail` —
  never rendering the raw object).
- **Calendar** no longer shows cancelled / no-show rides.

## v0.12.2 — 2026-06-04 — Smart extraction: survive transient network blips

Fixes a 500 ("Couldn't reach the AI service") when one of several screenshots hit
a transient TLS error (`SSLV3_ALERT_BAD_RECORD_MAC`) mid-call.

- The raw `ssl.SSLError` escaped the handlers (which only caught `httpx.HTTPError`)
  and crashed the request. `llm.minimax_vlm_understand` now wraps **any** transport
  failure as `LLMError`; `smart._vlm_one` catches broadly and retries; the gather
  uses `return_exceptions=True`; and `extract_reservation`'s safety net catches
  `Exception` so extraction **never** 500s — worst case returns all-null and the UI
  asks for manual entry. One bad image no longer sinks the others.
- Regression test: a VLM raising `ssl.SSLError` degrades to all-null.

## v0.12.1 — 2026-06-04 — Smart extraction: cross-device reliability + visible errors

Fixes a report where a screenshot returned "AI found 0 of 9" with no explanation.

- **Frontend no longer swallows extraction errors.** `runExtract` (Add ride) and
  the Smart-update flow (RideDetail) now surface the real reason — unsupported
  format, image too large, or service unreachable — and "couldn't read it, add
  manually" when the model reads nothing, instead of a blank "0 found".
- **In-browser image normalization** (`lib/smart.ts normalizeImage`): every
  screenshot is downscaled (long edge ≤2200px) and re-encoded to PNG/JPEG via
  canvas before upload — consistent from Android/iPhone/Mac/Linux, under the size
  limit, vision-friendly. Undecodable formats (e.g. HEIC on Chrome) raise a clear
  "convert to PNG/JPG" message.
- **Backend diagnostics + prompt**: `services/smart.py` logs the (truncated) VLM
  response and warns when it returns no fields; `EXTRACT_PROMPT` now tells the
  model to ignore phone status bars / app chrome and extract partial data.
- Backend accepts `image/heic`/`image/heif` as a safety net (clearer than a drop).

## v0.12.0 — 2026-06-04 — Smart update: change a ride from screenshots

A client's change of plans → drop the screenshots on the ride and the system
applies the change, checking for schedule clashes first.

- **PATCH /rides/{id}** now edits the ride itself (pickup/dropoff/time/pax/flight/
  notes/fare), not just status/payment. Route or schedule edits **re-quote** the
  fare and **move the Google Calendar event** (`booking.apply_ride_update`).
- **Conflict detection** (`booking.find_conflicts`, `RIDE_BUFFER_MIN`=45): active
  rides whose window (± a travel/turnaround buffer) overlaps the new time.
- **POST /rides/{id}/preview-update** (staff, dry-run): re-quotes + reports
  conflicts without persisting — backs the diff + warning shown before applying.
- **RideDetail → "Smart update"**: drop the client's change screenshots → AI reads
  the new details → editable diff (changed fields tagged) → conflict warning
  (apply-anyway) → apply → a change-confirmation message you can copy or send by
  SMS/email/AI call (auto-send staged until Phase 7 comms).
- Client email now surfaced on ride detail (to pick the email channel).

## v0.11.1 — 2026-06-04 — Smart reservation: MiniMax Coding Plan vision

Adds the MiniMax **Coding Plan** (subscription, `sk-cp-` key) as a vision
provider, alongside the pay-as-you-go MiniMax-M3 path.

- `services/llm.py`: `minimax_vlm_understand` → `POST {host}/v1/coding_plan/vlm`
  (MiniMax-native: Bearer auth, `base_resp` status, one image per call).
- `services/smart.py`: `SMART_VISION_PROVIDER` selects `minimax_coding_vlm`
  (default — one VLM call per screenshot, merged into one reservation, newer
  images win, a failed image is skipped) or `minimax_anthropic` (MiniMax-M3, all
  images in one call). Both still degrade to manual entry on failure.
- config / compose / `.env.example`: `SMART_VISION_PROVIDER`, `SMART_VISION_HOST`.
- See `docs/setup-minimax-vision.md`.

## v0.11.0 — 2026-06-04 — Smart reservation: real AI from multiple screenshots

The Smart "Add reservation" tab now does real vision extraction (it used to only
work inside the design preview and otherwise fell back to a fake sample).

- **Vision LLM** (`services/llm.py`): thin `anthropic`-SDK client with a per-call
  `base_url`; `vision_complete` sends a text prompt + N base64 images in one
  message. Kimi/MiniMax only — never Anthropic OAuth.
- **Smart extractor** (`services/smart.py`): merges several screenshots of a
  client's SMS/WhatsApp/email into ONE reservation via **MiniMax-M3** (the only
  MiniMax model that reads images). `SMART_SIMULATED` (default) returns a
  deterministic sample so the flow works without a key/billing; best-effort —
  a vision failure degrades to manual entry, never blocks.
- **Endpoint** `POST /api/v1/rides/extract` (staff-only, multipart): 1–5 images,
  `image/*` only, ≤10 MB each.
- **Add ride → Smart**: pick/drag/paste **multiple** screenshots, remove or add
  before extracting; thumbnails + count; real extraction replaces the old
  `window.claude` browser path. A subtle "demo mode" note shows until the key
  is set.
- See `docs/setup-minimax-vision.md`.

## v0.10.0 — 2026-06-02 — Google Calendar sync for scheduled rides

Scheduled rides flow into the Black Volt Google Calendar.

- **Calendar adapter** (`services/calendar.py`): a Google service account (shared
  on `blackvoltmobility@gmail.com`) creates/updates ride events; simulated by
  default (`CALENDAR_SIMULATED`) so bookings work without Google. Best-effort —
  never blocks a booking.
- Booking a scheduled ride creates an event (title, pickup location, route/flight/
  fare/phone, 30-min reminder); cancelling removes it. `google_event_id` stored on
  the ride (migration `0006_ride_calendar`).
- **Add ride** now builds a real `scheduled_at` from its date + time fields, so new
  rides land on the app calendar **and** Google Calendar.
- `app/scripts/sync_calendar.py` backfills existing upcoming rides.
- See `docs/setup-google-calendar.md`.

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
