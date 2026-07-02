# Design — Featured events: scanner, landing pages & social posts

## Context

Black Volt Mobility wants to capture ride demand around **large Denver events** (stadium
concerts, Red Rocks shows, arena games). The owner's idea, using
`https://www.empowerfieldatmilehigh.com/events/detail/ed-sheeran-2026` as the first
target:

1. A **daily scanner** finds upcoming large events (preferably Empower Field at Mile
   High and Red Rocks, but any big Denver-metro event qualifies) and suggests them in a
   new **dashboard Events section**, ordered by date, venue, and proximity to the
   driver's home base (Aurora).
2. When the **admin approves** a suggestion, the platform generates a **public event
   landing page** with: artist/show info, photos, nearby bars & restaurants, best
   **drop-off spots before** the show and **pickup spots after**, and a prominent
   **booking CTA**.
3. Approval also generates **social posts** through the existing social engine — one
   **video** and one **photo** post, adapted to the event — entering the existing
   draft→approve→publish flow (edit / delete / regenerate / publish all work as today).
   More posts can be generated on demand.
4. The **public home page** gets an "Upcoming events" section linking to the event
   landing pages.

**Expected outcome:** a rider searching "ed sheeran denver ride" (or landing from a
social post) reaches `/events/ed-sheeran-empower-field-2026`, sees everything they need
for the night (show info, where to eat, where we drop them off, where we pick them up),
and books a prepaid ride at the flat metro rate.

## Decisions (confirmed with the user)

- **Data source — hybrid:** **SeatGeek API** is the base (aggregates all Denver venues,
  including Red Rocks which sells via AXS and is missing from Ticketmaster);
  **Ticketmaster Discovery API** enriches events at TM venues (official links, better
  images). Both free-tier keys, owned by the owner.
- **Booking CTA — prefilled normal ride (MVP):** the landing deep-links to `/book` with
  dropoff=venue, event date, suggested arrival time (~1h before showtime) and
  `utm_campaign=event-<slug>`; a second CTA books the **post-show pickup**
  (pickup=venue). No changes to the booking engine. Rides are **already prepaid** at
  booking via Square (`book_start→review→pay→confirmed` funnel) — nothing new needed.
- **Pricing — current zone engine untouched:** Empower Field and Red Rocks (Morrison)
  fall in the `denver_metro` flat zone = **$120/leg**. The landing sells it as
  "Flat $120 — no event-night surge".
- **Venue watchlist:** always include **Empower Field, Red Rocks, Ball Arena, Coors
  Field, Fiddler's Green**; additionally **any Denver-metro venue** whose event beats a
  configurable popularity threshold (SeatGeek `score`).
- **Event pages are DB-driven** (unlike the hardcoded `seoRoutes.ts` rides pages):
  approving in the dashboard publishes the landing instantly, **no deploy per event**.
- **Venue knowledge is curated per-venue, not per-event:** drop-off/pickup spots, bars &
  restaurants and traffic tips belong to the venue and rarely change. A curated
  **venue profile** (constant in code, like `zones.py`) is written once per watchlist
  venue + a generic fallback, and every event at that venue reuses it.
- **Out of scope — separate spec right after this one:** admin **assigning any ride to
  any driver** (cross-tenant) with a **70/30 split** (70% driver, 30% stays in Black
  Volt's Square account). It applies to *all* rides, not just events, so it is its own
  feature. This spec only records the dependency.

## Data model

New tables (Alembic migration `0037_events`, `down_revision = "0036_social_daily_media"`).
Both rows live under the owner tenant (`tenant_id = OWNER_TENANT_ID = 1`); events are a
platform-level (single-brand public site) feature gated by `require_admin`.

### `event_suggestions`
| column | type | notes |
|---|---|---|
| `id` | PK | |
| `tenant_id` | FK → tenants | owner tenant |
| `source` | str(16) | `seatgeek` / `ticketmaster` |
| `source_id` | str(64) | dedup key, unique with `source` |
| `title` | str(200) | |
| `performer` | str(200), null | headline act |
| `venue_name` | str(160) | |
| `venue_key` | str(40), null | matched watchlist key (`empower_field`, `red_rocks`, `ball_arena`, `coors_field`, `fiddlers_green`) or null |
| `venue_address` | str(240), null | for the booking deep-link |
| `venue_lat` / `venue_lng` | float, null | |
| `distance_mi` | float, null | haversine from home base (Aurora) at insert |
| `starts_at` | datetime(tz) | |
| `score` | float, null | SeatGeek popularity |
| `image_url` | str(500), null | best remote image |
| `event_url` | str(500), null | official/ticket link |
| `status` | str(16) | `suggested` / `approved` / `dismissed` |
| `raw` | JSON | source payload (debug/enrichment) |
| `created_at` / `updated_at` | datetime | |

Dedup: unique `(source, source_id)` for upserts + fuzzy match (normalized title + same
date + same venue) so the same show from SeatGeek and Ticketmaster becomes one
suggestion (Ticketmaster data stored into `raw`/image enrichment, not a second row).
Dismissed suggestions never resurface (upsert skips status changes).

### `events`
| column | type | notes |
|---|---|---|
| `id` | PK | |
| `tenant_id` | FK → tenants | owner tenant |
| `suggestion_id` | FK → event_suggestions, null | provenance |
| `slug` | str(80), unique | e.g. `ed-sheeran-empower-field-2026` |
| `title` | str(200) | |
| `performer` | str(200), null | |
| `venue_key` | str(40) | watchlist key or `generic` |
| `venue_name` | str(160) | |
| `venue_address` | str(240), null | booking deep-link target |
| `starts_at` | datetime(tz) | |
| `doors_at` | datetime(tz), null | if the source provides it |
| `hero_path` | str(300), null | downloaded to `MEDIA_DIR/tenants/1/events/` |
| `about_text` | text, null | AI-written "about the show", admin-editable |
| `tips_text` | text, null | AI-written extras (optional), admin-editable |
| `status` | str(16) | `draft` / `published` / `archived` |
| `event_url` | str(500), null | |
| `created_at` / `updated_at` | datetime | |

### Venue profiles (code constant, not DB)
`backend/app/services/venue_profiles.py`: dict keyed by `venue_key` with curated,
factual content — `dropoff` (best spots + why), `pickup` (post-show meeting points +
traffic tips), `eats` (nearby bars/restaurants, short list with 1-line notes),
`parking_pain` (the "why not drive" argument), `coords`, `address`. Plus a `generic`
profile for non-watchlist venues (venue name + address only, generic tips). I research
and write these; the owner reviews the copy. Served to the frontend inside the public
event detail response.

## Backend

### Scanner — `services/events_scan.py`
- APScheduler job, daily ~06:00 America/Denver, registered next to the existing
  review-reminder job. Also runnable on demand from the dashboard ("Scan now" button).
- **SeatGeek**: `GET /2/events?venue.city=Denver...` (+ nearby metro cities / lat-lng
  radius), next 90 days. Keep an event if its venue matches the watchlist **or**
  `score >= EVENTS_MIN_SCORE` (config, default `0.6` on SeatGeek's 0–1 scale — big
  arena/stadium acts clear it, club shows don't; adjustable without deploy via `.env`).
- **Ticketmaster Discovery** (optional enrichment): for kept events at TM venues, fetch
  official URL + best 16:9 image; merged into the suggestion. If
  `TICKETMASTER_API_KEY` is unset or the call fails → skip silently (SeatGeek data is
  complete enough).
- Upsert suggestions; compute `distance_mi` from home base
  (config `BASE_LAT`/`BASE_LNG`, default = Aurora base). Suggestions whose
  `starts_at` has passed are pruned (deleted if still `suggested`).
- Failures: API/network errors are logged and leave existing suggestions untouched
  (stale-but-present beats empty).
- New settings: `SEATGEEK_CLIENT_ID`, `TICKETMASTER_API_KEY` (optional),
  `EVENTS_MIN_SCORE`, `EVENTS_SCAN_ENABLED` (default true when key present). Keys live
  in `.env` only — never committed. **Owner TODO:** create free developer accounts at
  seatgeek.com/account/develop and developer.ticketmaster.com; I provide the steps.

### Approval pipeline — `services/events.py`
`approve_suggestion(db, suggestion_id)`:
1. Create `events` row (`status="draft"`), slug from performer+venue+year with
   uniqueness suffix.
2. Download the best image to `MEDIA_DIR/tenants/1/events/<slug>-hero.<ext>` (reuse
   `_sniff_image`/downscale helpers from social). Failure → event still created,
   landing falls back to the venue-styled gradient hero (same pattern as social).
3. AI content: existing LLM chain (Kimi → MiniMax) writes `about_text` (short, factual,
   rider-oriented: who's playing, why it's big, what time to arrive). Failure → concise
   template text; always admin-editable afterwards.
4. Auto-create **2 social post drafts** via the existing `generate_and_create`:
   one `media_kind="video"` and one `media_kind="image"` (the image post uses the
   downloaded hero as its reference photo), with an event brief (title, date, venue,
   flat-$120 CTA, landing URL). They enter the normal social flow: approve / edit /
   delete / regenerate / publish; "Generate another post" works from the event too.
5. The event is created **`published`** (approve = the landing goes live immediately,
   matching the owner's flow); the admin can then edit copy/hero or unpublish from the
   Events tab. `draft` exists only as the unpublished state.

Lifecycle: a nightly step of the scan job archives events with `starts_at` in the past
(landing returns 410-style "event has passed" page with a link to `/book`).

### API — `api/v1/events.py`
Admin (all `require_admin`):
- `GET  /events/suggestions` — list `suggested`, ordered by `starts_at`, with venue /
  score / distance; filters: venue_key.
- `POST /events/suggestions/{id}/approve` → runs the pipeline, returns the event.
- `POST /events/suggestions/{id}/dismiss`
- `POST /events/scan` — run the scanner now.
- `GET/PATCH /events/{id}` — edit title/about/tips/status/hero; `POST /events/{id}/post`
  — generate an extra social post (kind=video|image).
Public (no auth):
- `GET /public/events` — `published`, future, ordered by date (home section).
- `GET /public/events/{slug}` — full detail + the venue profile block.

## Frontend

### Dashboard — `/dashboard/events` (admin-only, both navs: sidebar + DriverTabBar overflow)
- **Suggestions list** (default tab): card per suggestion — image, title, date, venue,
  score, `X mi from base`, source badge; actions **Approve** / **Dismiss**; "Scan now".
  Ordered by date; venue filter chips.
- **Events tab**: approved events with status, links to the public page, edit form
  (title, about, tips, hero swap, publish/unpublish/archive), the event's social posts
  (reusing the existing post cards/actions), and "Generate post" (video/photo).
- Mobile-first per project rule: verified at 390 / 820 / 1200.

### Public landing — `/events/[slug]` (server-rendered from the API)
Same visual mold as `/rides/[slug]`:
- **Hero**: event photo (or gradient fallback), title, date/time, venue, "Flat $120 —
  no event-night surge" badge.
- **About the show** (`about_text`).
- **Drop-off before the show** + **Pickup after the show**: from the venue profile —
  concrete spots and traffic tips; small map image if available for the venue.
- **Bars & restaurants nearby**: curated list from the venue profile.
- **Why Black Volt**: flat rate, prepaid, PUC/insured, professional driver (reuse the
  trust bar pattern from the SEO route pages).
- **CTAs** (primary, duplicated top & bottom): *Book your ride to the show* →
  `/book?dropoff=<venue_address>&date=<event date>&time=<starts-1h>&utm_campaign=event-<slug>`
  and *Book your post-show pickup* → pickup=venue, time=<starts+3h> (rider adjusts).
  Uses the same query-prefill mechanism the SEO pages use today; funnel measured by the
  existing analytics via the utm.
- **SEO**: JSON-LD `Event` (+ `Offer` for the ride), OG image = hero, dynamic sitemap
  entries for published events, `metadata` per page. English copy (site chrome keeps
  its existing i18n).
- Past/archived event → "This event has passed" page, link to `/book` and upcoming
  events (no 404, keeps the SEO juice).

### Home page — "Upcoming events" section
In the public landing (`WebShell` page), between existing sections: horizontal cards
(hero thumb, date badge, title, venue) for the next N published events, each linking to
its landing. Hidden entirely when there are no upcoming events. Fetches
`GET /public/events` server-side.

## Error handling summary
- Scanner API failure → log, keep previous suggestions.
- Image download failure → gradient fallback hero.
- LLM failure at approve → template about-text; admin edits.
- Social post generation failure at approve → event still created/published; posts can
  be generated manually from the event (error surfaced as toast).
- Public detail of unknown/unpublished slug → 404; archived → "event passed" page.

## Testing
- Backend (pytest, simulated external calls): scanner parsing + watchlist/threshold
  filter + upsert dedup (incl. cross-source fuzzy) + distance + prune; approve pipeline
  (event created, slug unique, 2 draft posts exist, image-post uses hero); dismiss
  never resurfaces; admin gate (403 non-admin); public endpoints only expose
  `published` future events; archive job.
- Frontend: `tsc --noEmit` + `next lint`; Playwright at 390/820/1200 — dashboard
  suggestions→approve flow, landing renders all sections, CTA href carries
  dropoff/date/utm, home section links.
- No tests against production; scanner runs simulated in tests
  (`EVENTS_SIMULATED`-style fixtures like the social engine).

## Phases
- **Phase 1 (this spec, MVP):** migration + models, SeatGeek scanner + scheduler job,
  dashboard Events section (suggest/approve/dismiss/edit), approval pipeline (hero +
  AI about + 2 social drafts), public landing + home section + prefilled CTAs, venue
  profiles for the 5 watchlist venues + generic. Validated end-to-end with **Ed
  Sheeran — Empower Field 2026** as the first real event.
- **Phase 1b:** Ticketmaster enrichment (merged into the scanner once the key exists).
- **Phase 2 (later):** new-big-event notifications (inbox/Telegram), round-trip event
  package.
- **Separate spec (next):** admin ride assignment to any driver + 70/30 Square split.

## Owner TODOs
- Create the free **SeatGeek** developer account (client id) and **Ticketmaster
  Discovery** API key; hand them to me for the VPS `.env`.
- Review the curated venue-profile copy (drop-off/pickup/eats) before launch.
