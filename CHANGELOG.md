# Changelog

## 0.91.2 — 2026-07-29 — "Reconnect" is useless advice when you already did

The owner reconnected Google and it still failed. Probing production told us why:

```
account: blackvoltmobility@gmail.com  ·  property: sc-domain:blackvoltmobility.com
403 "User does not have sufficient permission for site ..."
VISIBLE PROPERTIES: []
```

He picked the **wrong Google account** on the consent screen (`authuser=1`). That account owns
**no** Search Console properties at all — the property belongs to `enderjnets@gmail.com`, which had
been reading data fine for fifteen days.

And the app answered that 403 with the same words as a narrow scope: *"reconnect once"* — the exact
thing he had just done. He would have looped forever.

- **A 403 is now diagnosed, not guessed** (`services/gsc.py`). On denial we ask Google which
  properties the account can actually see. If ours is not among them the answer is
  **`wrong_account`**, carrying the connected email and the property we expected, and the card says
  *"you connected X, which cannot see Y — reconnect and pick the account that owns it"*. If the
  property **is** visible, the scope really is the problem and it stays `needs_reauth`.
- Both the status read and the submit go through the same diagnosis, and the underlying Google
  message is now logged — it was being swallowed, which is why this took a live probe to see.

⚠️ **This reconnect also broke the working Search Console read**: the new account cannot see the
property, so the daily snapshot will fail until it is reconnected with `enderjnets@gmail.com`.

6 new tests (939 total).

## 0.91.1 — 2026-07-28 — The sitemap button says what it needs, where the button is

The owner pressed **"Tell Google about the sitemap"** and reported that nothing happened.
Production logs say otherwise: **three** presses, each `POST /admin/sitemap/submit → 200 OK`.
And `blog_configs.updated_at` was still **2026-07-15** with no `/gsc/authorize` or `/gsc/callback`
in the logs — he had never reconnected, so the token was still read-only and Google refused every
submit.

The backend was right. The interface was not: it answered with a toast **at the top of the page**,
gone in three seconds, while he was looking at a button near the bottom that would never work.
That is a design failure, not a user error.

- **The permission is checked before he presses anything** (`services/gsc.py`). Google returns the
  granted scopes on the token refresh `sitemap_status` already performs, so `_sitemaps_list` now
  hands them back and the endpoint reports **`can_submit`**. It is `true`/`false` when Google says,
  and **`null` when it does not** — "we don't know" must never hide the only action available.
- **The card shows the reconnect prompt instead of a button that cannot work**
  (`components/bv/dash/BlogAdmin.tsx`), and it **stays** in that state after a refused submit
  instead of relying on a toast.
- **The outcome renders under the button**, where the action was, and does not time out.
- The reconnect copy is now an instruction with the concrete next step, not a diagnosis
  ("the saved permission is read-only") — EN and ES.

3 new tests (933 total), all verified to fail without the change.

## 0.91.0 — 2026-07-28 — Getting Google to come and read the site

The indexation check added in 0.90.0 came back with the same answer for **both** published
articles:

```
"coverage": "URL is unknown to Google",  "last_crawl": null
```

Google has never seen a single page. That is the real reason fifteen straight days report zero
impressions, and it means publishing more articles cannot help on its own. Verified the fault is
not ours: `robots.txt` allows Googlebot, `sitemap.xml` serves 18 correct URLs including both
articles, and every page answers 200 in 24–99 ms.

- **The sitemap can now be submitted from the dashboard** (`services/gsc.py`) — `sitemaps.list`
  for status (registered? last read when?) and `sitemaps.submit` to send it, both through the
  existing `asyncio.to_thread` pattern. The Analytics tab shows the status and flags the telling
  case: **registered but never downloaded**.
- **The OAuth scope widened** from `webmasters.readonly` to `webmasters`, because read-only cannot
  submit. A token minted before this returns 403, which is reported as **"reconnect once"** rather
  than a generic error — a completely different instruction for the owner. Reconnecting needs one
  click; the existing consent flow already asks for offline access.
- **Publishing an article re-submits the sitemap** (`services/blog_publish.py`), best-effort and
  wrapped so Google being down can never cost a publish. That module's docstring had claimed it
  "pings the sitemap" since F1 with **no code behind it** — the third such claim found in this
  engine. It is true now.
- **The step Google forbids us to automate is named, not faked.** Its Indexing API only accepts
  job postings and live broadcasts, so asking it to index an article is off the table. The tab
  lists exactly which articles Google has never seen and deep-links each one to its Search Console
  inspection page, saying plainly that this part is manual.

- **Refreshing the Google token no longer requests scopes.** Deploying the wider scope failed
  immediately with `invalid_scope: Bad Request` — not the 403 the reconnect path was written for,
  but a rejection of the *token refresh itself*, before any API call. A refresh token carries the
  scopes it was granted, so asking for more at refresh time kills the whole refresh: widening the
  scope would have taken the **daily Search Console read** down with it until the owner
  reconnected. Dropping the argument keeps an old read-only token reading, and confines the
  failure to the submit, where "reconnect once" is the right answer.

**Confirmed against production**: reading works on the existing token and returns
`{"sitemaps": []}` — **Google has no sitemap on file for this site at all**, which fully explains
the "unknown to Google" verdicts. Submitting correctly reports `needs_reauth` until the owner
reconnects once.

14 new tests (930 total), Google's client mocked throughout. No migration.

## 0.90.0 — 2026-07-28 — The Analytics and Speed tabs report something real

The owner reported both tabs looked dead. Investigated against production — logs, DB, and the
live API — rather than guessed.

### Speed was calling an API that always says no
Production log: `runPagespeed?url=…blackvoltmobility.com/blog → 429`, and the endpoint
answered the dashboard **200 OK** anyway. Verified by calling PSI directly:

```json
{"code":429,"message":"Quota exceeded ... consumer 'project_number:583797351490'"}
```

That project number is Google's **shared anonymous project**: without an API key every caller
on earth lands in one bucket whose daily quota is permanently spent. The code assumed
"keyless is allowed at low volume; a key just raises the quota" — it is not true, and the
result was **zero `psi` rows ever written**.

- **`services/site_speed.py` now measures the pages itself** — no key, no quota. Real TTFB
  (streamed, so headers-received is timed separately from the full download), page weight,
  whether it travelled compressed, HTTP version, render-blocking scripts and stylesheets in
  `<head>` (JSON-LD excluded — penalising our own structured data would be backwards), and
  image weight by `HEAD` so an audit costs the site almost nothing. Pages: `/`, `/blog`,
  `/book` and the newest published article. The payload is stamped `method: "self"` so nobody
  mistakes it for Lighthouse. A page that 500s or times out is **recorded**, not dropped.
- Snapshot kind renamed `psi` → `speed` (string column, **no migration**; there was no `psi`
  row to lose). `GOOGLE_PSI_API_KEY` deleted from config.

### Analytics threw away 13 of the 14 days it downloaded
`GET /blog/admin/analytics` returned each Search Console day **without its date**, so no trend
could be drawn — and the tab then rendered exactly one of them as three bare zeros.

- Every day now carries its date and comes back oldest-first, with 30-day totals.
- **The engine's own numbers ship alongside**: published / scheduled / held-back articles,
  keywords by status and source, and what it will write next. Those are true today, unlike
  Search Console.
- **Indexation**: `urlInspection.index.inspect` reports whether Google has actually indexed
  each published article — cached as a daily snapshot, never on a dashboard load, and it
  degrades silently if the API is unavailable.
- When every number is genuinely zero the tab now **says why** (a new site that has not
  started ranking) instead of looking broken.
- The endpoint's logic moved into `blog_service.analytics()`; its docstring had claimed it
  "returns empty scaffolding" since F1.

23 new tests (915 total), including the parsing edge cases and an end-to-end speed run against
`httpx.MockTransport` — never the network. No migration.

## 0.89.1 — 2026-07-28 — "Publish now" actually publishes

The owner pressed Publish on a finished article, twice, and got 200 OK both times. The post
stayed `scheduled` and never went live.

- **`publish_now` did not publish** (`services/blog_publish.py`) — it only moved `publish_at`
  forward and left the status at `scheduled` for the background job to release. That job
  returns early while the blog is paused, so the button was a permanent no-op that reported
  success. It now sets `published`, stamps `published_at` and fires the auto-share, and it is
  **not gated by `paused` or `autopublish`**: those stop the autopilot, not the owner. A
  `draft` can be published from here too — holding an article back is only useful if
  overriding the hold is one click. The function had no test at all, which is how it survived.
- **Fixed a test that failed only between midnight and 1am in Denver** — `test_tip_counts_
  toward_revenue_today` scheduled its ride at "UTC now + 1 hour", which lands on *tomorrow's*
  service day during that window. The product was right; the test was still thinking in UTC.

9 new tests (902 total). No migration.

## 0.89.0 — 2026-07-27 — The blog stops writing brochures: real fares, a quality gate, and a button that works

Our own engine had published **zero** articles in the 13 days since it was paused, while Soro
kept billing. Investigated against production before changing anything: generated a real
article through the live admin API and read it end to end.

The plumbing was fine (EN 584 + ES 743 words, FAQ, links). The content was not. It claimed
*"our all-electric **fleet**"* and *"our chauffeurs are trained"* — there is one Kia EV9 — and
it contained no fare, no drive time, and no airport logistics. Meanwhile
`frontend/lib/seoRoutes.ts` already held eight hand-written landing pages with real fares,
distances and durations from the live quote engine, and **none of it ever reached the writer**.

- **The writer is grounded in real business facts** (`services/blog_facts.py`, new) — the
  eight published routes with their fares (Aurora→DEN from $105, Denver→Vail from $329,
  Denver→Aspen from $790), miles and minutes, plus the non-negotiable truth about the
  business. `tests/test_blog_facts.py` parses the TypeScript source and fails if the two ever
  drift, so a price change on the site can never leave a stale fare in an article.
- **A quality gate decides whether an article may publish itself** (`services/blog_quality.py`,
  new) — title length and on-topic-ness, word count, banned claims, stock-phrase density, at
  least one real number, search-intent FAQ, and links that actually appear in the body and
  point at a page that earns money. A failing article gets **one corrective retry with the
  checker's own complaints fed back**; if it still fails it is parked as a **`draft` with no
  publish date** and the reasons shown in the dashboard. The autopilot can no longer publish
  something embarrassing.
- **Articles link to the pages with prices on them** — `allowed_link_paths` now includes the
  eight `/rides/...` routes. Before, the model linked `/`, `/blog` and the `/rides` index.
- **"Write now" no longer returns an error while succeeding** — generation takes over 100s,
  which is the hard ceiling of the proxy in front of the app, so the request 500'd every time
  even though the article was written. `POST /blog/admin/generate` now returns **202** and
  writes in the background; the dashboard shows live progress and refuses a double-click.
- **Search Console is finally a keyword source** (`services/blog_keywords.py`) — the docstring
  claimed it was source #1 and the code never queried it, so all 40 production keywords came
  from the LLM with **invented** monthly volumes that then ranked the whole content plan. Real
  impressions now feed in, and the LLM no longer supplies a demand figure at all.
- **Slugs come from the keyword, not the headline** — no more
  `experience-denver-airport-transfers-with-black-volt-mobility-s-kia-ev9`.
- **Formatting slips are repaired, not punished** — verified against the first real run on
  the new engine. The model reliably writes three good FAQ questions as `##` headings and
  then leaves the JSON field empty, leaves `internal_links` empty while the prose links
  correctly, and overshoots the title by five characters with a droppable subtitle. All three
  are now fixed before grading, so the gate judges the writing rather than the typing:
  `Luxury Airport Shuttle Denver: Premium Electric Chauffeur Service` → `Luxury Airport
  Shuttle Denver`. Internal links are read from the body, which is the only list that renders.
- Chore: named the fare+tip rollup `dashboard.revenue_sum()` (it was copy-pasted in nine
  places) and cleared the eight pre-existing `ruff` line-length errors.

- **The Spanish article has to be in Spanish** — caught on the first clean production run:
  an article passed every check and was scheduled to publish with a `body_md_es` that opened
  *"If you're looking for a reliable and luxurious way to travel from Boulder…"*. Nothing in
  the gate looked at the language, and that would have put a duplicate of the English article
  on the `/es` page. The language is now detected from the prose and checked against the slot,
  the instruction is repeated as the last line of the prompt, and the title shortener refuses
  a cut that would leave a Spanish page with an English headline.

57 new tests (894 total). No migration.

## 0.88.0 — 2026-07-26 — Service day in the driver's timezone + tips to the driver + fee on what actually cleared

Two owner reports: the assigned driver's payout base ignored his adjustments, and the
dashboard KPIs did not match reality. Both investigated against the real production rows
(read-only) before touching anything.

- **Service day is local, not UTC** (`services/dashboard.py`) — `stats`, `week_earnings`
  and `weeks_summary` bucketed on `func.date(scheduled_at)` with the DB session in UTC.
  Denver is UTC-6, so a 19:45 pickup is 01:45 UTC the next day and landed on tomorrow's
  numbers. Verified on prod: "RIDES TODAY 1 / REVENUE TODAY $155" was ride 70, driven
  **Jul 25 19:45 Denver** — the previous evening; today had zero. The weekly bars were
  shifted too (a Thursday 21:20 ride drawn on Friday). Now one shared `service_day()` /
  `today_local()` (via `CALENDAR_TIMEZONE`) backs the KPIs, the week chart, the week
  navigator and the My Stats funnel, so they cannot disagree with each other again.
  NOTE: tips were ALREADY counted in "This week" — the $605 included $50 of tips. That
  part of the report did not hold up and no change was made for it.
- **Tips go 100% to the driver** (`services/earnings.py`) — the gratuity was recorded on
  the ride and counted in the owner's revenue but never reached the assigned driver's
  payout. It is now added to the driver whole, on top of their share: never split, never
  charged a processor fee, never taxed. The identity becomes `driver + owner == net + tip`,
  still exact to the cent.
- **The Square fee is charged only on what cleared Square** (`services/earnings.py`,
  `assignment.card_amount_for`) — a cash/Venmo/Zelle ride was being docked a card fee it
  never paid, and an event ride was charged a fee on the full price when only the deposit
  runs through Square. The fee now follows the money.
- **A discount survives an edit** (`services/booking.py::apply_ride_update`) — re-quoting
  called `build_quote()` without the ride's discount context, so any route/time edit put
  the fare back to LIST price: overcharging the customer and inflating the driver's base.
  The code and the loyalty flag (recovered from the stored breakdown) are carried forward
  and `discount_amount` is kept in step. Latent until now — prod has no discounted ride yet.
- **Recording the method on a FINISHED ride marks it paid** (`api/v1/rides.py`) — two real
  rides were driven, collected by Venmo, had their method AND tip method recorded, and
  still read "Unpaid" because picking the method and flipping the flag were separate
  taps. Choosing a method on a ride that hasn't happened yet is still just planning, and
  an explicit `paid` in the same request always wins, so the flag stays a toggle.
- Tests: 837 backend (34 new). Each fix has a regression test verified to FAIL without it.
  No migration.

## 0.87.0 — 2026-07-25 — Ride hand-off: assign to another driver, private chat, agreed split

The owner works rides they book, but sometimes another driver on the team should take
one. The ride never changes owner: the customer, the money and control stay with whoever
booked it — the assigned driver gets the work, a private thread, and their cut.

- **Assignment reuses `Ride.assigned_tenant_id`** (already existed for discount hand-offs),
  so cross-tenant visibility needed no query changes — `services/booking.py` already lists
  on `or_(tenant_id, assigned_tenant_id)`. New `services/assignment.py` owns the rules:
  only the ride's owner can assign, re-price or settle (`can_manage`); the assigned driver
  can work the ride and use the internal thread (`can_view`). Endpoints:
  `POST/DELETE /v1/rides/{id}/assign`, `PATCH /v1/rides/{id}/payout`,
  `GET /v1/rides/{id}/earnings-preview`, `GET /v1/rides/assignable-drivers`.
- **Money split in `services/earnings.py`** — gross − Square fee − optional tax reserve =
  net, split by an agreed percentage (presets 100/80/70/50 plus any value). All integer
  CENTS with the rounding residue to the owner, so `driver + owner == net` exactly and no
  fraction of a cent leaks into a hand-settled payout. The fee is the tenant's configured
  estimate (`RateConfig.square_fee_pct`/`square_fee_fixed_cents`) because Square's real fee
  only exists once a payment settles; the tax reserve defaults to 0 so no existing number
  changes silently. Percentages and fees are SNAPSHOT onto the ride at assign time, so a
  later config change never rewrites a past ride's payout. The app computes and records —
  it moves no money (`driver_payout_status` is bookkeeping).
- **Internal channel** — `ride_messages.channel` (`client` | `internal`, default `client`
  so every existing row and the passenger endpoints are untouched). `internal` is
  owner↔assigned-driver only; the passenger endpoints are hard-coded to `client` and a
  passenger hitting the internal route gets 403. Both sides are staff, so "mine" and unread
  are resolved by TENANT, not by sender. Quick replies (EN+ES) for the things that always
  need saying: on my way / at the pickup / picked up / en route / drop-off done / running
  late / passenger not here / all good.
- **Customer PII window** — the customer belongs to the ride's OWNER. The assigned driver
  sees the phone, address and notes while the trip is live and loses them once it is
  finished (`_should_mask_pii`); the owner always sees everything. Auditing this found a
  leak the tests now cover: the ride DETAIL embeds the client record, which is masked too.
- **Photo rotation escape hatch** (`POST /v1/social/uploads/rotate` + a ⟳ button on each
  thumbnail). Verified in prod that the owner's photos arrive already landscape with NO
  EXIF flag, so v0.86.0's EXIF fix — correct in itself — cannot help them; nothing can
  auto-detect already-rotated pixels. The ingest now also logs the original's dimensions
  and orientation so the real cause is diagnosable from the next upload.
- **`flight` needs a number** — "United" or a bare "UA" is not a trackable flight, so it is
  null now (prompt rule + a digit check in `_coerce` that does not depend on the model).
- Tests: 810 backend (29 new — the money split incl. the owner's $95/80% example and
  cent-exactness, assignment authority, the passenger-can-never-see-internal leak test,
  the PII window, and route ordering). Migration 0049.

## 0.86.0 — 2026-07-24 — Whole-conversation screenshot extraction + EXIF-correct photo uploads

Two accuracy bugs the owner hit in the dashboard: Smart reservation put a contact
card's address on the wrong end of the trip (or dropped it), and a photo uploaded for
a social post published rotated.

- **Smart reservation reads the whole conversation** (`services/smart.py`) — the
  coding-plan VLM takes only ONE image per call, so extracting per image left the model
  blind to the rest of the thread: a lone contact card can't say whether its address is
  the pickup or the drop-off. Verified in prod logs — the same two screenshots yielded
  the address as pickup (trip inverted), as dropoff, and as null across three runs.
  Now each image is TRANSCRIBED (concurrent, one call each — a deterministic task the
  VLM is reliable at) and a single text call (Kimi primary, MiniMax fallback) extracts
  reservations from all transcripts TOGETHER, grouping by client itself. Explicit rules
  cover which end of the trip a lone address belongs to and preferring a real street
  address over a vague reference ("her house"). A failed image is still skipped, not
  fatal; step 2 failing still degrades to `[]` for manual entry. The `minimax_anthropic`
  path (already whole-context) is untouched; dead per-image grouping helpers removed.
- **Photo uploads are stored upright** (`services/social.py`) — `_downscale_for_social`
  re-encoded without applying the EXIF orientation tag, so every phone photo over
  1920x1080 lost its rotate flag and published sideways. Now the orientation is applied
  via `ImageOps.exif_transpose`, and a rotated-but-small photo is re-encoded too instead
  of passing its stale flag downstream. `_tiktok_safe_media` orients before measuring
  aspect, so a sideways 9:16 photo is no longer padded as if it were landscape. Fixed at
  `save_reference_image`, the ingest chokepoint both upload endpoints share.
- Tests: 781 backend (10 new — EXIF orientation on oversized/small/upright, the ingest
  chokepoint, aspect-after-orient, and the two-step pipeline: single step-2 call with
  every transcript, model grouping, merge collapse, skipped image, step-2
  failure/unparsable/prose-wrapped). No migration.

## 0.85.0 — 2026-07-21 — Passenger notification bell + clearer ride messaging + driver bell fix

Closes the messaging gaps in the per-ride chat (v0.82.0): the passenger had no in-app
surface for a driver's message, both sides' "send message" entry was buried, and the
driver dashboard bell showed nothing but the push prompt on a phone.

- **Passenger notification bell** — a bell now sits in the web header for signed-in
  passengers, polling `/v1/client/notifications`. A driver's ride message records an
  in-app notification (not only a push), so the passenger sees an unread badge with or
  without push enabled. Tapping a message opens that ride's chat directly
  (`/trips?chat=<id>`); cancellation refunds also appear.
- **Backend** — new `client_notifications` table (migration `0048`) + `ClientNotification`
  model, `notifications.emit_client()` (best-effort, per-client prune, no double-push),
  and `client/notifications` GET/read/read-all endpoints scoped to the session's client.
  The driver→passenger message and refund fan-outs now also emit the in-app row.
- **Push deep-link** — the passenger ride-message push now opens the exact ride chat.
- **Driver ride list** — each ride row shows an unread-message count so a waiting
  passenger message never slips by.
- **Fix: driver dashboard bell** — the notifications list collapsed to 0 height inside
  the mobile bottom sheet (a `flex:1` scroll child in a content-sized flex column), so
  only the "turn on notifications" prompt showed. The list now has a definite height and
  always renders.

## 0.84.0 — 2026-07-20 — Official Black Volt logo across icons + splash

Adopt the official brand logo (electric-blue bolt / dark wordmark). Master files live
in `brand/`; web-servable copies in `frontend/public/brand/`.

- **App icon (Android)** — regenerated all launcher densities + adaptive icon
  (bolt on void `#0A0A0F`) via `@capacitor/assets` from `mobile/assets/`.
- **Launch screen** — the dark wordmark ("BLACK VOLT / MOBILITY") centered on void,
  all densities/orientations, light + dark.
- **Web** — favicon/PWA icons (`icon-192`, `icon-512`, `maskable-512`,
  `apple-touch-icon`) regenerated from the bolt; official wordmark + 1200×630
  `og-image.png` served from `/brand/` for social previews.

## 0.83.0 — 2026-07-20 — Android app: native Google sign-in + FCM push

Fase C for Android. Wires the native capabilities the backend was already armed for.
All new code is **guarded by `isNativeApp()` → a complete no-op on the web** (the
fetch interceptor is never even installed off-native), and ships through the normal
web deploy because the native app loads the live site.

- **Native Google Sign-In** — inside the Android app the sign-in modal now uses the
  phone's Google account picker (`@capgo/capacitor-social-login`) instead of the web
  GIS button. It obtains a Google ID token, exchanges it at `POST /auth/login/google`
  with `X-BV-Native: 1`, and stores the returned session token.
- **Bearer + native header interceptor** — `lib/nativeFetch.ts` wraps `window.fetch`
  once (native only) to add `Authorization: Bearer <token>` and `X-BV-Native: 1` to
  same-origin `/api` calls; the token is persisted via `@capacitor/preferences`.
- **FCM push** — `lib/nativePush.ts` requests the notification permission, registers
  the device with FCM (`@capacitor/push-notifications`) and mirrors the token to
  `POST /push/subscribe {platform:"fcm"}`, so ride updates and driver messages arrive
  even when the app is closed.
- `mobile/` — added `@capgo/capacitor-social-login`, `@capacitor/push-notifications`,
  `@capacitor/preferences` and `cap sync`'d.

## Mobile (Android) — 2026-07-18 — Capacitor shell: buildable native Android app

Fase B for Android. A Capacitor wrapper that loads the live site as a native app;
a debug APK builds cleanly (`com.blackvoltmobility.app`, SDK 36). No web change.

- `mobile/` — Capacitor 8 project. `capacitor.config.js` loads `server.url`
  (production, or `CAP_SERVER_URL` for a dev stack), HTTPS-only, with
  `allowNavigation` for the site + Square 3-D Secure + Google. Splash/status bar
  in brand `#0A0A0F`; UA marked `BlackVoltApp`. `mobile/android/` native project
  committed (build artifacts / `local.properties` gitignored).
- `frontend/lib/native.ts` — `isNativeApp()` / `nativePlatform()` (reads the
  Capacitor global + UA marker; no `@capacitor` import, SSR-safe). The "Install
  app" button and the add-to-home-screen hint hide inside the native app, and the
  web-push service worker is skipped there (push will arrive via FCM).

## Backend infra — 2026-07-18 — Android-ready: multi-audience Google, Bearer sessions, FCM push

Groundwork so the upcoming native **Android** client app can authenticate and receive push.
**No user-visible change** (the customer app version stays 0.82.0); every change is
retrocompatible and a no-op until the native OAuth client ID / FCM credentials exist.

- **Multi-audience Google Sign-In** — `verify_google_id_token` now accepts a token whose `aud` is
  the web client ID **or** any ID in the new `GOOGLE_CLIENT_IDS` (CSV) setting, so the same passenger
  login works from the web button and the native app. Empty → identical to today (web ID only).
- **Bearer sessions** — `deps.current_payload` falls back to `Authorization: Bearer` when there's no
  cookie (a WKWebView with a remote origin can't rely on cookies); the cookie still wins. `/auth/me`
  now honours it too. `POST /auth/login/google` returns the session token in the body **only** when
  the caller sends `X-BV-Native: 1`, and native passenger sessions get a 180-day TTL (web keeps 7 days).
- **Native push (FCM HTTP v1)** — `push_subscriptions.platform` column (migration 0047, existing rows
  = `webpush`; `p256dh`/`auth` now nullable), `services/fcm.py` sender, and a branch in
  `push._send_one` that routes `platform="fcm"` rows to FCM. Every existing call-site (chat push,
  pickup reminders, ride events) is untouched; the driver PWA's Web Push is unchanged. `POST
  /push/subscribe` accepts `{platform, endpoint, keys?}`. No-op without `FCM_*` env.
- Tests: `test_android_backend.py` (Bearer, multi-audience accept/reject, native token+TTL, FCM
  subscribe + delivery routing). Full backend suite: 766 passed, 0 failed. Migration 0047 reversible.

## v0.82.0 — 2026-07-17 — Per-ride passenger↔driver messaging (Fase A of native apps)

Riders and their assigned driver can now exchange messages tied to a single ride —
the ride *is* the conversation. First deployable phase of the mobile-app roadmap
(client app to the stores); delivers value today on web + the driver PWA, with no
store dependency.

**Backend**
- `app/models/ride_message.py` + migration `0046_ride_messages`: new `ride_messages`
  table (tenant-scoped, FK CASCADE to rides, `sender` enum client|driver, `read_at`
  for live unread counts). Adds the `ride_message` value to `notification_kind`
  (in an autocommit block, per Postgres enum rules). Migration is reversible.
- `app/services/ride_messages.py` + `app/api/v1/ride_messages.py`: `GET/POST
  /rides/{id}/messages`. Sender side is derived from the session, never the body;
  passengers touch only their own ride (403/404 otherwise), staff act as the driver.
  Posting is gated to the chat window (`booking.chat_window_open`: booked →
  completed+48h) with a 10/min·60/h rate limit. Opening the thread stamps `read_at`
  on the other party's messages. Client→driver rings the staff bell + Web Push;
  driver→client pushes the rider — both best-effort, never break the send.
- `GET /rides` and `GET /rides/{id}` now expose `unread_messages` + `chat_open`
  per viewer (one grouped query, no N+1).
- 13 new API tests (authorization, window, read-tracking, rate limit, fan-out
  routing). Full backend suite: 751 passed, 0 failed.

**Frontend**
- `components/bv/RideChat.tsx`: reusable thread + composer (on-brand bubbles,
  polls every 6s while visible) and a mobile-first bottom-sheet panel.
- `/trips`: the "Message" button now opens the in-app ride chat with an unread
  badge (Call stays a `tel:` link). Driver drawer (`RideDetail`) gets a Messages
  section. The bell maps `ride_message` and deep-links to `/dashboard/rides?open=<id>`.
- i18n EN + ES for all new strings.

## v0.81.1 — 2026-07-17 — Fix: goal projection crashed for zero-conversion accounts

Setting a client/revenue goal and opening the projection ("how many conversations
a day to hit it") returned a 500 for any account that had logged activity but not
closed a single client yet. The Wilson lower bound of a not-yet-observed conversion
rate is ~0, so `required_activity` divided the target by ~0 and produced
`float("inf")`, which is not JSON-serializable — the endpoint crashed on serialize.

- `backend/app/services/funnel_math.py`: `required_activity` now caps the required
  daily effort at a credible ceiling (`max(central estimate, COACH_MAX_PER_DAY)`)
  instead of returning infinity, mirroring the existing coaching guard. The central
  estimate and healthy-data bands are unchanged; only the degenerate worst-case is
  capped. All effort fields are now provably finite (no `inf`/`nan` reaches JSON).
- `backend/tests/test_funnel_math.py`: regression test asserting the zero-conversion
  projection stays finite, JSON-serializable, and correctly ordered.
- Fixes `test_project_by_clients` (and the state-dependent `test_project_by_revenue`
  failure) — full suite now 738 passed, 0 failed.

## v0.81.0 — 2026-07-15 — Record customer tips on a ride

Customers sometimes add a tip at the end of a ride. There was no way to record it —
the ride modal only had fare, payment method and paid. Drivers can now log a tip in
the same place, including how it was paid (which may differ from the fare's method,
e.g. a cash tip on a card ride). Tips count as earnings.

- `backend/app/models/ride.py`: new `tip` (Float, nullable) and `tip_method` (reuses
  the existing `payment_method` enum) columns. NULL = no tip.
- `backend/migrations/versions/0045_ride_tip.py`: adds both columns; `tip_method`
  references the existing enum with `create_type=False`.
- `backend/app/api/v1/rides.py`: `RidePatch` accepts `tip` (ge=0) + `tip_method`;
  `patch_ride` records them and treats `tip=0` as an explicit clear (drops the
  method too); `_ride_out` serializes both.
- `backend/app/services/dashboard.py` + `funnel.py`: earned-revenue rollups now sum
  `fare_total + coalesce(tip, 0)` (revenue today, weekly totals, per-client spend,
  team revenue, My Stats). `avg_fare` / `value_per_client` stay fare-only so pricing
  and coaching targets aren't skewed by tips.
- `frontend/components/bv/dash/RideDetail.tsx`: a Tip block under the payment method
  with quick $5 / $10 / $20 chips, a custom amount, and a method selector (defaults
  to the fare's method). Shows "+$X" on the fare card; editable/removable.
- `frontend/lib/booking.ts` + `lib/i18n.tsx`: `tip`/`tip_method` types; EN + ES
  strings.
- Tests: `backend/tests/test_ride_update.py` covers record, clear (tip=0), default,
  negative rejection, and tip-included-in-revenue.

## v0.80.2 — 2026-07-12 — Public blog: restore Soro (coexistence during transition)

The F2 SSR `/blog` page replaced the route that used to render the paid Soro embed,
so Soro's already-published articles vanished from `blackvoltmobility.com/blog` while
our own engine had no published owner-tenant posts yet (autopilot paused). Soro is
paid and must keep auto-publishing until our engine is polished, so the two now
**coexist** on the public blog.

- `frontend/components/bv/web/SoroBlog.tsx`: added `showHeader?: boolean` prop
  (default `true`) so the embed can render without its own `<h1>` on a shared page.
- `frontend/app/(web)/blog/page.tsx`: renders our SSR posts (when present) then the
  Soro embed below (`<SoroBlog showHeader={false} />`), under a "More from our blog" /
  "Más de nuestro blog" divider when we have our own posts. Removed the misleading
  empty-state text (Soro fills the page meanwhile).

Cutover (F6) later removes the `<SoroBlog>` block once our engine's articles are the
sole content — at which point the Soro subscription can be cancelled.

## v0.80.1 — 2026-07-12 — Blog writer: fix article generation (bilingual)

The article writer dropped **every** post to the short fallback template — in both
English and Spanish. Root cause: `blog_writer._parse_json` used strict JSON parsing,
but MiniMax pretty-prints its response with **literal newlines inside string values**
(e.g. `body_md`), which the strict parser rejects (`Invalid control character`). Kimi
escaped them; MiniMax does not — and prod runs MiniMax-only (Kimi key returns
`AuthenticationError`). Verified against live MiniMax output: strict parse → `None`
(template); `json.loads(..., strict=False)` → full 900-word article, EN and ES.

- `backend/app/services/blog_writer.py`: `_parse_json` now parses with `strict=False`
  (tolerates raw newlines/tabs in strings) while keeping the code-fence/prose stripping.
- Regression test `test_parse_json_tolerates_raw_newlines_and_fences`.

No migration. This does **not** un-pause autopilot on its own — that stays an owner
toggle in the dashboard once article quality is confirmed.

## v0.80.0 — 2026-07-12 — Volt Blog Autopilot (our own "Soro")

A full AI SEO blog engine that replaces the paid Soro embed (renewal $81 on 2026-10-05).
Built and deployed across 5 phases (commits `c1373c7`→`6c713ba`); this release also bumps the
public version and ships the Brand-DNA/GSC/Speed follow-up fixes below.

**The engine (F1–F5):**
- **Keyword discovery** (daily): Google Autocomplete + LLM topical map, intent scoring, dedupe,
  auto-promote to the calendar. Grounded in the real business (zones, airport, routes, events).
- **Bilingual (EN+ES) articles** written by the LLM (Kimi→MiniMax), with a deterministic template
  fallback so a post is always produced; validated internal links (never a 404); hybrid-24h publish
  window (edit/veto before it goes live).
- **Native SSR pages** at `/blog` and `/blog/[slug]` — content is in the HTML (Googlebot sees it),
  with Article + FAQ + Breadcrumb JSON-LD, hreflang en/es, canonical, sitemap, and curated hero
  images. This SSR is the core SEO win over Soro's client-side embed.
- **Auto-share**: on publish, a draft social post (hero + link) enters the existing social→Buffer
  pipeline for owner approval (never auto-posts).
- **Analytics/Speed**: Google Search Console (real clicks/impressions/CTR/position = true "Impact")
  and daily PageSpeed Insights.
- **Owner dashboard** `/dashboard/blog`: Calendar, Published, Keywords, Brand DNA, Analytics, Speed.

**Follow-up fixes in this release:**
- Brand DNA is now **auto-seeded** (voice/audience/themes/avoid/image-style) and back-fills older
  blank rows, so the dashboard is never empty; plus an **"Auto-fill with AI"** button.
- **Connect Google Search Console** button added to Analytics (the OAuth endpoints existed but had no
  UI); callback now redirects to the app host where the session lives.
- **Speed** tab is now usable: runs PageSpeed **keyless** at low volume (a free key just raises the
  quota), a **"Run audit now"** button, and readable score/metric/opportunity cards.

Autopilot ships **paused** in production pending a working LLM key (see project notes); everything
degrades gracefully. Backend migration `0044`; 24 blog tests; suite green.

## v0.79.0 — 2026-07-11 — "Install app" now works on Safari (iOS + macOS)

**Owner-reported bug:** tapping the "Install app" button in Safari — from either the rider site or the
driver dashboard — did nothing.

**Root cause:** the button was driven entirely by Chrome's `beforeinstallprompt` event, which Safari
(iOS *and* macOS) never fires. When no prompt was available the button only toggled an 11px grey text
line (easy to miss → "nothing happens"), and on **macOS Safari** it showed the wrong hint (open the
"⋮" menu, which Safari doesn't have) because iOS detection didn't cover desktop Safari.

**Fix:**

- **New `isSafari()`** in `lib/push.ts` — detects Safari on iOS and macOS desktop, excluding
  Chrome/Edge/Firefox/Opera (which all carry "Safari" in their UA).
- **New `InstallInstructions.tsx`** — a dismissable instruction sheet (bottom sheet, Escape/tap-outside
  to close) with the correct manual steps and a Share glyph: iOS → tap **Share → Add to Home Screen**;
  macOS Safari → click **Share → Add to Dock**. Any other prompt-less browser falls back to the generic
  browser-menu hint.
- **`InstallButton`** now opens that sheet on Safari instead of the invisible text line. Chrome/Edge keep
  firing the native prompt exactly as before.
- **`InstallHint`** banner now also appears for macOS Safari users, and its button opens the same
  instructions (previously the banner had no actionable button unless the native prompt was available).
- i18n: added `install.help.*`, `install.ios.s1–3`, `install.mac.s1–2` in EN and ES.

Frontend-only; no backend, migration, or API change.

## v0.78.0 — 2026-07-10 — Multi-date event pages + a cleaner events dashboard

Two owner-reported problems with `/dashboard/events` and the public event pages:

1. **Archived events cluttered the dashboard.** `GET /events/admin` returned every status ordered
   by `starts_at asc`, so past/archived events floated to the top and buried the ones being
   promoted. **Fix:** a client-side filter row on the Events tab — **Active** (default =
   published + draft) / **Archived** / **All**, with counts.
2. **Each date of a show was its own page.** A two-night run (Avett at Red Rocks, Jul 10 & 11) was
   two `Event` rows with slugs `…-2026` and `…-2026-2` → two landings, two ad targets. **Fix:** a
   lightweight grouping so the dates of one show share a single public page with a date selector.

Implementation (no Event restructuring — still one row per date, so per-date pricing, the `/quote`
engine, booking, deposit=1/3, and per-date analytics are untouched):

- **New `Event.series_key`** (nullable, indexed; migration **0043** backfills every existing event
  from the same base slug the approve flow builds — `performer/title-venue-Denver year`). Two nights
  of the same act/venue/year share it; `NULL` = ungrouped (stands alone, unchanged behaviour).
  `approve_suggestion` sets it, so a later night joins the group automatically. New helper
  `events.series_key_for` is the single source of truth (frozen inline copy in the migration).
- **`get_public_event`** now returns `canonical_slug` (soonest live date — the page URL) and
  `dates[]` (one entry per published, upcoming sibling with its own `round_trip_price` /
  `one_way_from`). **`list_public_events`** collapses a show to one card (`dates_count`,
  `price_from`). Draft/archived/foreign-tenant siblings never appear.
- **Landing** (`events/[slug]/page.tsx`): a non-canonical date URL 307-redirects to the canonical
  page with `?date=…` preselected, **preserving UTM/`fbclid`** so running ads keep attribution. A
  new `EventDateSelector` (client) swaps the price, deposit, JSON-LD, and the **per-date booking
  link** (`/events/<sibling-slug>/book`) so checkout + Purchase analytics stay per-date. Home
  section shows "N fechas · desde $price".
- **Dashboard**: the Events tab groups a show's dates into one card with date chips; publishing a
  date is what promotes it (existing toggle — no new endpoint). Bilingual EN/ES throughout.
- Joules needs no change — its per-slug URLs now land on the unified page with the right date
  preselected via the redirect. Tests: 7 new (series_key grouping, dates payload, canonical
  redirect, draft/archived exclusion, all-archived, list grouping, tenant scoping); full suite green.

## v0.77.0 — 2026-07-09 — Event estimate uses the venue's real zone fare

The public event estimate (`events._public_round_trip_price`) priced every leg at the cheapest
inner **`denver_metro`** flat ($105), but the real `/quote` engine charges each leg at the
**venue's actual zone** — Red Rocks (Morrison) is `metro_mid` ($115), not `denver_metro`. So the
landing advertised **$385** (deposit $128) while checkout quotes **~$405**, understating the price
for the flagship venue (and any venue in an outer zone). The deposit was 1/3 of the wrong number.

- **New `events.venue_leg_fare(db, ev)`** resolves the venue's zone fare via `zones.match_zone`
  on `ev.venue_address` (string match — no maps calls), falling back to the inner-metro flat when
  there's no address or no covered zone (never worse than before).
- `get_public_event` and Joules `_events_block` now price the one-way/round-trip off this venue
  fare. Red Rocks landing → **$405 / $345** (deposit $135 / $115), matching the real quote.
- Backend-only, no migration, no frontend code change (the landing is `force-dynamic` and reads
  the API per request). Tests: `venue_leg_fare` unit + `get_public_event` round-trip; full suite
  **700 passed**.

## v0.76.0 — 2026-07-09 — Event booking is instrumented end to end

The event booking flow (`EventBooking.tsx`) fired **no** analytics — no internal funnel
events, no Meta pixel `InitiateCheckout`/`Purchase`, no CAPI. So event-landing ad campaigns
had nothing to optimize toward (a conversions campaign would starve), and our own Insights
funnel was blind for events. This wires it up, mirroring the general `/book` flow.

- **Funnel + pixel on the event flow.** `EventBooking.tsx` now fires `book_start` → `book_review`
  (+ `QuoteViewed`) → `book_pay` (+ Meta **InitiateCheckout**, value = live quote total) →
  `book_confirmed` (+ Meta **Purchase**, deduped with server CAPI via `purchaseEventId`).
  Session-deduped per stage.
- **ViewContent on the event landing.** A small client component
  (`components/bv/web/EventViewContent.tsx`) fires Meta `ViewContent` once per event view — the
  top-of-funnel signal for event ad campaigns and retargeting.
- **DRY.** `trackFunnelOnce` moved from `Booking.tsx` into `lib/analytics.ts` (exported) and is
  now shared by both booking flows; behavior unchanged.

## v0.75.0 — 2026-07-09 — Event pages lead with the deposit + sticky mobile CTA

Paid Instagram traffic was landing on event pages, reading them, then bouncing without
booking (78 sessions on the Sam Barber page → 0 reservations). The page led with the full
round-trip total ($415) and never showed the small deposit that actually reserves the ride,
and on phones the CTA scrolled out of view. This reframes the offer for mobile conversion.

- **Lead with the deposit, total as breakdown.** Event pages now headline the reservation
  deposit — a third of the round trip, e.g. "Reserve for $138 today" — with the full
  round-trip total shown right beneath it. Computed in `app/(web)/events/[slug]/page.tsx`
  (`deposit = round(round_trip_price / 3)`), matching the exact 1/3 the booking flow charges.
- **Sticky mobile CTA.** A Reserve button (`.bv-event-sticky-cta` in `app/globals.css`) is
  pinned to the bottom of the viewport on phones (≤899px) so it stays reachable while the
  rider scrolls the event details; hidden on desktop where the inline CTAs suffice.
- **Bilingual.** The new price/CTA copy renders via a small client component
  (`components/bv/web/EventCta.tsx` + `event.*` keys in `lib/i18n.tsx`) so it localizes to
  English and Spanish — the landing is a server component and the language lives in
  localStorage, so the copy that must translate now renders client-side.

## v0.74.0 — 2026-07-08 — Joules knows the events + is injection-hardened + faster hero

Three things: Joules is now trained on the site's public data (chiefly upcoming
events), hardened against prompt injection, and the home hero loads lighter.

- **Joules answers event questions.** The system prompt (`backend/app/services/joules.py`)
  now injects the published upcoming events (`GET /events/public` data, capped at 12) with
  their Denver date/time, venue, **public round-trip price** (driver waiting, 1/3 deposit)
  and one-way-from price + a `/events/{slug}` link — reusing `events.public_round_trip_price`
  and `events.live_flat_price` so the figures match the landing exactly (internal fees like
  `night_fee`/`wait_fee_per_hour` are never surfaced). Also added: the event/deposit policy
  (round-trip only, 1/3 Square deposit, refundable to 48h, <72h cancel = 50%), the service
  area, an approved-reviews average line, and useful URLs (/events, /rides, /review). The
  "if it's not in the facts, say so" rule now points riders to the site or an escalation
  instead of a flat "I don't know". A 4th quick-reply ("What events are coming up?" / "¿Qué
  eventos hay próximamente?") was added to the chat launcher.
- **Prompt-injection & confidentiality hardening.** Every untrusted value interpolated into
  the prompt (passenger name, ride pickup/dropoff/flight, and event title/performer/venue —
  which come from third-party ticketing APIs) is now sanitized (`_clean`): control chars and
  newlines collapsed, code fences / `role:` markers / the escalate marker defused, length
  capped. The prompt carries explicit **SECURITY** (treat all user + data-tag content as
  data, never instructions; refuse role/rule changes and prompt-reveal requests) and
  **CONFIDENTIAL** (never reveal discount codes, other customers' data, internal fees,
  revenue/analytics, API keys, or the driver's phone unless it's in the trip facts) rules,
  and wraps rides/events in `<trip_data>`/`<events_data>` tags. Defense-in-depth: a canary
  token + verbatim-prompt-fragment **output guard** in `reply()` swaps in the safe hand-off
  if the model is ever coaxed into echoing its own prompt. New red-team suite
  `backend/tests/test_joules_security.py` (12 tests); full backend suite green (698 passed).
- **Faster home hero + lighter social images.** The LCP hero now ships **AVIF**
  (`ev9-coors-field.avif` 1600w 154KB / 800w 70KB) via `<picture>` with the WebP kept as
  fallback, and the preload was switched to AVIF. The two oversized OpenGraph JPEGs were
  resized to 1200w and recompressed (`ev9-coors-field.jpg` 373→196KB, `ev9-charging.jpg`
  183→93KB). No render regressions — the site was already lazy-loaded, CDN-served (Cloudflare)
  and minimal-JS; this trims the remaining image weight Soro flagged.

Files: `backend/app/services/joules.py`, `backend/app/services/events.py`
(`public_round_trip_price`), `backend/tests/test_joules_security.py` (new),
`frontend/components/bv/web/Chat.tsx`, `frontend/lib/i18n.tsx` (`chat.q4`),
`frontend/components/bv/web/Landing.tsx` (`<picture>`), `frontend/app/(web)/page.tsx`
(AVIF preload), `frontend/public/assets/*` (AVIF + recompressed JPGs), `version.ts`.
Backend logic change but **no DB migration**.

## v0.73.0 — 2026-07-07 — Sign in from the PWA + a livelier Joules launcher

Two mobile-UX gaps closed on the rider app.

- **Sign in / register on the PWA.** The header "Sign in" text button is hidden on phones (<900px) and the bottom tab bar had no account entry, so a signed-out visitor had no way to sign in except by hitting the booking wall. Added a compact **account icon** (person) to the mobile header that opens Google sign-in — which also creates the account (there's no separate register). Desktop keeps the text button; the signed-in avatar/menu is unchanged. `SignInModal` copy now reads "Sign in — or create your account —…" (EN+ES).
- **Joules launcher with life.** The floating chat button looked decorative. It now proactively draws attention: ~7s after load it starts a periodic **wiggle** + **pulse ring** and floats a **rotating one-liner** bubble ("Need a fare quote?" / "Airport transfer?" / "Going to an event?"), plus an unread dot. Clicking the bubble opens the chat; the ✕ (or opening the chat) dismisses it and it stays quiet for the rest of the session (`sessionStorage`). Positioned above the FAB and the tab bar and clamped to the viewport so it works on **web, mobile and installed PWA**; all motion is neutralized under `prefers-reduced-motion`.

Frontend-only, no backend or migration. Files: `WebShell.tsx` (mobile account icon), `Chat.tsx` (nudge/wiggle/dot), `globals.css` (`.bv-mobile-account`, `.bv-chat-nudge`, `bvWiggle`/`bvPulse` keyframes), `i18n.tsx` (`chat.nudge1-3` + `auth.subtitle`).

## v0.72.1 — 2026-07-07 — Fix: event reservation lost after sign-in

Booking an event while signed out abandoned the reservation: after clicking "Pay deposit" the rider signed in with Google (and completed their profile on first login), but the app then sent them to `/account` instead of continuing — no payment, no booking. The dedicated event flow was calling sign-in without a resume callback, so the app fell through to its default post-login destination. It now passes a resume closure (the same pattern the generic `/book` funnel uses): after sign-in and profile completion the deposit continues automatically to the payment step. Frontend-only, no migration.

## v0.72.0 — 2026-07-07 — Events: round-trip-with-wait only + deposit + smart pickup time

Event rides are now **round trip only** — one price, your driver takes you to the venue, **waits during the show**, and brings you home (no surge). The one-way "ride there" / "ride home" options are gone from the event experience; the landing now shows a single **Book round trip** action that opens a **dedicated event reservation flow** (`/events/[slug]/book`), separate from the generic booking funnel.

- **1/3 deposit to reserve.** A one-third deposit is charged now (Square) to secure the booking; the balance is collected in person on the event day. Riders read the terms and accept them with a required checkbox before paying — acceptance is recorded server-side (auditable).
- **48-hour refund policy.** Fully refundable up to 48 hours before the event; within 48 hours the deposit is non-refundable (the driver reserved the night).
- **Smart pickup time.** The suggested pickup time is computed from **Google-Maps traffic** so you arrive ~30 minutes before showtime — editable by the rider. The return is timed to when the show ends.
- **AI event duration.** On approval, the driver's wait time is pre-filled from an AI estimate of that specific event's length (still editable).
- **Driver sees the balance.** The driver ride detail shows "Deposit paid $X · collect $Y balance on the event day" so they charge the remaining two-thirds, not the full fare.

Backend: traffic-aware `duration_in_traffic`, public pickup-suggestion endpoint, `deposit_cents`/`balance_due_cents`/`terms_accepted_at`/`terms_version` on rides (migration 0042), deposit-aware charge + `fee_pct=100` cancellation path. 685 backend tests pass (incl. 11 new). The generic `/book` funnel and existing full-prepay event rides are unchanged.

## v0.71.1 — 2026-07-06 — Fix PWA installability + explicit Install button

The v0.71.0 PWAs weren't actually installable: the service worker was only registered when a user enabled notifications, and it had no `fetch` handler — so Chrome never met its installability criteria and `beforeinstallprompt` never fired (no install prompt on Android).

- `public/sw.js`: added a no-op `fetch` handler (installability requirement; still caches nothing).
- `lib/pwaInstall.ts`: shared install store — captures `beforeinstallprompt`/`appinstalled` at load and registers the SW on **every** page visit (via `InstallHint`, mounted in both shells) so the app qualifies as installable.
- `InstallButton` (new): a permanent "Install app" affordance in the site footer and the driver's Settings — fires the native prompt when available, else shows Add-to-Home-Screen / browser-menu instructions. Hidden once installed. `InstallHint` refactored onto the shared store.
- i18n `install.button` / `install.menuHint` (EN+ES).

## v0.71.0 — 2026-07-06 — PWA: installable apps + Web Push (rider + driver)

Phase 1 of the mobile apps: both the rider site (apex) and the driver dashboard (app. host) are now installable PWAs with their own manifest, icons, and service worker, plus Web Push for both audiences.

- **Installable**: `manifest-client.webmanifest` / `manifest-driver.webmanifest` linked per host via each route-group layout; on-brand icon set generated by `frontend/scripts/gen_pwa_icons.py`; minimal `public/sw.js` (push + notificationclick deep-link only — no HTML caching). Dismissible `InstallHint` (Android `beforeinstallprompt` / iOS Add-to-Home-Screen).
- **Web Push (VAPID / pywebpush)**: new `push_subscriptions` table (mig 0041) + `services/push.py` (fire-and-forget, own session, prunes dead 404/410 endpoints, silent no-op without keys). Driver push mirrors the 7 dashboard-bell events via `notifications.emit`; rider push covers staff-cancellations, refund decisions, and a pickup reminder (APScheduler, 3h lead, deduped by `rides.pickup_reminder_sent_at`). `PushOptIn` control in the bell, driver Settings, and rider Account.
- Router `/api/v1/push` (config / subscribe / unsubscribe / test). 13 new backend tests. Auth unchanged (same-origin cookie — native Bearer is Phase 2 / Capacitor).

## v0.70.1 — 2026-07-05 — Perf pass 2 (Soro Site Speed 88 → target 100)

Follow-up to v0.70.0's perf work (Soro re-check moved 74→88, load 8.3s→3.7s). Remaining lever = the critical-path load; 3 of 4 metrics already "Good".

- **LCP hero preload**: `<link rel="preload" as="image" imagesrcset/imagesizes fetchpriority=high>` on the home + `/rides/[slug]` server pages (React-hoisted to `<head>`), so the hero starts downloading before JS/fonts instead of after.
- **Joules chat code-split**: `ChatAssistant` now loads via `next/dynamic({ ssr: false })` — its module leaves the shared first-load bundle and loads on the client after hydration (launcher appears a beat after paint; no functional change).

Frontend-only, no backend/migration.

## v0.70.0 — 2026-07-05 — Pricing: uncovered-endpoint guard + performance pass

**Pricing fix (Lisa/Longmont):** an endpoint outside every named zone (Longmont was unlisted) let the OTHER endpoint's flat win — a ~42-mile Longmont→DEN ride quoted the core flat. Root cause: `zones.match_zone` matches pickup OR dropoff by city name; `pricing.quote` lets `zone_flat` replace the whole metered calc.

- **Uncovered-endpoint guard** in `booking.build_quote` (single funnel for quote/ride/round-trip/events → full parity): when a matched flat coexists with an endpoint that is in no zone (and isn't an airport keyword or the pinned base), the flat becomes a FLOOR — the trip is also metered and the higher total wins. The guard can never lower a price.
- **Zones:** `longmont` + `niwot` added to the boulder zone terms (same north corridor); new `zones.covered()` helper.
- Tests: 4 new (Longmont→boulder flat, far uncovered town meters above the flat, near uncovered town keeps the flat floor, bare "DEN" keeps the flagship flat). Zone/pricing suites 44 passed; full backend 653 passed (4 pre-existing PIL failures unrelated).

**Performance pass (Soro measured 8.3s load / 74):** home was 1,078 KB; 786 KB addressable.

- Hero JPEGs → pre-generated WebP (`scripts/gen_hero_webp.py`): coors-field 365→171 KB (73 KB mobile), charging 179→54 KB (23 KB mobile); `srcset`/`sizes` + explicit width/height, `fetchpriority="high"` on LCP heroes, lazy elsewhere. Originals kept as OG images (scraper compatibility). Benefits home + 8 /rides pages + driver profile.
- Meta Pixel (242 KB) `afterInteractive` → `lazyOnload` (out of the critical path; PageView still fires).
- `headers()` in next.config.js: `/assets/*` now `Cache-Control: public, max-age=2592000` (Cloudflare HIT instead of 4h REVALIDATE).

## v0.69.1 — 2026-07-05 — Blog embed lifecycle hardening

**Fix (from post-deploy adversarial audit):** the Soro embed registers a window `popstate` listener and mutates `<head>` (canonical, Blog JSON-LD, `document.title`) — removing its `<script>` tag undoes none of that, so after an SPA exit from `/blog`, back/forward on other pages fired a stale handler (console TypeError, title overwritten) and a stray canonical/JSON-LD lingered in `<head>`.

- `SoroBlog.tsx`: intercept `window.addEventListener` only while the embed script loads, capture its `popstate` handler (matched by its own internals), restore the original on `onload`/`onerror`, and detach the captured handler on unmount; cleanup also sweeps the embed's `<head>` artifacts (canonical tagged `data-soro` + Blog/BlogPosting JSON-LD — our own pages' JSON-LD lives in `<body>` and is untouched).
- `blog/page.tsx`: nested `<main>` → `<section>` (WebShell already renders the page's `<main>` landmark).

## v0.69.0 — 2026-07-05 — Blog

**Feature:** Black Volt Mobility now has a public blog at `/blog` on the apex site, powered by the Soro embed (SEO article engine, paid quarterly through 2026-10-05).

- **New route `app/(web)/blog/page.tsx`** — server component with SEO metadata (title/description/canonical/OG) that renders a branded H1 + intro (own indexable copy) above the Soro widget.
- **New client component `components/bv/web/SoroBlog.tsx`** — injects the Soro embed script (`app.trysoro.com/api/embed/<public-token>?theme=dark`) into `#soro-blog`, (re)created per mount and cleaned up on unmount so it survives StrictMode / SPA re-entry; container stays empty and harmless if the embed is disabled. The embed token is a public identifier (not a secret).
- **Navigation** — "Blog" added to the header `NAV` array and the footer links in `WebShell.tsx`, i18n `nav.blog` / `blog.title` / `blog.intro` in EN + ES.
- **Sitemap** — `/blog` added to `app/sitemap.ts` (priority 0.7, weekly).
- No CSP anywhere in the stack, so the external Soro script loads without allow-listing. No backend changes, no migration.

## v0.68.0 — 2026-07-05 — The notification bell works

**Feature:** the dashboard header bell is now functional — an unread count badge + a panel of recent activity, tenant-scoped, delivered by polling (no websockets in the stack).

- **New `Notification` model + migration 0040** (`notifications` table, `notification_kind` pg-enum, JSONB `data`, per-tenant, retention capped at 100 newest rows). Only `kind` + `data` are stored; the frontend renders bilingual text from i18n templates.
- **Service `services/notifications.py`** — `emit()` is best-effort (commits its own row, rolls back only on its own failure) and is called AFTER each caller commits, so a notification failure can never lose the underlying ride/message/review.
- **Events wired** (next to the existing emails): new ride (`payments.authorize_for_ride`, `rides.confirm`), ride cancelled (`rides.cancel`), chat escalated + new chat message (`chat.send_message`, deduped to one per unread batch), new review (`reviews.submit`), discount redeemed (`payments`), subscription payment failed (`webhooks_square`). Ride/discount notifications route to the servicing driver (`assigned_tenant_id`), matching the email.
- **API `/api/v1/notifications`** (staff-only, tenant-scoped): `GET` (unread count + 30 newest), `POST /{id}/read`, `POST /read-all`. Cross-tenant access 404s.
- **Frontend** — `NotificationsBell.tsx` replaces the decorative bell: numeric badge, dropdown on desktop / bottom sheet on mobile, 60s polling (paused when the tab is hidden), deep-links per kind, mark one/all read, EN + ES.

No secrets touched; migration runs on backend boot.

## v0.67.1 — 2026-07-05 — Joules speaks your language

**Fix:** Joules now respects the site language instead of always opening in English.

- **Greeting follows the page language.** The i18n provider hydrates the saved
  language (`localStorage`) after first render, but the chat greeting was captured
  once in state at mount (English default) and never re-translated. A small
  `useEffect` in `Chat.tsx` keyed on `lang` now re-syncs the greeting bubble to the
  current language while the panel still shows only that greeting — so a Spanish
  visitor is greeted in Spanish, an English visitor in English.
- **Replies mirror the passenger's language.** The system prompt no longer hard-locks
  Spanish when the UI is Spanish. `joules.py` now instructs Joules to reply in the
  **same language as the passenger's most recent message** (English or Spanish),
  using the UI language only as the tie-break default when a message is too short to
  detect — so a mid-conversation language switch is honored both ways.

_No schema changes. Backend `build_system_prompt` + `test_joules_prompt.py`, frontend
`Chat.tsx`._

## v0.67.0 — 2026-07-04 — Joules, the real AI assistant

**What shipped:** the public-site chat widget is now **Joules**, a real Kimi→MiniMax
assistant (replacing the canned `bvAI.ts` mock with its fake "Hi Alex" greeting).

- **Google sign-in required.** The widget is visible to anonymous visitors with
  Joules' greeting + suggestion chips; sending the first message opens the existing
  Google sign-in modal, then the pending message auto-sends (reuses
  `useWeb().openSignIn` + the profile-gate resume chain).
- **Live pricing + passenger context.** The system prompt is built server-side from
  the tenant's effective zone prices (same merge as `/rate-config`), the service
  area, cancellation/payment policies, Denver time, and the signed-in passenger's
  upcoming rides (status, pickup time, driver contact once assigned). Joules is
  **read-only** — it directs users to `/book` and `/trips`, never books or changes
  anything.
- **Escalation.** When a passenger asks for a human (or every LLM provider fails),
  Joules emits an `[ESCALATE]` marker; the backend strips it, flips the conversation
  to `escalated`, and emails the tenant owner the transcript + contact (Resend,
  once per transition, never blocks the reply).
- **Dashboard Inbox is real.** `/dashboard/inbox` now lists persisted conversations
  (client, last-message time, unread badge, "Needs you" filter) and renders the full
  thread; opening clears the unread badge; owner can email the client (mailto) or
  close the chat. Tenant-scoped — each owner sees only their own threads.
- **Bilingual** EN/ES; the reply language follows the passenger.

**Backend:** new `chat_conversations` + `chat_messages` tables (migration `0039_chat`,
one conversation per `(tenant_id, client_id)`, reopens when closed);
`app/services/joules.py` (prompt builder + provider chain + fallback);
`llm.chat_complete` (multi-turn) + `llm.providers()`; `email.notify_owner_chat_escalation`;
`api/v1/chat.py` (passenger post/history gated by `require_passenger`, staff
list/read/close gated by `require_staff`, per-client rate limits 5/min + 30/h).
**Frontend:** `lib/chat.ts`, rewritten `Chat.tsx` + `dash/Inbox.tsx`, deleted the
`lib/bvAI.ts` mock. **Tests:** 22 new backend tests (API auth-gating, rate limit,
escalation email once, tenant scoping, prompt content) — full suite green.

## v0.66.4 — 2026-07-04 — Live prices everywhere (kills teaser drift)

**Problem (from the v0.66.3 code review):** teaser prices were hardcoded in three places (seoRoutes.ts, FAQ prose, Booking placeholder) plus a stale $74 in the chat assistant, while the owner tunes real fares live in the Rates dashboard — v0.66.2 and v0.66.3 were both manual re-sync releases and the site drifted again within the hour of deploy. Pricing policy going forward: stay >=10% (~$15-30) below **Uber Black Reserve**; owner adjusts in Rates as Uber moves.

- **Frontend reads the live zone map**: new `lib/zonePrices.ts` fetches `GET /v1/rate-config` server-side with ISR (`revalidate = 300`); `/rides/[slug]`, `/rides`, and the homepage Popular routes resolve each route's `zoneKey` (new field in seoRoutes) against it — `priceFrom` is now only an offline fallback. FAQ answers use a `{{price}}` token filled at render (visible text + JSON-LD), so prose can never disagree with the number again.
- **Booking screen**: pre-quote placeholder and pay-later amounts use the live `denver_metro` flat via `getRateConfig()` instead of a hardcoded 110.
- **Chat assistant**: retired the $74/`$12+$2.40/mi` era — persona and mock replies now interpolate the live rate config (generic wording when offline).
- **Event landings & social posts**: new `events.live_flat_price(db, tenant)` — `flat_price`, `one_way_from`, round-trip estimate, event social topic, and about-text fallback read the tenant override, not the import-time constant.
- **Rates save path**: `_check_zone_prices` now strips entries equal to `DEFAULT_ZONE_PRICES`, storing only intentional deviations — the editor's full-map round-trip was permanently pinning every zone key, making future code recalibrations dead for the tenant.
- **zones.py**: `metro_mid` renamed "Denver metro — outer ring" (it no longer contains DTC); base-address pin `_BASE_MARKERS` ("s fraser st") → core, so the flagship base→DEN price no longer depends on Google's Aurora/Centennial labeling or Centennial's ring; ring comment rewritten (benchmark rule, not distance).
- **Tests**: dtc/denver tech/lone tree core-membership asserts added; base-street pin tested under both city labels; removed the hand-synced "not in <flat prices>" tuple (the `zone is None` assert above it is the real check).

## v0.66.3 — 2026-07-03 — Competitive zone pricing (Uber benchmark)

**Problem:** the owner's own base→DEN test quoted **$140** — above Uber for the same reservation. Two causes: (1) Google formats the Aurora 80016 base as "Centennial, CO" and `centennial` sat in the $140 `metro_mid` ring; (2) several zones were priced above Uber Black for their typical airport run (RideGuru benchmark, 2026-07-03: DTC→DEN Black $112 vs our $140; Parker $123 vs $165; Brighton $87 vs $165; Boulder $170 vs $180; Denver→Vail $359 vs $390; Breck $303 vs $349; COS→DEN premium ~$230 vs $359; FoCo ~$208 vs $280; Greeley ~$176 vs $249).

**Changes (rule: flat ≤ Uber Black on-demand → always ≤ Uber Reserve):**
- `backend/app/services/zones.py` ring membership recalibrated to the Black→DEN benchmark: **centennial, greenwood village, denver tech, dtc, lone tree, parker, broomfield, brighton → `denver_metro` $110**; `metro_mid` $140 keeps golden/highlands ranch/morrison + castle pines (down from far); `metro_far` $165 is castle rock only.
- Zone prices: **boulder 180→165, vail 390→349, summit 349→299, colorado_springs 359→229, fort_collins 280→199, loveland_greeley 249→169**. Aspen stays $790 (owner decision: no price war on Aspen) and denver_metro/DEN stays $110. Owner decisions 2026-07-03: Brighton joins the $110 core (parity with Uber's SUV tier — Black sedan is uncatchable there); short intra-metro trips stay on the $110 flat (not the target business).
- Prod + local dev `rate_configs.zone_prices` override (tenant 1) updated to the same map — the override is what quotes actually read.
- `frontend/lib/seoRoutes.ts` teasers synced: DTC **$110**, Boulder **$165**, Vail **$349**, Breck **$299** (priceFrom + FAQ); Aurora/Cherry Creek $110, Red Rocks $140, Aspen $790 unchanged.
- New regression test: base address with the "Centennial" Google label must price as `denver_metro` $110.

## v0.66.2 — 2026-07-03 — Price teaser sync + ad deep-link

**Problem:** customer-facing teaser prices had drifted from the live quote engine. The homepage cards, `/rides/[slug]` labels + JSON-LD, the `/book` placeholder fare, and the event landing all showed **$120** (and Boulder **$190**, plus stale mountain FAQ figures) while the real flat zones charge **$110** metro/DEN, **$140** outer/DTC, **$165** far ring, **$180** Boulder — a price a customer would see advertised and then not match at checkout (bad UX + SEO doorway risk).

**Changes:**
- `backend/app/services/zones.py`: code defaults aligned to the owner's Rates configurator — `denver_metro` 120→**110**, `boulder` 190→**180** (all other zones already matched). `DEFAULT_ZONE_PRICES`, `ZONE_DESCRIPTORS`, and `events.py` `FLAT_PRICE` derive from these, so the event landing + social posts auto-follow. The DB `rate_configs` override (source of truth) was already correct on prod; this only fixes the code fallback.
- `frontend/lib/seoRoutes.ts`: `priceFrom` + FAQ prose synced to live quotes per route — Aurora/Cherry Creek **$110**, DTC + Red Rocks **$140**, Boulder **$180**, and mountain FAQ figures corrected to the real flat (Vail **$390**, Breck **$349**, Aspen **$790**). Home cards, `/rides` list, and `/rides/[slug]` label/JSON-LD all read from this.
- `frontend/components/bv/web/Booking.tsx`: pre-quote placeholder fare 120→**110**.
- Ad deep-link: Instagram/Facebook paid campaign points to `/book?to=Denver%20International%20Airport&utm_source=ig&utm_medium=paid&utm_campaign=den-flat-110` — destination prefilled so the visitor sees a quote immediately.
- Tests updated to the new prices (`test_zones`, `test_booking_zones`, `test_booking_api`, `test_events_*`, `test_round_trip`, `test_event_pricing`); round-trip combined total 395→**375** (2×110 + $40 event + $25 night + $90 wait). 613 backend tests pass; ruff/tsc/lint/build clean.

## v0.66.1 — 2026-07-03 — Ad measurement (Meta Pixel + Conversions API)

The Instagram/Facebook ads run on a *Traffic* objective, so Meta was optimizing for
cheap clickers, not bookers — and there was no Pixel, so it had no booking signal at all.
This wires up first-party ad measurement so a *Conversions* campaign can find people who
actually book. Ships dormant: no pixel is loaded and no events are sent until an ad-account
pixel id + CAPI token are configured, so the default build is unchanged.

- **Browser Pixel (`components/bv/MetaPixel.tsx`, `app/layout.tsx`):** base pixel loads only
  when `NEXT_PUBLIC_META_PIXEL_ID` is set (build arg). The booking flow fires `QuoteViewed`
  (custom) when a fare is shown, `InitiateCheckout` at the payment step, and `Purchase` on
  confirmation (`lib/analytics.ts` + `Booking.tsx`).
- **Conversions API (`services/meta_capi.py`, `api/v1/payments.py`):** on a card
  authorization the server sends a `Purchase` to Meta's Graph API in a background task
  (never blocks the booking). It carries the same `event_id` (`purchase_<ride_id>`) as the
  browser Purchase so Meta deduplicates the pair.
- **Privacy + safety:** email/phone/name are SHA-256 hashed per Meta's spec before leaving
  the box — raw PII is never sent. The CAPI access token is a secret (VPS `.env` only, never
  committed). The send is gated on `capi_live` (enabled + not simulated + creds present) and
  on `OWNER_TENANT_ID`, so only the owner's bookings reach the owner's pixel. Fail-soft: a
  measurement error can never break a payment.
- Config: `META_PIXEL_ID`, `META_CAPI_ACCESS_TOKEN`, `META_CAPI_ENABLED`,
  `META_CAPI_SIMULATED`, `META_TEST_EVENT_CODE`, `NEXT_PUBLIC_META_PIXEL_ID`
  (see `.env.example`). Tests: 7 service unit tests + 2 endpoint tests.

## v0.66.0 — 2026-07-02 — Event reservations: prepaid by card

Event rides are high-commitment and often booked well ahead, so they now prepay in full
by card at booking instead of the everyday authorize-hold (a Square hold expires in ~6
days and would fail for a concert booked further out). Non-event rides are unchanged.

- **Immediate capture (`payments_square.authorize` + `payments.authorize_for_ride`):** a new
  `capture` flag charges in full (`autocomplete=true`) when the ride is an event ride
  (`price_breakdown["event"]` set). The Payment is stored `CAPTURED` and both legs of a
  round trip are marked `paid`. Everyday rides still authorize-hold + staff-capture.
- **Card required for events (`confirm_ride`, `Booking.tsx`):** pay-later/cash is blocked
  server-side (402 `card_required_for_event`) and the "Pay later" tab is hidden at checkout
  for event rides; a prepay + refund-policy note is shown.
- **Event cancellation policy (`rides.py` cancel):** full refund 72h+ before pickup, else a
  50% refund (auto — no driver decision). `settle_cancellation` now accepts `fee_pct=50`
  and refunds the non-fee half of the captured payment. Everyday rides keep the 24h /
  driver-choice policy.

## v0.65.2 — 2026-07-02 — Distance-tiered metro pricing

Split the single flat Denver-metro zone into distance tiers so the far affluent suburbs
pay a rate that reflects the longer drive (driver margin + willingness to pay), without
sub-tiering the whole metro.

- **`services/zones.py`:** two new zones ahead of `denver_metro` (precedence: farther pickup
  wins on a mixed trip). `metro_mid` ($140/leg → ~$400 round trip): Greenwood Village / DTC,
  Centennial, Highlands Ranch, Lone Tree, Golden. `metro_far` ($165/leg → ~$450 round trip):
  Castle Pines, Castle Rock, Parker. Close-in metro (Denver, Aurora, Cherry Creek, Cherry
  Hills, Englewood, Littleton…) stays the base rate (~$340 round trip); Boulder keeps $480.
- The owner's custom close-in ($110) and Boulder ($180) rates are unchanged; the new tiers
  use these defaults until tuned per-driver in Rates → Flat zones.

## v0.65.1 — 2026-07-02 — Event pricing calibration (real operator data)

Tuned event pricing against real concert-transport field rates (one-way ≈ Uber Black,
round trip prices the whole-evening commitment).

- **Uber Black formula** `UBER_BLACK_PER_MILE` 3.75 → **5.0** (config.py + compose + VPS
  `.env`). The old rate under-predicted long premium routes (Boulder → Empower ≈ $152 vs a
  real ~$200), which made the Research tool's "cap under Uber Black" slash high-value far
  origins and understate our margin. Re-run *Research prices* on an event to refresh.
- **Ed Sheeran event** wait fee $70/h → **$40/h** (data), so the Boulder round trip lands at
  **$500** (2 × $190 legs + $120 wait), matching the market instead of $590.

## v0.65.0 — 2026-07-02 — Event pricing: fees, round trips & Uber research

Layers per-event pricing on top of the featured-events module: event/night/wait fees, a
round-trip product bookable in one prepaid checkout, and a competitive-research agent that
prices us against Uber Black.

- **Per-event pricing (`event.py` mig `0038`, `event_pricing.py`):** each `Event` carries
  `event_fee`, `night_fee`, `night_cutoff` (Denver-local), `wait_fee_per_hour`,
  `est_duration_hours`, an editable `round_trip_price`, and a `pricing_research` snapshot.
  `find_event_for_ride` matches a ride to an event by venue + time window, so fees apply on
  **any** booking channel (event landing, direct `/book`, admin-created). Night fee is keyed
  to the leg's local time; all time-of-day logic runs in `America/Denver`.
- **Round-trip booking (`booking.create_round_trip`, mig `0038` ride linkage):** creates a
  linked outbound + return pair (`return_ride_id`, `is_return`) with per-leg fares that sum
  to the round-trip total (event/night/wait surcharges ride on the outbound). A single Square
  authorization covers both legs; confirm/capture/cancel propagate across the pair; calendar
  syncs both. A paid round-trip leg blocks route edits (409) to protect the captured amount.
- **Quote + booking surfaces:** `/quote` and `/book` accept `round_trip` + `return_at`; the
  event landing shows "One-way from $X · Round trip $Y" and a round-trip CTA; the booking
  flow has a round-trip toggle (prefilled from the landing deep-link) and charges once.
- **Uber competitive research (`uber_research.py`, `pricing-scout` container):** the dashboard
  "Research prices" button estimates Uber Black / Black SUV from affluent Denver origins,
  compares them to our fare, scores each origin for ad targeting (margin × affluence ×
  proximity to base), and writes an AI recommendation. Live prices come from an optional,
  isolated Playwright `pricing-scout` service (HMAC, fail-soft); without it a published-rate
  formula is used, so research always produces a full table. The suggested round-trip price
  is capped just under Uber Black when we'd otherwise be pricier.
- **Config:** `UBER_BLACK_*` rate knobs + `PRICING_SCOUT_URL`/`PRICING_SCOUT_SECRET`
  (`.env`-tunable). Docs: `docs/setup-event-pricing.md`.

## v0.64.1 — 2026-07-01 — Featured events: hardening & fixes (code-review follow-up)

Fixes the 10 findings from the high-effort review of v0.64.0.

- **Scanner robustness (`events_scan.py`):** `run_scan` now bulk-loads the tenant's
  suggestions once and dedups in memory. Fixes a latent bug where the production session
  (`autoflush=False`) hid rows added earlier in the same run from the in-loop dedup SELECTs —
  a within-run duplicate `(source, source_id)` could raise IntegrityError and roll back the
  whole scan (0 saved). Also removes the per-item N+1 (1 query vs ~200) and runs the SeatGeek
  and Ticketmaster fetches concurrently. Cross-source dedup now keys on venue_key + day +
  title (robust to venue-name/time spelling differences across sources).
- **Post-show CTA (`events.py`):** an event is only `passed` once it's actually retired
  (archive grace window), so the "Book your post-show pickup" button stays live during and
  just after the show instead of vanishing at showtime.
- **Timezone (`events.py`):** AI blurb, fallback copy, social topic, and the slug year now
  render `starts_at` in America/Denver, so evening shows no longer show the next day.
- **Tenant scoping (`events.py`):** `list_public_events`, `get_public_event`, and
  `archive_past_events` now scope to the owner tenant (CLAUDE.md anti-pattern #6) — no
  cross-tenant leak on the SaaS path.
- **Single source of truth:** the flat fare is read from the metered zone engine
  (`zones.DEFAULT_ZONE_PRICES['denver_metro']`) instead of a hardcoded 120 in three places;
  the frontend uses the API's `flat_price`.
- **Owner-tenant resolution:** one shared `tenancy.owner_tenant_id(db)` resolver (DB-backed,
  no `or 1` magic) used by the scanner and the API, so writer and reader can't diverge.
- **SSRF:** the hero download validates **every** redirect hop before following it (not just
  the final URL); `/sitemap.xml` fetch now has a 3s timeout so it can't hang on backend health.
- 8 new regression tests (571 backend total): autoflush in-run dedup, passed-during-show,
  tenant isolation, cross-source fuzzy dedup, and per-hop SSRF rejection.

## v0.64.0 — 2026-07-01 — Featured events: concert & big-event ride pages

New end-to-end module that turns big Denver events into ride-booking landing pages.

- **Daily scanner** (`services/events_scan.py`, APScheduler 06:00 America/Denver): pulls upcoming
  Denver-metro events from **SeatGeek** (base) + **Ticketmaster Discovery** (enrichment/source),
  keeps those at watchlist venues (Empower Field, Red Rocks, Ball Arena, Coors Field, Fiddler's
  Green) or above a popularity bar (`EVENTS_MIN_SCORE`, default 0.6), dedups across sources, ranks by
  distance from the driver's Aurora base, and upserts into `event_suggestions`. Fails soft — a missing
  key or network error leaves existing suggestions untouched; approved/dismissed rows are never
  disturbed. Ticketmaster fetch **live-verified**: 300 events, 31 watchlist hits (Ed Sheeran at
  Empower Field, Red Rocks, Coors Field) with images.
- **Dashboard → Events** (owner-admin only): review suggestions ranked by date with venue/score/
  distance, **Approve** / **Dismiss**, **Scan now**, edit published events (title/about, publish/
  unpublish/archive), and generate extra video/photo posts per event.
- **Approval pipeline** (`services/events.py`): creates a **published** event (landing live
  instantly, no deploy), downloads the hero image, writes an AI "about the show" blurb (Kimi→MiniMax,
  factual fallback), and spawns **two social-post drafts** (video + photo) into the existing
  approve/edit/regenerate/publish flow. A post-generation failure never blocks the (already live)
  landing.
- **Public landing** `/events/[slug]` (DB-driven, server-rendered): hero, "Flat $120 each way — no
  surge" badge, about, **curated per-venue** drop-off/pickup guidance + nearby bars & restaurants
  (`services/venue_profiles.py`), trust bar, JSON-LD `Event`, dynamic sitemap entry, and dual booking
  CTAs deep-linking to `/book` (to-the-show + post-show pickup, `utm_campaign=event-<slug>`). Past
  events show a friendly "this event has passed" page (no 404).
- **Home**: new "Upcoming events" strip linking to each event page (hidden when none).
- **Footer**: Instagram + TikTok icons linking to the brand accounts.
- Migration `0037_events` (`event_suggestions`, `events`). New settings (`.env`):
  `SEATGEEK_CLIENT_ID`, `TICKETMASTER_API_KEY`, `EVENTS_MIN_SCORE`, `EVENTS_SCAN_ENABLED`,
  `EVENTS_BASE_LAT/LNG`. Keys live in the gitignored `.env` only. 29 new tests (564 total). See
  `docs/setup-events.md`.

## v0.63.2 — 2026-07-01 — TikTok: pad non-9:16 photos so they publish

- **Bugfix**: TikTok rejected uploaded photos with `Invalid post` because they weren't 9:16 (verified
  live: a 9:16 image is `sent` on TikTok, a 0.68-aspect one is rejected; Buffer re-hosts the image so
  it isn't a fetch issue). New `_tiktok_safe_media` produces a padded **1080×1920** variant (photo
  contained + centered on a blurred copy of itself — nothing cropped) saved as `<stem>-tt916.jpg`;
  images already ~9:16 (e.g. AI renders) pass through untouched. `_do_publish` sends this variant to
  **TikTok only** — Instagram/Facebook keep the original framing (owner chose "only adjust when
  needed"). Reuses Pillow (v0.62.4); best-effort (falls back to the original on any error). +3 tests
  (535 total). No migration.

## v0.63.1 — 2026-07-01 — Social: retry a missing network on already-published posts

- `publish_post` now also accepts a `published` post for retry (idempotent skip means it only hits
  connected targets missing from `external_ids` — safe no-op when nothing's pending). The dashboard
  computes pending **connected** platforms client-side (from the accounts list, so an unconnected
  target like Facebook never counts) and shows the "Publish remaining" button + "published to X ·
  pending Y" line on any post with a pending connected network — including legacy `published` ones
  (e.g. post 63: live on Instagram, missing TikTok). +1 test (532 total). No migration.

## v0.63.0 — 2026-07-01 — Social: partial-publish state + per-platform retry

- New `partial` post status: when a post publishes to some target platforms but still owes others
  (only **connected** targets count), it's marked `partial` instead of a misleading full `published`.
  `_do_publish` computes remaining connected targets; `publish_post` accepts `partial` for retry
  (idempotent skip from v0.62.5 means a retry only hits the pending networks — no duplicates).
- Dashboard: partial posts show a "Partly published" badge, a "Published to X · pending Y" line, and a
  **Publish remaining** button. `PostStatus`/`POST_STATUSES` gain `partial`; i18n EN+ES. +2 tests
  (531 total). No migration (status is a free String column).

## v0.62.5 — 2026-07-01 — Publishing: idempotent per-platform retry (no duplicates)

- `_do_publish` now skips any platform already present in `external_ids` (`if ext.get(platform):
  continue`), so re-publishing only fills in the networks that haven't posted yet — no duplicate
  Instagram/TikTok posts on retry. A post that already published to some platform is never downgraded
  to `failed` when a remaining platform fails terminally (`had_prior` guard). Enables recovering a
  partially-published post (e.g. live on Instagram, missing TikTok) by resetting it to `approved` and
  publishing again. +1 test.

## v0.62.4 — 2026-07-01 — Fix: image posts to TikTok (downscale oversized uploads)

- **Bugfix**: image posts published to Instagram but TikTok rejected them with `UnexpectedError:
  "Invalid post"`. Root cause: TikTok's photo API caps images at **1920×1080** (long×short edge);
  an uploaded photo was 2252×3290 (the AI-rendered 768×1344 image published fine, proving it wasn't
  a schema/carousel issue). Uploads are now downscaled on save to fit 1080×1920 via Pillow
  (`_downscale_for_social` in `save_reference_image`) — JPEG q85, aspect preserved, alpha-PNG kept;
  best-effort (animated gif / decode failure keeps the original). Instagram is unaffected (accepts
  the smaller size), and 1080px is plenty for mobile. Added `pillow==11.0.0`. TikTok photo limits
  confirmed against the official Content Posting API docs.

## v0.62.3 — 2026-07-01 — Fix: publishing image posts to Instagram

- **Bugfix**: "Publish now" silently did nothing on image posts — Instagram's Buffer call 400'd with
  `Field "shouldShareToFeed" of required type "Boolean!" was not provided`. v0.62.2 sent only
  `{"type": "post"}` for images; `InstagramPostMetadataInput` requires **both** `type` and
  `shouldShareToFeed`. `_network_meta` now always sends `shouldShareToFeed: true` (image → `type:
  "post"`, video → `type: "reel"`). With IG publishing succeeding, the post flips to PUBLISHED instead
  of staying stuck APPROVED. (TikTok's separate per-image "Invalid post" rejection of some uploaded
  photos is TikTok photo-mode format/aspect validation, not a schema bug — best-effort.) Verified
  against the live Buffer GraphQL schema via introspection.

## v0.62.2 — 2026-07-01 — Fix: publishing AI image posts to Buffer

- **Bugfix**: image posts (media_kind=image) rendered fine but flipped to **FAILED** on publish —
  the Buffer publish path was video-only, sending the image URL as a `video` asset. Buffer rejected
  it (`Video URL returned unsupported content-type: image/png`). `social_buffer.create_post` now
  takes `media_kind` and ships an `image` asset (`{image:{url}}`) with Instagram `type: "post"`
  instead of `reel` (image asset shape + PostType verified via live Buffer GraphQL introspection).
  `_do_publish` forwards `row.media_kind`. Video publishing unchanged.

## v0.62.1 — 2026-07-01 — Fix: AI-generated image posts no longer fail

- **Bugfix**: AI-generated image posts landed as **FAILED** even though the ROG worker rendered a
  valid jpg and the callback returned 200. `_write_render_asset` was video-only (`_VIDEO_EXTS` +
  `_sniff_video`), so the incoming `media_ext=jpg` was rejected → `apply_render_callback` marked the
  post `failed`. The helper now accepts images too (`_IMAGE_EXTS`, reusing the existing content-based
  `_sniff_image`, saved as `image-<ts>.<ext>`). No schema change, no worker change; existing failed
  image posts can be retried from the dashboard.

## v0.62.0 — 2026-07-01 — Social: AI-generated image posts

- **AI image posts**: Photo mode gets a "My photo" / "AI image" sub-choice. "AI image" needs no
  upload — the backend submits a Kling **text→image** job (the ROG worker's `produce_blackvolt_image`,
  9:16, with a branded-gradient fallback) and the still comes back as the post's media. Renders in
  ~1 min and lands as a draft pending approval, like video.
- Design without a new field: an image post **with** a reference photo uses it directly (instant,
  v0.61.0); **without** a photo it AI-generates. `request_render` branches on that;
  `apply_render_callback` already writes assets by extension (`media_ext=jpg`) and now sets
  `cover_path` for images. Daily auto-posts still use your uploaded photo library (AI-image stays a
  manual, per-post creative choice to control Kling credit spend).

## v0.61.0 — 2026-06-30 — Social: photo or video posts + smarter daily auto-posts

- **Photo OR video posts**: "Generate a post" gets a Video / Photo toggle. A photo post uses the
  owner's uploaded image directly — no Kling video render — with AI-written caption + hashtags
  (`SocialPost.media_kind`, migration `0036`; `social.finalize_image_post`; `request_render`
  no-ops for image posts). AI-generated images remain a Phase-2 follow-up (needs the ROG worker
  extended to an image mode).
- **Daily auto-posts, image option**: per-tenant `social_daily_media` preference (Settings → Social
  auto-posts: Video / Photo / Mixed, default **Video** = opt-in). Photo days pull the newest photo
  from the tenant's uploaded `social/refs` library and **fall back to video** when it's empty.
- **Smarter daily topic**: `_smart_daily_brief` replaces the static angle rotation — it picks the
  topic from the best-converting UTM campaign / route (own analytics) plus a Denver seasonal demand
  hint, and always closes with a booking CTA (traffic → reservations). Still never auto-publishes;
  the owner approves every post.

## v0.60.1 — 2026-06-30 — Popular routes: teaser prices synced to flat zones

- Updated the `priceFrom` "from $X" teasers in `lib/seoRoutes.ts` (home Popular routes cards +
  `/rides/[slug]` landing pages) to match the v0.60.0 flat zones: Aurora/Cherry Creek/DTC/Red Rocks
  → DEN **$120**, Boulder → DEN **$190**, Denver → Vail **$390**, Breckenridge **$349**, Aspen
  **$790**. Bumped the Booking pre-quote placeholder from $74 → $120 (metro default).

## v0.60.0 — 2026-06-30 — Flat-rate zones (Denver metro, Boulder, mountains, COS, N. Colorado)

- **Fixed zone pricing**: rides whose pickup **or** dropoff falls in a named zone are now charged a
  fixed flat price instead of the metered fare — Aspen $790, Vail/Beaver Creek/Eagle $390, Summit
  County $349, Colorado Springs $359, Fort Collins/Wellington $280, Loveland/Greeley $249, Boulder
  $190, Denver metro (incl. **DEN airport**) $120. Anything outside every zone is still metered by
  distance + time (`services/zones.py`, wired into `booking.build_quote` before the legacy airport
  floor). Zone match is symmetric and precedence-ordered (specific mountain/city zones beat the
  Denver-metro catch-all, since the base is itself in the metro).
- **Fixed means fixed**: peak/surge never applies to a zone flat; extra-stop fee, group surcharge and
  discount codes still apply on top. Matching keys off the address's city component so a POI like
  "Aspen Grove, Littleton" prices as metro, not Aspen.
- **Per-driver zone prices**: new `rate_configs.zone_prices` JSON column (migration `0035`) + a "Flat
  zones" section in the dashboard Rates screen; each driver can override any zone's price. The
  customer quote shows a "Flat rate · <zone>" chip when a zone applies.

## v0.59.0 — 2026-06-30 — Smart reservation: multi-reservation batch + recoverable scans

- **Batch extraction**: `Add ride → Smart` reads several requests at once. The backend now runs one
  vision call per screenshot and **groups results by client** (phone, else name; a key-less
  follow-up bubble continues the most recent reservation), returning a LIST of reservations instead
  of one merged result. `extract_reservation(..., merge=True)` keeps the single-reservation behavior
  for filling one existing ride (RideDetail).
- **Review queue**: when a scan yields more than one reservation, `AddRide` shows a chip queue (one
  draft per client, with ready/missing/created status), lets the driver edit each, and create them
  individually or via **Create all ready**. Nothing is saved until confirmed; a summary screen lists
  every created ride.
- **Recoverable retry**: a **Start over** button on the capture screen, and explicit messages when a
  file isn't an image or the screenshot limit is hit — instead of silently dropping files.
- **Limit**: `SMART_MAX_IMAGES` raised 5 → 6 (compose default + `.env.example`).
- API: `POST /rides/extract` now returns `{reservations, simulated, count}` (was `{fields, ...}`) and
  accepts a `merge` form field. Backend `test_smart.py` updated + grouping cases (16 tests).

## v0.58.0 — 2026-06-29 — Reviews: centralized cross-tenant moderation + driver attribution

- **Cross-tenant moderation**: the platform owner's review panel (`/dashboard/reviews`) now lists,
  approves, hides, replies to and deletes reviews for **all drivers**, not just the owner's tenant.
  Admin endpoints (`list_admin`/`patch_review`/`delete_review`) accept `tenant_id=None` → all tenants;
  safe because only the platform owner passes `require_admin` (revisit if per-tenant admins land).
- **Driver attribution**: `list_admin` joins `Tenant` and returns `tenant_name`/`tenant_slug`; each
  review card shows a driver badge, and a driver dropdown filters the panel to one driver.
- **Profile attribution**: a review left on a driver's public profile (`/review?driver=<slug>`) is
  routed to that driver's tenant (`submit_review` resolves `tenant_slug`), so the badge is truthful.
  Invites created from a ride inherit the ride's tenant; candidates picker spans all drivers.
- No schema change (no migration). Backend 479 tests (+5 cross-tenant/attribution).

## v0.57.0 — 2026-06-29 — Insights: visual booking funnel + conversion by campaign

- **Visual funnel** (`components/bv/dash/charts.tsx::FunnelChart`): the booking funnel is now
  descending bars (started → reviewed → paid → confirmed) with % of start and a hover tooltip
  (conversion vs previous step + drop-off).
- **Conversion by UTM campaign**: `summary()` adds a `campaigns` block computed by **session
  attribution** (funnel events carry no utm; only `session_start` does, joined by `session_id`).
  Insights gets a campaign selector that re-scopes the funnel + a per-campaign conversion table
  (starts → confirmed %). Funnel steps now count **distinct sessions** (real conversion), not
  raw clicks (`sign_in`/`book_pay_failed` remain event counts).
- No migration. New deterministic backend test for session-based funnel + campaign attribution.

> Note (ops, not code): review-request emails send fine (Resend returns 200) but the sending
> domain `send.blackvoltmobility.com` is **missing its SPF TXT record** (DKIM is present, DMARC
> = quarantine), so Gmail routes them to Spam. Add the SPF (and bounce MX) record shown in the
> Resend dashboard to land them in the inbox.

## v0.56.0 — 2026-06-29 — Insights: interactive charts + accurate time metrics

- **Interactive charts** (`components/bv/dash/charts.tsx`, zero-dependency SVG): `TrendChart`
  plots visitors + pageviews over time with a hover crosshair + tooltip; `Donut` shows the
  device mix with hover highlight + center readout. Wired into `Insights.tsx`, replacing the
  static pageviews bars; the device list became a donut.
- **Data correctness**: capped time-on-page at 30 min (`MAX_DURATION_MS` in
  `services/analytics.py`) at ingest **and** in the `summary()` aggregates (`LEAST(...)`), so an
  idle/backgrounded tab no longer inflates `avg_session_ms` / per-page averages. Verified the
  summary matches raw `analytics_events` counts (pageviews/visitors/sessions) on prod.

## v0.55.0 — 2026-06-28 — Automatic review requests after each ride

Closes the reviews loop: completed rides now trigger an automatic review-request email.

- **Scheduler** (`services/scheduler.py`): a 15-min interval job calls
  `reviews.send_due_reminders`, which emails a review request to riders whose ride completed
  ~N hours ago. Per-tenant enable + hours (`tenants.review_reminders_enabled` /
  `review_reminder_hours`, migration `0034`, **off by default / 3h** — opt in from Settings);
  global kill-switch + `REVIEW_REMINDER_LOOKBACK_HOURS` in config so enabling never blasts
  old rides.
- Dedup via any existing `ReviewInvite`/`Review` for the ride (manual requests and repeats are
  skipped); uses `updated_at` as the completion proxy within a bounded window; **email only**
  (the SMS path stays a manual deep link). The created invite makes the resulting review
  VERIFIED. Owner controls it from **Settings → Auto review requests** (toggle + hours).
- Verified: 4 new backend tests (due once, dedup, too-recent skip, no-email skip, tenant
  off-toggle) + full suite green, ruff clean, no new migration drift; scheduler registers the
  job cleanly; settings endpoint round-trips the flags.

## v0.54.0 — 2026-06-28 — Customer reviews: collect, moderate & request

A full first-party reviews system (replaces the empty testimonials placeholder).

- **Backend** (`models/review.py`, mig `0033`, `services/reviews.py`, `api/v1/reviews.py`):
  `Review` + `ReviewInvite` tables (tenant-scoped). Public endpoints to submit a review
  (always `PENDING`), list approved reviews per surface, and resolve an invite token; admin
  endpoints (`require_admin`) to list/approve/reject, toggle `show_on_home` / `featured`,
  reply, delete, list completed-ride candidates, and create review-request invites. Reviews
  are VERIFIED when they come from an invite token or a signed-in passenger reviewing their
  own ride. Owner is emailed (Resend) on each new review.
- **Request a review**: admin picks a past customer and sends via **email** (Resend), **text**
  (an `sms:` deep link from the owner's phone — no Twilio), or **copy** (message + link).
- **Frontend**: `StarRating`, `ReviewsStrip` (home / route / profile islands), `ReviewForm`,
  public `/review` and `/review/[token]` pages, a "Leave a review" CTA on completed trips, and
  an admin `dashboard/reviews` panel. Approved reviews surface on home, route pages, and the
  driver profile. EN + ES.
- Verified: 10 new backend tests + full suite green, ruff clean, no migration drift; frontend
  tsc + lint + build clean; submit→moderate→home loop verified end-to-end; no mobile overflow.

## v0.53.0 — 2026-06-28 — Route pages: premium hero, real route map & trust signals

Upgraded the `/rides/[slug]` landing pages from text-only to premium, conversion-ready pages —
to convert the paid/organic traffic we're about to drive.

- **Hero** (`page.tsx`): full-bleed luxury-EV photo with brand gradient + H1 + fast-fact chips +
  primary CTA. Per-route hero/alt via `routeHero()` (defaults by category) in `seoRoutes.ts`;
  hero also feeds the OpenGraph image for richer social shares.
- **Real route map**: committed static maps at `/assets/maps/<slug>.webp` — generated by
  `scripts/gen_route_maps.py` from OpenStreetMap tiles + the real OSRM driving line, recolored
  to the Void-Black brand theme (zero runtime cost, no API key). The project's Google key only
  has Distance Matrix enabled, so Static Maps isn't used.
- **Trust signals** (`RouteTrust.tsx`): factual badges — owner-driven, fully insured, 100%
  electric, flat upfront price, flight-aware, private. No invented reviews/ratings. A
  `testimonials?` field renders real quotes only when present (empty for now).
- Mobile-first; verified at 390 / 820 / 1200.

## v0.52.1 — 2026-06-27 — Route pages discoverable from home & footer

Internal linking so the new `/rides` pages are reachable from the site (not only via Google),
which also helps SEO.

- **Home**: new "Popular routes" section (`Landing.tsx`) with cards to the top routes + a
  "See all routes" link to `/rides`. Works on mobile (body content), unlike the desktop-only
  header nav.
- **Footer** (`WebShell.tsx`): added Book / Routes / top-route links and replaced the outdated
  "Denver / Aurora, CO" with the full service area (Denver metro · DEN · Vail/Breck/Aspen).
- i18n keys added (EN/ES): `home.routes.*`, `footer.area`, `nav.rides`.

## v0.52.0 — 2026-06-27 — SEO route landing pages for organic traffic

Foundation for free, long-term organic traffic — built to avoid Google's "doorway page"
penalty (each page is hand-written with unique content, not templated).

- **8 curated route/use-case pages** at `/rides/[slug]` (`lib/seoRoutes.ts` + server components
  with `generateStaticParams`/`generateMetadata`): Aurora→DEN, Cherry Creek→DEN, DTC corporate→DEN,
  Boulder→DEN, Red Rocks concert rides, and Denver→Vail/Breckenridge/Aspen. Each has unique copy,
  a real example fare (anchored to the live /quote engine), highlights, and a route-specific FAQ.
- **Deep-link CTAs**: each page links to `/book?from=…&to=…&ref=…&utm_campaign=<slug>` and
  `Booking.tsx` now reads `?from`/`?to` to prefill the trip → visitor lands on an instant quote,
  conversion attributed by campaign in Insights.
- **`/rides` hub** page + nav link (EN/ES) for discovery and internal linking.
- **SEO foundation**: `app/sitemap.ts`, `app/robots.ts`, `metadataBase` + default OpenGraph in the
  root layout, `LocalBusiness` JSON-LD on the home page, and `Service` + `FAQPage` + `BreadcrumbList`
  JSON-LD on each route page.

## v0.51.0 — 2026-06-27 — Service area: full Denver metro + mountain resort transfers

Expanded the stated service area to match what Black Volt actually serves (base: Aurora 80016).

- **Backend** (`social.py` `_brand_ctx`): the service framing now covers the whole Denver metro
  (including Boulder), DEN airport both ways, and a new high-value segment — luxury mountain-
  resort transfers to Vail, Breckenridge & Aspen. The AI brief + deterministic template CTAs
  (EN/ES) mention the mountain transfers so generated social posts pitch them.
- **Frontend**: landing hero subtitle (EN/ES) rewritten to state metro + DEN + mountain
  coverage; new coverage line on the booking page (`book.coverage`, EN/ES).

## v0.50.0 — 2026-06-27 — Booking funnel: show price first + reliable conversion tracking

Prep for paid traffic: verified the dashboard booking funnel end-to-end and plugged the leaks
before spending on visits.

- **Removed the price wall** (`backend/app/config.py`): `REQUIRE_AUTH_TO_QUOTE` now defaults to
  `False`, so anonymous visitors see their fare immediately instead of hitting a sign-up wall
  before any price (the biggest cold-traffic drop-off). Lead attribution is preserved — sign-in
  is still required to create a ride and carries the `?ref`/`bv_ref` driver attribution. The
  wall stays available per-tenant for lead-capture mode. `Booking.tsx` moved the sign-in prompt
  from the quote step to ride creation (401 on create → sign in → auto-retry).
- **Reliable funnel measurement** (`Booking.tsx`): each stage now counts at most once per
  session (no `book_start` inflation from reloads/back-nav); `book_review` ("reviewed route")
  fires only when a price is actually shown, not just on reaching the step.
- **Payment-failure visibility**: new `book_pay_failed` event on declined cards / failed ride
  creation, surfaced in the dashboard Insights funnel (`analytics.py` summary + `Insights.tsx`,
  EN/ES) so drop-off at the payment step is visible.
- **Verified live**: `/api/v1/track` accepts events on both apex and `app.` hosts (202); UTM /
  referrer / device are captured for source attribution.

## v0.49.0 — 2026-06-27 — Social posts: general luxury-EV focus + reference-photo matching

Reworked AI social-post generation (`/dashboard/social`) on two owner complaints: posts
were forced to name the specific car, and an uploaded reference photo only matched the first
shot while the rest showed unrelated vehicles.

- **General, fact-led content** (`backend/app/services/social.py`): the brief no longer
  builds every post around `{vehicle}`. Both the AI prompt (`_ai_brief`) and the deterministic
  fallback (`_template_brief`) now open with an attention-grabbing fact about luxury electric
  vehicles, stay general (a specific model may be mentioned but isn't the subject), and place a
  single CTA at the end (book a luxury EV for door-to-door rides + DEN transfers both ways).
- **Generic visuals when no photo**: `_VP_SYSTEM` + `_template_video_prompts` depict "luxury
  electric vehicles" in general rather than a pinned model.
- **Reference-photo matching**: when a photo is attached, `request_render` derives a concrete
  vehicle description from it via vision (`_describe_vehicle_visual` / `_vehicle_match_from_ref`),
  injects it into every Kling prompt (`_ensure_vehicle`), and passes `vehicle_match` to the
  render worker. The worker (`bv_producer.py`) now anchors the ad in the uploaded car —
  multiple distinct Ken Burns motion variants + i2v of the SAME photo make the majority of the
  body — and fills only the remaining ambiance with description-matched AI shots, so vehicles
  no longer mismatch.

## v0.48.1 — 2026-06-26 — Driver profile: links, booking host, slug & vCard

Fixes to the public driver profile (`/d/<slug>`) reported on `app.blackvoltmobility.com`.

- **Social links**: the Instagram link no longer double-prefixes the URL (it broke when a full share URL with `?igsh=…` was pasted). Instagram/website now render as modern icon+label pills via normalizers (`instagramHandle`/`instagramUrl`/`websiteUrl`); the Instagram value is also normalized to a handle on save in Settings.
- **Booking host**: "Book a ride" and the shared profile link/QR (`publicProfileUrl`) now target the public apex host via `publicSiteOrigin()` (strips the `app.` dashboard subdomain). "Book a ride" carries `?ref=<slug>`, and the booking page persists it (`setRef`) before the sign-in wall so the lead is attributed to the driver and priced against their rate across the host boundary.
- **Profile slug**: the default tenant slug is renamed `black-volt` → `ender-ocando` (migration `0032`); `black-volt` keeps resolving via `SLUG_ALIASES` (profile fetch + referral) and a frontend redirect, so existing links/QRs don't break.
- **Save contact**: the downloaded vCard now includes structured name, org, title, phone, profile/website/Instagram URLs, bio, and the embedded avatar photo (base64, RFC 2426 folded; URI fallback on CORS failure).

## v0.48.0 — 2026-06-26 — Mandatory client/driver agreement signing

Passengers and drivers must accept their required legal agreement before using the app.

- **Client terms (passengers)**: a non-dismissable, full-screen step shows the client terms (markdown) with a clickwrap "I have read and accept" checkbox; booking is gated until accepted.
- **Driver agreement (drivers/owners)**: requires a typed full legal name as an electronic signature in addition to the checkbox before the dashboard unlocks.
- Bilingual (EN/ES), follows the app locale; re-fetches and re-prompts if the document version changed (409) between load and accept.
- **Frontend**: new `GET /auth/me.agreements_pending` drives the gate; new `lib/agreements.ts` API client + `AgreementGate` component (with a small dependency-free markdown renderer), wired into `AuthGuard` (staff/drivers) and `WebShell` (passengers).

## v0.47.1 — 2026-06-26 — Social video voice no longer reads hashtags

Bug fix: the generated social video's voiceover was reading the hashtags aloud.

- **Root cause**: the AI brief asks for three fields (`SCRIPT`/`CAPTION`/`HASHTAGS`), but the prompt didn't forbid hashtags inside `SCRIPT`, and `_parse_brief` stored whatever followed `SCRIPT:` verbatim — so `#tags` leaked into `SocialPost.script`, which is the exact text sent to the TTS render worker.
- **Fix**: new `social._voice_script()` strips `#tag` tokens (and the resulting stray spaces before punctuation) from any text destined for the spoken voice. Applied in `_parse_brief` (new posts) **and** in `request_render` (so drafts already in the queue render cleanly without regenerating). The LLM `SCRIPT` instruction now explicitly says "spoken narration ONLY, NO hashtags". The `caption`/`hashtags` fields are untouched — hashtags still appear in the published post text.
- Tests: `test_voice_script_strips_hashtags`, `test_parse_brief_strips_hashtags_from_script_only` (28/28 in `test_social_service.py`).

## v0.47.0 — 2026-06-26 — Rider cancellation + driver refund decision, driver contact fix & new-ride emails

Riders can self-cancel; the driver chooses the refund when a late cancellation warrants a fee. Plus the /trips driver-contact fix and driver email notifications.

- **Rider cancellation**: new passenger-scoped `POST /rides/{id}/cancel` (auth + ownership-checked, idempotent). Riders may cancel a `QUOTED`/`CONFIRMED`/`ASSIGNED` ride; once the driver is `EN_ROUTE` it's rejected (409). Cancelling sets `cancelled_at` and removes the Google Calendar event.
- **24h refund policy**: cancelling **≥24h** before pickup (or with no scheduled time) auto-refunds in full — an `AUTHORIZED` hold is voided, a `CAPTURED` charge refunded. Cancelling **<24h** before pickup leaves the payment pending the driver's decision.
- **Driver refund decision**: new staff-scoped `POST /rides/{id}/refund-decision` with `fee_pct ∈ {0,20,30}` — full refund, or keep a 20%/30% cancellation fee and refund the rest. Fee eligibility (<24h) is enforced server-side; an uncaptured hold is captured in full then partially refunded. `payments.refund_payment` now supports a bounded partial `amount`; new `payments.settle_cancellation` orchestrates void/refund/fee. New `payments.refunded_amount` (cents) records the refunded portion. Payment lookup is scoped to the ride's owning tenant so discount-handoff rides settle correctly.
- **Driver contact on /trips (bug fix)**: `GET /rides` / `GET /rides/{id}` now resolve the assigned driver from `assigned_tenant_id` **or** the ride's owning `tenant_id` (gated on a phone being present), so a normally-booked ride surfaces the owner-driver's name/phone/vehicle — fixing "Driver to be assigned" with disabled call/text buttons on the rider's own confirmed ride.
- **Driver email notifications**: the driver is emailed (via Resend; best-effort, never blocks the flow) when a ride is confirmed (`authorize_for_ride` + `confirm_ride`) and when a ride is cancelled (with a "review the refund" prompt for within-24h cancellations). Recipient resolved from the driver tenant's `AllowedUser`.
- **Frontend**: My Trips gains a "Cancel ride" action with a 24h cancellation-fee warning; the driver dashboard ride detail shows a refund-decision panel (Full refund / Keep 20% / Keep 30% with computed amounts) on within-24h cancelled rides. New `cancelRide` / `refundDecision` API clients; bilingual i18n keys added.
- **Migration**: `0030_cancellation_fields` adds `rides.cancelled_at` and `payments.refunded_amount` (both nullable, reversible).

## v0.46.0 — 2026-06-26 — Pay-at-drop-off booking + real My Trips with driver contact

Two booking improvements and a real /trips page.

- **Pay at drop-off**: the payment step now offers "Pay now" (card via Square) or "Pay at drop-off" — the latter confirms the ride as pay-on-completion (cash; the driver collects at the end) with no online charge. New passenger-scoped `POST /rides/{id}/confirm` (ownership-checked, idempotent) moves the ride to CONFIRMED with method `cash`, unpaid.
- **Payment-gated confirmation (bug fix)**: a web booking now starts as a QUOTED draft and is only CONFIRMED — and only then synced to the driver's Google Calendar — once the rider completes the payment step (pays online or commits to pay-at-drop-off). Previously the ride was confirmed and placed on the calendar *before* payment, so an abandoned booking still landed on the driver's schedule. Calendar sync is now gated to active confirmed statuses (`_CALENDAR_VISIBLE`); Square authorization also triggers the sync.
- **Real My Trips**: the /trips page now renders the rider's real upcoming and past rides from the API (no more mock data), split into Upcoming/Past with status, schedule, fare and flight number, with loading/empty/error states.
- **Call/text your driver**: once a driver is assigned, a trip shows Call and Message buttons that open the phone's dialer (`tel:`) / SMS app (`sms:`). The assigned driver's contact (name, phone, vehicle, rating) is exposed only on the rider's own rides via `dashboard.assigned_drivers()`.
- **Chore**: cleaned up pre-existing lint (unused imports, over-long lines, import order) in `test_discounts.py`, `test_pricing.py` and migration `0029`.

## v0.45.1 — 2026-06-26 — Discount codes: redeem on payment & owner-driver pricing

Refinements to the discount-codes feature shipped in v0.45.0.

- **Redeem on payment success**: a code's use is now counted only when the payment is authorized, not when the ride is created. Abandoned or failed bookings no longer waste a code's available uses. The redemption is atomic (claim + increment in a single transaction), so retries and concurrent payments can't double-consume a code, and payment is never blocked if a code runs out between booking and paying.
- **Owner-driver pricing**: when a ride is booked with a driver's discount code, the base fare is now computed from that driver's own rate config (not the booking site's), with the discount applied on top — so the quote shown matches the amount charged.

## v0.45.0 — 2026-06-25 — Discount codes on booking, driver codes module & admin campaigns

Passengers can now apply discount codes at booking. Drivers manage their own promo codes from the dashboard. Admins can create multi-driver campaigns that generate a unique code per selected driver in one step.

- **Discount codes at booking**: the booking flow now has a code field — clients enter a promo code and the fare is reduced in real time before payment. Codes are validated against the backend and error states (expired, not found) surface clearly.
- **Reservation-only booking**: on-demand "Now" rides have been removed. All bookings are scheduled — passengers always pick a date and time.
- **Driver discount-codes panel**: new Discounts section in the driver dashboard. Drivers can create promo codes (capped at 50%), toggle codes active/inactive, and delete them. Codes are shown with uses, expiry and active status.
- **Admin campaign creator**: admin users see an additional Campaign section on the same page. One form lets the admin name the campaign, set discount % (1–100, uncapped), max uses, expiry, and pick one or more drivers from a checklist (with "All drivers" shortcut). The backend generates one unique code per selected driver and the UI shows the code alongside its driver email.

## v0.44.0 — 2026-06-25 — Social posts cross-post to TikTok

Black Volt's generated social videos now publish to TikTok automatically, alongside Instagram and Facebook, via the owner's connected Buffer account.

- **TikTok added to default publish targets**: `_DEFAULT_TARGETS` now includes `tiktok`, so every owner-approved post is routed to the connected TikTok channel. `_do_publish` already skips any platform whose `SocialAccount` isn't connected, so tenants without TikTok are unaffected and Instagram/Facebook behaviour is unchanged.
- No new endpoints or schema changes. Activation is config-only: the Black Volt Buffer account (org `6a36d65c…`) holds the TikTok + Instagram OAuth; the backend reads `BUFFER_API_KEY` / `BUFFER_ORG_ID` and posts via `social_buffer`. Connect/refresh the channel from Dashboard → Social → Accounts (Sync).
- **Security (multi-tenant)**: the shared Buffer account is now gated to the owner tenant via `OWNER_TENANT_ID`. Sub-tenant workspaces can no longer sync the owner's channels or publish through the owner's account (`sync_buffer_channels` returns empty and `_do_publish` falls back to simulated for non-owner tenants). Closes a pre-existing path where another tenant's admin could attach Black Volt's IG/TikTok to their own workspace.

## v0.43.0 — 2026-06-25 — Ride preferences (account + onboarding + per-ride + driver view)

Passengers can now set standing ride preferences and tune them per ride; drivers see them on the ride.

- **Account → Ride preferences panel**: conversation (happy to chat / prefer quiet), temperature (cooler / warmer), music (none / soft / driver's choice), help with luggage, pet / service animal, and a free-text note (e.g. allergies). Each dimension defaults to "no preference". Saved optimistically.
- **Onboarding gate**: optional, collapsible "Ride preferences" section so new riders can set them at sign-up without lengthening the required form.
- **Per-ride**: the booking flow prefills the rider's standing preferences and lets them change them for that single ride or keep the defaults. The chosen values are snapshotted onto the ride.
- **Driver ride detail**: shows the ride's effective preferences (per-ride snapshot, falling back to the client's standing preferences), hiding any neutral values.
- Backend: `clients.ride_preferences` (JSONB) + `rides.ride_preferences` (JSON snapshot), validated by a `RidePreferences` schema (enum dimensions, notes ≤ 500 chars; notes treated as PII, never logged). Migrations `0025` + `0026`. Extends `PATCH /me/profile` and `POST /rides` (no new endpoints; `require_passenger`/scoping unchanged).
- i18n EN + ES for all new strings; new icons (thermometer, briefcase, paw-print, chevron-up).

## v0.42.2 — 2026-06-25 — Driver accounts routed away from the customer portal (fix `passenger_only`)

**Fix:** a driver/owner who signed into the customer site hit `passenger_only` when saving "Complete your profile" — the passenger-only `/me/*` endpoints reject non-passenger sessions, but the client account page and onboarding gate still rendered for them. Root cause surfaced while debugging margie240478, who was on the driver access list (so she authenticated as an owner with no `client_id`) despite being a customer.

- **Frontend guard:** `components/bv/web/WebShell.tsx` now treats only `role === "passenger"` sessions as customers. A driver/owner who signs in on the customer site is sent to their dashboard with a notice (`auth.driverPortalNotice`, EN+ES) instead of a broken passenger profile form. Backend `require_passenger` is unchanged (access control intact).
- **Data:** the specific account was re-classified as a customer (removed from the driver access list) so it signs in as a passenger and the account page works normally.

## v0.42.1 — 2026-06-25 — Account fixes: dialog address autocomplete + visible default address

**Two follow-up fixes to the v0.42.0 account page, both reproduced on production.** Frontend-only (no backend or schema change).

- **Address autocomplete clipped in dialogs (fix):** the Google Places suggestion dropdown was being clipped by the modal card's `overflow-y: auto` in the "Add address" and "Complete your profile" dialogs — lower suggestions were cut off and the card gained a scrollbar (`/book` was unaffected since it isn't a modal). Fix: the dialogs now scroll on the overlay with `margin:auto` on the card, so the absolutely-positioned dropdown is never clipped. Applies to `components/bv/web/AddressEditor.tsx` and `components/bv/web/ProfileGate.tsx`.
- **"Complete your profile" saved but showed no change (fix):** the gate persisted `home_address` correctly, but the account page never displayed it (and it's separate from the Saved-addresses book), so updating it looked like nothing happened. The profile card now shows the default address (`acct.defaultAddress`, EN+ES) under the phone. `components/bv/web/Account.tsx`.

## v0.42.0 — 2026-06-24 — Account page that actually works (saved addresses, honest payment, saved preferences)

**The client `/account` page was mostly non-functional: "Saved addresses" and "Payment method" were hardcoded fakes, and the SMS/Email/language toggles reset on reload.** This wires every section to real, tenant- and client-scoped data.

- **Saved address book** (new): passengers add, edit, delete and choose a default address — with the same Google Places autocomplete as `/book`. New `client_addresses` table (migration `0024`), service-enforced "exactly one default" invariant, and CRUD under `/api/v1/me/addresses` scoped to the session's own `client_id`+`tenant_id` (cross-client/cross-tenant access returns 404). New `app/models/client_address.py`, `app/services/addresses.py`, `app/api/v1/addresses.py`; frontend `lib/addresses.ts` + `components/bv/web/AddressEditor.tsx`.
- **Honest payment section**: removed the fake "Visa ···· 4242" card. The panel now states plainly that payment is collected per ride at booking via Square, with no card stored on file.
- **Persistent preferences**: SMS consent, a new **email consent** (`clients.email_consent`, migration `0024`) and **language** (`clients.lang`) now persist through `/me/profile` and survive reloads. `ProfilePatch`/`profile.serialize` extended with `email_consent` + `lang` (normalized to EN/ES, served lowercase for the i18n).
- **Mobile-first**: address rows, action buttons and the editor modal work on phone, tablet and desktop (verified 390/820/1200).
- **Tests**: new `tests/test_me_addresses.py` (12 cases — CRUD, default-uniqueness, delete-promotes-oldest, cross-client/cross-tenant isolation, auth) + 3 added to `tests/test_me_profile.py` (email_consent + lang persistence/normalization).

## v0.41.0 — 2026-06-24 — Branded date & time picker (dashboard + client booking)

**Picking a date and pickup time is now fully tap-and-click on every device, and clients can finally schedule a ride for later.** Native inputs (v0.40.1) still felt like "typing segments" on desktop, and the public booking form's "Schedule" toggle was dead — it showed no fields and never sent `scheduled_at`, so a client could not book for later at all. The backend already accepts `scheduled_at` (`RideInput`), so this is a frontend change.

- **Shared helpers** (`lib/datetime.ts`, new): `pad2`/`normDate`/`normTime`/`buildScheduledAt` moved out of `AddRide.tsx` (single source of truth for the v0.40.1 "never save a timeless ride" rule), plus `formatDateDisplay`/`formatTimeDisplay` (locale-aware via `Intl`).
- **Branded picker** (`components/bv/DateTimePicker.tsx`, new): `BVDatePicker` (month calendar + Today/Tomorrow/+2d shortcuts, past days disabled) and `BVTimePicker` (common-time chips + AM/PM + hour/minute steppers). 100% clickable, identical on phone and desktop, in the Black Volt aesthetic. Reuses the existing popover style and outside-click/Escape pattern from `AddressAutocomplete`; value formats unchanged (`YYYY-MM-DD` / `HH:MM` 24h).
- **Dashboard** (`components/bv/dash/AddRide.tsx`): the date/time fields use the new pickers (drop-in; the submit guard and Smart/AI pre-fill via `normDate`/`normTime` keep working).
- **Client booking** (`components/bv/web/Booking.tsx`): selecting "Schedule" now reveals the date/time pickers and the ride is created with `scheduled_at`; "Now" stays immediate. Validation blocks advancing if "Schedule" is chosen without a date (`book.sched.err`, EN+ES).

## v0.40.1 — 2026-06-24 — Reliable scheduled_at on Add Ride (native date/time pickers)

**Fix:** the dashboard "Add ride" form could save a ride with `scheduled_at = null` — which silently kept it off Google Calendar (calendar sync, correctly, skips rides with no time). Root cause: the date field was free text parsed with `new Date(...)`, which fails on non-ISO/localized input (e.g. Spanish "24 jun") and returned `null` without warning.

- `components/bv/dash/AddRide.tsx`: date/time fields now use native `type="date"` / `type="time"` inputs (always emit `YYYY-MM-DD` / `HH:MM`, language-independent) with `colorScheme: dark` for the dark theme. Added `normDate`/`normTime` to coerce AI-extracted values into those formats so Smart mode keeps working. Added a submit guard: if a valid date+time can't be built, the form shows an error (`errDateTime`, EN+ES) instead of creating a timeless ride.

## v0.40.0 — 2026-06-23 — Per-user Google Calendar sync (members connect their own calendar)

**Fix:** a team member's saved/edited ride no longer lands on the admin's calendar (`blackvoltmobility@gmail.com`). Calendar sync was global — every ride was pushed to the single configured calendar regardless of which tenant owned it. Now each ride routes to the correct calendar by tenant, and non-admin members connect their own Google Calendar via OAuth (self-service). Four parts:

- **A) Backend — per-tenant routing** (`app/services/booking.py`): `sync_ride_to_calendar` and ride deletes resolve the target calendar via `_calendar_route(db, ride)` — admin/default tenant → the shared Black Volt calendar (unchanged); a member who connected their own calendar → their calendar; an unconnected member → **skipped** (never the admin's). `app/services/calendar.py` `upsert_event`/`delete_event` accept an explicit `service`/`calendar_id`, gained `service_from_refresh_token`, and a patch→insert fallback for events that moved calendars.
- **B) Backend — connect flow** (`app/api/v1/calendar_link.py`, migration `0023_calendar_credential`): `POST /api/v1/calendar/connect` (signed CSRF `state`), `GET /api/v1/calendar/callback` (code→token exchange), `GET /api/v1/calendar/connection`, `POST /api/v1/calendar/disconnect` (revokes at Google). Each member's refresh token is stored **encrypted at rest** (Fernet, `app/services/crypto.py`), keyed by tenant; scope is the minimum `calendar.events`.
- **C) Frontend — Settings card** (`components/bv/dash/Settings.tsx`, `lib/calendar.ts`): "Connect Google Calendar" with connected/email/disconnect states; admins see "uses the Black Volt calendar". EN + ES strings added.
- **Security / multi-tenant**: connect endpoints are staff-only; the tenant is always taken from the session token, never the request; `state` is HMAC-signed + time-boxed and re-checked against the session on callback; tokens are encrypted (fail-closed — never stored in plaintext) and never logged.

## v0.39.0 — 2026-06-23 — Client onboarding: profile gate right after Google sign-in

**New riders complete the data Google can't give us (phone, names) before their first booking continues, and passengers can finally edit their own profile.** Three parts:

- **A) Backend — profile data + completeness** (migration `0022_client_onboarding_profile`): `clients` gains `first_name`, `last_name`, and `sms_consent`. `verify_google_id_token` now also returns `given_name`/`family_name`, and `find_or_create_client` persists them, keeping the existing `name` synced to `"First Last"`. A profile is "complete" once it has first name + last name + phone (derived, no stored flag). `profile_complete` is added to `POST /login/google` and `GET /me` so the client can decide to show the gate without an extra round trip.
- **B) Backend — passenger self-service API** (`app/api/v1/me.py`, `require_passenger` dep): `GET /api/v1/me/profile` and `PATCH /api/v1/me/profile`, scoped by the session's `client_id` (`cid`) — never a body value. Phone is normalized to E.164 server-side (`app/services/phone.py`, US default, international allowed; invalid → 422). The backend is the source of truth.
- **C) Frontend — the gate** (`ProfileGate.tsx`): a blocking, mobile-first modal shown from `WebShell` right after a Google sign-in when `profile_complete` is false; saving resumes the booking, dismissing cancels. The optional default-address field reuses the booking `AddressField` (Google Places autocomplete). The Account page's Edit button opens the same gate, so passengers can edit their own profile. All strings added to EN + ES.
- **Security / multi-tenant**: profile endpoints require a passenger session with a `cid`; staff/admin/open-mode sessions are rejected. A passenger can only read/update their own record (the `cid` comes from the signed token, not the request).

## v0.38.0 — 2026-06-21 — Social: image adjustments — reject-reason steers the AI visuals + manage uploaded images

**The reject-with-reason correction now extends to images, and the owner can manage a post's uploaded images directly.** Two parts:

- **A) Reason + lessons steer the AI-generated visuals** (`_video_prompts`, `app/services/social.py`): the Kling visual prompts now receive the post's `rejection_reason` (as a per-render correction) and the tenant's accumulated lessons (`_tenant_lessons`, injected into `_VP_SYSTEM` as highest-priority visual preferences). Since prompts are built at render time, the next **Render** after a rejection produces scenes that reflect the feedback (e.g. "show daytime Denver, not night"), and visual lessons accumulate across future posts — reusing the existing `social_feedback` table (no migration).
- **B) Manage uploaded images on an existing post**: `UpdatePostBody` + `update_post` gain `reference_image_paths` (validated by `_clean_ref_paths` — tenant-prefixed, no traversal, cap 4). Changing a post's images sends it back to **draft** and clears stale render progress so the owner re-renders. Frontend (`v0.38.0`): an "Edit images" panel on the post card (reusing the 64×64 thumbnail + remove/add pattern) → `updatePost(id, { reference_image_paths })`.
- **Security / multi-tenant**: image paths are validated to the tenant's own `social/refs/` dir (`PATCH` stays `require_admin` + tenant-scoped); reason/lessons are trusted admin guidance injected separately from the untrusted `<topic>` data, preserving the visual-prompt output contract. No worker changes.

## v0.37.0 — 2026-06-21 — Social: reject with a reason → the system corrects the post and learns

**When the owner rejects a proposed post, they can now write *why* — the system instantly regenerates a corrected draft applying that reason, and accumulates the reasons as brand "lessons" injected into every future post so the AI stops repeating mistakes.**

- **db** (migration `0021`): `social_posts.rejection_reason` (Text) + new tenant-scoped `social_feedback` table (`tenant_id`, `post_id`, `reason`, `created_at`) — the growing log of owner lessons. New model `SocialFeedback` re-exported from `app/models/__init__.py`.
- **service** (`app/services/social.py`): `reject_post(reason=…)` now stores the reason, logs a `SocialFeedback` row, and **regenerates** the post's script/caption/hashtags via `generate_brief(correction=reason)`, then clears stale render progress (re-render stays manual). `_tenant_lessons()` returns the most-recent-distinct reasons (capped 12); `_ai_brief`/`generate_brief` inject them as high-priority "OWNER PREFERENCES" into **every** brief (so generate, generate-from-image and daily auto-posts all learn). Reject without a reason behaves exactly as before.
- **api**: `POST /social/posts/{id}/reject` gains an optional `RejectBody { reason }` (still `require_admin` + tenant-scoped; backward compatible with no-body callers).
- **frontend** (`v0.37.0`): the Reject button opens an inline reason textarea ("Reject & fix" / "Cancel"); the reason is sent to `rejectPost(id, reason)`. A corrected draft comes back and shows a subtle "You asked to change: …" note. EN/ES strings added.
- **Security / multi-tenant**: feedback is strictly tenant-scoped (one tenant never learns from another's). The owner's reason is trusted admin guidance (sanitized, capped 500) injected as a separate high-priority block — the untrusted `<subject>`/`<angle>` handling is unchanged, and the strict 3-line brief contract is preserved. No worker changes.

## v0.36.0 — 2026-06-21 — Social: live render progress bar (real worker-reported progress)

**While a Social post renders, the dashboard now shows a real progress bar with the current stage — not just a "Rendering" pill.** The render worker reports each stage back to Black Volt over the same signed channel it uses for the finished video.

- **Worker → backend progress** (`render_worker.py` + `bv_producer.py` on the ROG, worker `v2.8.40`): `produce_blackvolt` takes a best-effort `progress(stage, pct)` hook and emits it across the pipeline (`voiceover → images → scenes → backgrounds → assembling → encoding`), interpolating per uploaded image and per Kling visual. The worker POSTs each update to a new `progress_url` (derived from the callback URL) with the **same HMAC-SHA256 signature** (`x-bv-render-signature`), short timeout, errors swallowed — progress can never break or slow a render.
- **Backend** (`social_posts.render_progress` int + `render_stage`, migration `0020`): new signed webhook `POST /social/webhooks/render/progress` → `apply_render_progress` validates tenant+post, clamps progress to 0–100, only ever raises it (tolerates out-of-order POSTs), and treats the stage as opaque data. It never touches `media_path`/`status`. `request_render` initialises the bar (`progress=0`, stage `queued`).
- **Frontend** (`v0.36.0`): the queue polls `listPosts` every 3s **only while a post is `render_requested`** (capped at ~25 min), and `SocialMedia.tsx` draws a branded determinate bar from `render_progress` with a localized stage label — falling back to an indeterminate animation if a worker doesn't report progress. The finished video then appears on its own.
- **Security**: progress webhook is authenticated solely by the existing HMAC (no user auth), verified with `verify_render_callback` (constant-time). `progress_url` is server-derived from the trusted callback host; the worker only POSTs there.

## v0.35.0 — 2026-06-21 — Social: owner-uploaded reference images + generate-from-image + Denver framing

**The owner can now bring their own images into a post, or generate a whole post from a single image — and every post is grounded in the real service area (all of Denver ⇄ DEN airport, both directions).**

- **Reference images** (`social_posts.reference_image_paths`, migration `0019`): the "Generate a post" panel gets a multi-upload (≤4, png/jpg/webp/gif, 5 MB) via `POST /social/uploads`. Uploads are magic-byte sniffed, written atomically under the tenant's own `media/tenants/{id}/social/refs/` dir with a server-generated name, and the paths attached to the post are validated to that exact prefix (no traversal, no cross-tenant reference).
- **Worker animates them** (`bv_producer.py` on the ROG): uploaded images are turned into clips — **Hailuo image-to-video** first (real motion, ~2/day free quota), an elegant **Ken Burns** zoom as the always-available fallback — and placed first in the video (order: uploaded → Kling AI → branded gradient). The render request now carries `reference_images` (public `/media` URLs MiniMax fetches itself). One image failing never sinks the render.
- **Generate from an image** (`POST /social/posts/generate-from-image`): upload one photo → the vision model (Kimi/MiniMax, never Anthropic OAuth) derives a short subject (treated as untrusted data), then the normal MrBeast brief→draft flow runs with the image attached.
- **Always-on Denver framing**: brand context now carries the service area + DEN airport, injected into the brief, caption and visual prompts so posts reflect premium door-to-door rides across the whole Denver metro and **both-way** airport transfers — never rides outside it.
- The motion prompt for i2v is fixed brand text, never built from user input (no prompt-injection surface).

## v0.34.0 — 2026-06-20 — Social: publish for real via Buffer

**Approved posts now publish to real Instagram/Facebook/TikTok through the owner's Buffer account.** Buffer holds the platform OAuth tokens and does the actual posting, so Black Volt never touches Meta App Review or the TikTok Content Posting audit.

- **Buffer adapter** (`backend/app/services/social_buffer.py`): a thin async GraphQL client (`list_channels` + `create_post`) over `https://api.buffer.com`, authed with a personal API key read from `.env` (never logged, never returned, never in an exception message).
- **Connect = "Sync from Buffer"**: the Social → Accounts tab gets a Sync button that upserts a `SocialAccount` per Buffer channel (stores Buffer's channel id; our DB never holds a platform token). Disconnected platforms show a "Connect in Buffer" link. No DB migration (reuses existing columns).
- **Real publish**: `_do_publish` now pushes each connected target's rendered video (by public `/media` URL) to Buffer — **Instagram as a Reel**, publish-now via `shareNow`, scheduled via `customScheduled` + `dueAt` — and stores the Buffer post id. Simulated fallback retained when Buffer isn't configured (`SOCIAL_PUBLISH_VIA_BUFFER` + key gate; never silently simulates in prod).
- **Safety**: media URLs are validated to our own host before sending to Buffer (no SSRF); a *transient* Buffer/network error leaves a scheduled post for the next tick instead of burning it to `failed`; the scheduler takes `FOR UPDATE SKIP LOCKED` on due rows to prevent double-publish. New route `POST /social/accounts/sync` is admin-only + tenant-scoped.
- Inbox replies + engagement analytics stay on their current path (Buffer's API exposes those poorly) — deferred.

## v0.33.0 — 2026-06-18 — Social: real Black Volt video ads (own renderer, Kling visuals, language voice)

**The render is now a real Black Volt ad, not a BitTrader clip.** The live render was using BitTrader's `produce_single` (its crypto-channel orchestrator) → BitTrader logo watermark, Spanish-locked voice (mixed EN/ES), and a generic gradient fallback (Kling never fired for an "automotive" topic with no visual prompts). Replaced with a **dedicated Black Volt renderer**, `bv_producer.produce_blackvolt` (in the BitTrader repo, runs on the ROG worker), that reuses the low-level primitives but with Black Volt branding:

- **Language-aware voiceover** (edge-tts): `en-US` / `es-US` premium voice chosen by the post's `lang` — no more mixed-language audio.
- **Visuals = MIX**: a hero Kling text-to-**video** clip + Kling text-to-**image** shots animated with a Ken Burns zoom, from **AI visual prompts** generated for the brand (Kia EV9, Denver, premium night arrival). Backend now sends `video_prompts` + `lang` in the render job (`social._video_prompts`, LLM-grounded with a deterministic template fallback; topic treated as untrusted data). If Kling video credits are exhausted it gracefully uses AI **images** (still real, on-brand footage); if Kling is down it uses a branded motion background — never BitTrader's gradient.
- **Minimalist-premium assembly**: a small **BLACK VOLT** corner wordmark + an elegant **end card** (wordmark + "Silent Power. Premium Arrival."). No karaoke.
- **Web-safe encode** (H.264 high · yuv420p · `+faststart`) → plays in any `<video>` and downloads cleanly (fixes the earlier audio-only/black-screen file).
- **Worker robustness**: the mp4 callback now retries (4×, backoff, 90s) so a transient TLS/edge blip never strands a finished render.

**Verification.** 272 backend tests + ruff clean (no migration). Isolated render on the ROG and a **production E2E** (EN): real EV9/Denver AI visuals + BLACK VOLT mark + end card, `video/mp4` H.264 yuv420p +faststart served `200`, played and downloaded fine. Note: Kling **text-to-video** currently returns "balance not enough" — the mix uses Kling **images** until the AI-video account is topped up.

## v0.32.1 — 2026-06-18 — Social render go-live (render worker deployed; `SOCIAL_SIMULATED=false`)

**Ops — the render pipeline is now LIVE in production.** Added a containerized **render worker** to the stack (`render-worker/` — `python:3.12-slim` + ffmpeg + DejaVu fonts running `render_worker.py`, no published ports, reachable only inside the compose network). The VPS `.env` now carries a generated `SOCIAL_RENDER_SIGNING_KEY` shared by both sides, `SOCIAL_RENDER_URL=http://render-worker:8090/render`, `SOCIAL_RENDER_CALLBACK_URL=http://backend:8000/api/v1/social/webhooks/render`, and **`SOCIAL_SIMULATED=false`**. Tapping *Render video* now does a real signed round-trip: backend → worker → branded ffmpeg clip → HMAC-signed callback → validated + written under `/media` → played in the queue. Verified by a local round-trip on the exact compose topology (24 KB `video/mp4` served `200`) and a production E2E. **Content note:** the worker emits a **branded Black Volt clip** (it has no BitTrader AI pipeline) — wiring the full AI video (Hailuo/TTS/Whisper, which lives on the ROG) is the next step: run `render_worker.py` from the BitTrader repo on a host reachable from the VPS and repoint `SOCIAL_RENDER_URL` (see `docs/setup-social-media.md`). The Social module remains admin-only; the callback stays HMAC-only.

## v0.32.0 — 2026-06-17 — Social Media (Stage 2): real BitTrader render + admin-only

**Feature — real video render (hybrid bridge → BitTrader).** Rendering a post now produces an actual mp4. A new **dependency-free BitTrader worker** (`BitTrader/render_worker.py`, stdlib HTTP + ffmpeg) accepts an **HMAC-signed** render job from Black Volt (`render_client.submit` now signs the outbound body), runs `agents.producer.produce_single` (or an ffmpeg sample when the paid video APIs aren't configured), and **POSTs the finished mp4 back inline as base64 over an HMAC-signed callback**. Black Volt's `social.apply_render_callback` verifies the signature, then `_write_render_asset` validates it (base64 decode, ≤`SOCIAL_RENDER_MAX_MB`, **magic-byte sniff** for mp4/mov/webm, server-generated filename, extension allow-list) and writes it under the public `/media` mount via an **atomic temp-then-rename**. The callback is **idempotent** (only attaches to a `render_requested`/`failed` post → a replayed signed callback is a no-op, never orphaning a file). The frontend now plays the real clip in a `<video>` (placeholder only while simulated). No base64-URL fetch → **no SSRF surface**. Full cross-process E2E verified: post → render → worker ffmpeg → signed callback → mp4 written → served `HTTP 200 video/mp4`.

**Change — the Social module is admin-only.** The whole `/api/v1/social/*` surface is now gated to super-admins (`require_admin`; the render webhook stays HMAC-only), and the **Social** tab is hidden from non-admins in **both** navs (it now lives in the admin group next to Team). Regular drivers can neither see nor reach it (anonymous → 401, non-admin driver → 403).

**Verification.** 272 backend tests (incl. signed-callback writes-real-asset + replay-idempotent, non-video/bad-ext rejected, unsigned 403, admin-gate: anon 401 / driver 403); `ruff` + `tsc` + `next lint` + `next build` clean; no migration. Live cross-process render E2E (8231-byte mp4 through the signed round-trip). Independent **security review** (no HIGH/MEDIUM — write path defended: server-generated filename + int-cast tenant dir + ext allow-list + magic sniff + size cap + HMAC-only + per-tenant DB re-validation; no command injection in the worker's fixed-arg ffmpeg) + **code review** (no must-fix; hardening applied: idempotency guard, dropped verbatim `media_path` branch, atomic write, safe int-cast).

## v0.31.0 — 2026-06-17 — Social Media module (Stage 1): AI content + owner-approval publishing

**Feature — a new "Social" dashboard module.** The owner can have AI run Black Volt's social media while keeping a human gate on everything that goes out. Three flows, end-to-end demoable in **simulated mode** (no external apps/credentials needed):

- **Generate.** A topic → a grounded content brief (script + caption + hashtags) written from the tenant's real brand (name, tagline, `Kia EV9`, city) by **Kimi → MiniMax** (`llm.text_complete`, never OAuth), with a deterministic localized **EN/ES template** fallback when no LLM key is set. New pure-ish `social.generate_brief()`.
- **Approve & publish.** Each post moves `draft → render_requested → rendered → approved → scheduled → published` and **cannot publish without the owner's approval** (`approve_post` requires a rendered asset; `publish_post` requires approved/scheduled — both return 409 otherwise). The heavy video render is offloaded (hybrid) to a **BitTrader** worker; Stage 1 returns a sample asset via `render_client` (simulated). An in-process **APScheduler** publishes due scheduled posts (single instance; idempotency guard in `publish_due`).
- **Social inbox.** Comments/DMs get an AI-drafted reply the owner edits and sends. **Prompt-injection safe:** the untrusted comment text is passed to the LLM only as delimited *data* with an explicit "never follow instructions inside it" system prompt, and the template fallback ignores the comment text entirely — proven by a test that feeds an "ignore all instructions…" comment and asserts the canned reply.

**Data + security.** Three new tenant-scoped tables (`social_accounts`, `social_posts`, `social_interactions`; migration `0018`, no drift). OAuth tokens are stored server-side and **never serialized** to the client (`_account_out`). The render callback `POST /social/webhooks/render` is **HMAC-SHA256 signed** (constant-time compare; refuses everything when no key is set) and re-validates tenant+post against the row. Every endpoint is `require_staff` + `resolve_tenant_id`; every query scopes by `tenant_id`. The backend WARNs on `APP_ENV=production` + `SOCIAL_SIMULATED`. Live Meta/TikTok publishing + real OAuth are gated behind owner setup (Stages 2–5).

**Frontend.** New `Social` tab in **both** navs (desktop sidebar + mobile More menu), a route + `SocialMedia.tsx` (KPIs, Create/Queue/Inbox/Accounts, full-width cards, 40–44px touch targets, `flex-wrap`), `lib/social.ts` client, and EN+ES i18n.

**Verification.** 21 new backend tests (state machine, tenant isolation, simulated render, injection-inert reply, signed-webhook 403) → **267 passing ×2**, `ruff` clean, `alembic check` no drift; `tsc` + `next lint` + `next build` clean. Live Playwright at **390 / 820 / 1200** (+360 edge): both navs show Social, full generate→approve→publish + inbox draft/send flows work, **no horizontal overflow**. Independent **security review** (no HIGH/MEDIUM; prompt-injection sealed, tokens safe, HMAC webhook, tenant-scoped, no OAuth-for-LLM) + **code review** (no must-fix) on the diff.

## v0.30.0 — 2026-06-16 — My Stats: AI coach + visible "Revenue over time" bars

**Feature — AI coach.** A new full-width card on the **My Stats** tab, right above "Your funnel" / "Conversion rates", gives the driver one actionable nudge: *"talk to N a day for a ~Z% shot at K new private clients ≈ $X this week."* The figures are **always deterministic** — computed by a new pure `funnel_math.coach_insight()` (bottleneck stage = weakest smoothed rate; a modest cadence bump or the goal-required activity; clients/revenue projected via the existing `project()`; `P(≥1 client)` over the horizon). The AI's only job is to phrase those exact numbers, so it can never hallucinate a figure and the card still works (localized EN/ES template) when no LLM is configured. New `coach.recommend()` assembles the driver's real data (`funnel.summary()` + `platform_stats.summary()`, including a "convert K of your N platform trips to private" angle), writes the message with **Kimi → MiniMax** (`llm.text_complete`, never OAuth), and caches the AI text per tenant·locale·day in Redis (best-effort; any Redis failure degrades to recompute). **Prompt-injection safe:** only numeric/enumerated fields ever reach the LLM — never OCR/user free text (platform labels, currencies, notes). New staff-only, tenant-scoped `GET /stats/coach?lang=&refresh=`. No migration.

**Fix — invisible "Revenue/Conversations over time" bars + missing total.** The `Trend` component (`MyStats.tsx`) colored every non-"today" bar `var(--obsidian-3)` (near-black), so revenue — which lands on *past* days — rendered with no visible bars (same class of bug fixed for `MiniBars` in v0.29.1). Now **any day with a value is a clearly visible volt bar** (today brightest + glow; other days at 0.7 opacity), and each Trend panel shows its **total** beside the title (a new optional `right` prop on `Panel`). Frontend-only.

**Verification.** New pure `coach_insight` tests (bottleneck = weakest stage; suggested ≥ current cadence; `prob ∈ (0,1)` and rises with cadence; `low ≤ point ≤ high`; no-earnings path) + `/stats/coach` endpoint tests (401 staff-gate; no-key → `source:"template"` with the real figures and correct bottleneck; platform angle when platform stats exist; `refresh=1` → 200). `ruff`/`tsc`/`next lint`/`next build` clean; no alembic drift. Live Playwright across 3 viewports (Revenue/Conversations bars visible + totals; coach message + chips; Regenerate; no overflow at 360px). Security + code review on the diff.

## v0.29.1 — 2026-06-16 — Week chart: visible past-week bars + per-week totals in the picker

Two follow-ups to the v0.29.0 week navigator:

**Fix — invisible bars on past weeks.** `MiniBars` (`Overview.tsx`) colored every non-"today" bar `var(--obsidian-3)` (near-black), so a past week — where no day is "today" — rendered with no visible bars even though the total was correct. Now **any day with revenue is a clearly visible volt bar** (today brightest + glow; other earning days at 0.7 opacity), and only `$0` days stay a faint baseline. This also improves the weekly chart in the Team member drawer (`TeamMemberDetail.tsx`), which shares `MiniBars`.

**Per-week totals in the picker.** The week-picker dropdown now shows **each week's total** next to its date range. New staff-only, tenant-scoped `GET /dashboard/weeks?count=N` (`count` bounded 1–52, no migration) returns `[{offset, start, end, total}]` from a single grouped query (`dashboard.weeks_summary`, reusing `booking.earned_ride_filter()` + the service-day bucketing); the front (`getWeeksSummary` + `WeekChart`) fetches it when the dropdown opens and renders the total right-aligned per option (range truncates on the left so it fits at 360px).

**Verification.** 17 dashboard tests (3 new: `/dashboard/weeks` shape + offsets, batch totals equal the single-week endpoint per offset, `count` out-of-range → 422, staff-gate 401); 234 backend total; `ruff`/`tsc`/`next lint`/`next build` clean. Live Playwright across 3 viewports (past-week bars visible; dropdown shows totals; no overflow at 360px). Security + code review on the diff.

## v0.29.0 — 2026-06-16 — Week navigator on the dashboard "This week" chart

The Dashboard's **"This week"** card becomes a week browser (like the Uber Earnings screen): **‹ ›** arrows step to the previous/next week and a **date-range dropdown** jumps to any recent week. Each week renders its own daily Mon→Sun bars + total, keeping the Black Volt bar style. Mobile-first: the picker is an easy-to-tap **bottom sheet on phones** (z-indexed above the fixed tab bar, never clipped) and a popover on tablet/desktop; arrows are 44×44 touch targets; no horizontal overflow at 360px.

**Backend (no migration).** Extracted a reusable `dashboard.week_earnings(db, *, tenant_id, monday)` (+ `_monday_of`) from the inline current-week query — same `booking.earned_ride_filter()` + service-day (`coalesce(scheduled_at, created_at)`) logic — so a navigated week matches "This week" exactly. `stats()` now calls it (the `/dashboard/stats` contract is unchanged). New staff-only, tenant-scoped `GET /dashboard/week?offset=N` (0 = current, negative = past; `offset` bounded `[-260, 0]` so no future weeks and ~5-year cap) returns `{offset, start, end, total, days[7]}`.

**Frontend.** `getWeek()`/`WeekEarnings` in `lib/dashboard.ts`; a `WeekChart` component in `Overview.tsx` replaces the inline card — local `offset` state fetches the selected week, `weekRange()` formats the date label per locale (cross-month aware), and the dropdown lists the last 12 weeks. New EN+ES `dash.week.*` strings.

**Verification.** 231 backend tests (4 new: offset-0 equals the dashboard week total, a past week excludes today, future/out-of-range offsets → 422, staff-gated 401); `ruff`, `tsc`, `next lint`, `next build` clean. Live Playwright E2E across **3 viewports** — desktop (1280), tablet (820), phone (390): arrows change the week ($1973.99 → $74 → $148), the dropdown jumps weeks, the phone bottom sheet renders above the tab bar with 44px touch targets and no horizontal overflow. Security review + code review run on the diff.

## v0.28.1 — 2026-06-16 — Fix: My Stats reachable on mobile

The mobile bottom navigation (`DriverTabBar.tsx`) is a separate component from the desktop sidebar, with hardcoded `PRIMARY` (Dashboard/Rides/Clients/Inbox) and `MORE` (overflow sheet) lists. The new "My Stats" tab (v0.27.0) was added to the desktop sidebar but **not** to either mobile list, so it was invisible on phones. Added `stats` as the first item in the `MORE` sheet — it now appears under the bottom **More / Más** menu (still inline in the desktop sidebar). Frontend-only; no API/DB change.

## v0.28.0 — 2026-06-16 — My Stats: AI import of Uber/Lyft/Co-op platform income

A "Platform income" panel inside the My Stats tab. The driver uploads a screenshot of their **Uber / Lyft / co-op** earnings summary; the existing AI vision model (smart-vision, MiniMax-M3) reads **platform, period, trips, earnings, and online hours**; the driver reviews/edits the parsed draft and saves it. The panel then shows platform income over the window and a **platform-vs-private comparison** (the whole pitch: convert those gig riders into higher-margin private clients). Per the product decision, this is **context only — it never touches the sales funnel** (conversations are still logged by hand).

**Backend.** New tenant-scoped table `platform_stats` (migration **0017_platform_stats**). `services/platform_stats.py` mirrors the Smart-reservation vision flow with its own prompt/keys/sample (simulated fallback when there's no vision key) and adds `save_stat`/`delete_stat`/`summary`. The summary attributes each import to `coalesce(period_end, created_at)`, totals per platform, and computes the private earned revenue for the same window via the shared `booking.earned_ride_filter()`. Endpoints on the staff-only `/stats/*` router: `POST /stats/platform/extract` (multipart screenshots → parsed draft; gated behind an active subscription like the Smart upload), `GET /stats/platform` (summary + comparison), `POST /stats/platform` (save), `DELETE /stats/platform/{id}` (tenant-scoped → 404 cross-tenant). All inputs are bounded and clamped server-side; unknown platforms coerce to `other`.

**Frontend.** `PlatformIncome.tsx` in My Stats: upload → AI draft → review form (platform, period, trips, earnings, hours) → save; a private-vs-platform split bar with per-trip economics; and a list of recent imports with delete. `lib/platform.ts` reuses the Smart image-normalize helper. New EN+ES strings under `dash.stats.plat.*`.

**Verification.** 227 backend tests green (6 new: extract simulated, non-image reject, save/list/summary/delete roundtrip, clamping, gating); `ruff`, `alembic check` (no drift), `tsc`, `next lint`, `next build` clean. Live Playwright E2E: upload a screenshot → AI returns the Uber sample → the review form pre-fills (Uber, 42 trips, $884.50, 31.5h) → save → it appears in the summary, per-platform breakdown, and comparison. **Security review** and **code review** run on the diff.

## v0.27.0 — 2026-06-16 — My Stats growth dashboard + revenue/count fixes + delete cancelled rides

Three things in one release.

**1. Dashboard revenue/count fix.** "Revenue today" and "Week total" undercounted: they only summed rides with `paid=True`, so a *completed* cash ride the driver never toggled "paid" showed $0; and a cancelled-but-paid ride would have inflated revenue. "Rides today" counted only `scheduled_at == today` (missing ad-hoc rides with no schedule) and didn't exclude cancelled. Introduced a single shared predicate `booking.earned_ride_filter()` — a ride counts as revenue when it's **completed OR paid, and never cancelled/no-show** — used by revenue today, the weekly chart, and the funnel. `rides_today` now uses `coalesce(scheduled_at, created_at)` and excludes cancelled. Backend-only, no migration. New tests cover completed-unpaid revenue, cancelled exclusion, and ad-hoc counting.

**2. Delete cancelled rides.** New `DELETE /api/v1/rides/{id}` (staff-only, tenant-scoped → foreign-tenant ride 404s). Guarded to **cancelled/no-show only** (409 otherwise); removes the calendar event and detaches payment rows (`ride_id → NULL`, audit trail preserved) before deleting. Frontend: a **Delete** button in the ride detail drawer (cancelled rides only) with a confirm dialog.

**3. "My Stats" tab — the driver's growth dashboard.** The business runs on converting Uber/Lyft riders into private clients, so this tab tracks that sales funnel: **conversations → pitches → contacts → clients → revenue**. The top (effort) is logged by hand in a 10-second daily quick-log; the bottom (clients, revenue) is derived from real Client/Ride data. It shows the funnel, smoothed **conversion rates with a 90% confidence band** (Beta-Binomial smoothing + Wilson interval — honest with tiny samples, flagged `low data` until there's enough history), a logging **streak**, trend charts, a forward **projection** at the current pace, and a **goal calculator**: pick a weekly/monthly/yearly target ($ or clients) and it works backward to "talk to N people a day" with an effort range. New tables `driver_funnel_logs` + `driver_goals` (migration **0016_driver_funnel**), pure math module `funnel_math.py`, service `funnel.py`, API `/stats/funnel*`, and `MyStats.tsx` + `lib/funnel.ts`.

**Verification.** 221 backend tests green (28 new: funnel math, funnel API, ride delete, revenue semantics); `ruff`, `alembic check` (no drift), `tsc`, `next lint`, `next build` all clean. Live Playwright E2E: My Stats renders + computes, the daily quick-log saves and updates the funnel/streak, the goal calculator returns a daily number, and a cancelled ride deletes (404 after). Revenue fix verified end-to-end via API deltas. **Security review: no high-confidence issues** (authz, multi-tenant isolation, the new DELETE, input validation, SQL injection all pass). Code review clean (one i18n regression caught and fixed). All new strings in EN + ES.

## v0.26.1 — 2026-06-15 — Settings: Save button always works

Fix: the dashboard **Settings** "Save changes" button was gated solely on a dirty-diff (`disabled={!dirty || busy}`), so it rendered greyed-out (opacity 0.5, `onClick` ignored) and read as "there's no save button" — the owner couldn't save edits to Instagram, phone, etc.

Now the button is **always clickable while the profile is loaded** (`disabled={busy || !form}`) — `PUT /tenant/settings` is idempotent, so saving unchanged data is harmless. The `dirty` check is kept only to drive an **"Unsaved changes"** Pill that appears while editing (clear affordance), plus the existing "Saved" flash. Frontend-only; no migration, no API change. New EN+ES string `dash.settings.unsaved`.

## v0.26.0 — 2026-06-15 — Driver direct phone (gated to registered clients)

Drivers can now add a **direct phone** in dashboard Settings. It surfaces as **Call** and **Text** buttons (and a `TEL` line in save-to-contacts) on their profile (`/d/{slug}` and the *Your Driver* tab) — but **only to signed-in clients**. Anonymous visitors never receive it.

**Server-side gating (not just hidden in the UI).** The public endpoint `GET /api/v1/tenants/{slug}` omits the `phone` key entirely unless the request carries a valid session (`include_contact = current_payload(request) is not None`); `public_profile()` only adds `phone` when `include_contact` is true. The frontend `getPublicProfile()` now sends `credentials: "include"` so a registered rider's cookie travels and the backend includes the number. This honors the v0.25.0 registration wall — to get the driver's direct line you register first.

**Editing.** New `phone` (`String(40)`, nullable) on `Tenant` via migration **0015_tenant_phone** (additive); added to `TENANT_EDITABLE_FIELDS` so the owner-only `PUT /tenant/settings` persists it (session-scoped, write-whitelisted). New `phone` Field in Settings (`type="tel"`, with hint), and a reusable optional `hint` prop on the shared `Field`.

**Verification.** 2 new backend tests (settings roundtrip/trim + gating: anon → no `phone`, session → `phone`); full suite 195 green; `ruff`, `alembic check` (no drift), `tsc`, `next lint`, `next build` clean; live gating verified via curl (anon vs cookie) and Playwright (anon profile has no Call/Text; authed does; Settings shows the `tel` field). **Security review found no exploitable issues**; code review found only one intended dev-mode note. EN+ES strings added.

## v0.25.0 — 2026-06-15 — Per-driver public links + designated-driver attribution + registration wall

Every team driver's public profile (`/d/{slug}`) becomes a **shareable referral link** (Instagram bio, business cards, QR) that **activates the customer-side multi-tenancy** that was previously dormant — until now every public passenger was hard-pinned to the default `black-volt` tenant.

**Designated driver (permanent, first-touch).** A visitor who signs in through a driver's link is attributed to that driver for good: their `Client` is created under that driver's tenant, so their rides accrue to that driver and show in *that* driver's CRM. Mechanism: on Google login `find_client_by_google_sub()` does a deliberate **cross-tenant identity lookup** (the only one, like the global allow-list) and returns the oldest match — so a returning rider keeps their first driver on any device, and a later link from another driver never reassigns or duplicates them (`resolve_referral_tenant()` only attributes brand-new accounts, validated against a real entitled tenant, else falls back to default). The owner can still reassign manually as super-admin.

**Registration wall.** `/quote` now requires a session when `REQUIRE_AUTH_TO_QUOTE` (default on) + `AUTH_ENABLED` — so every lead signs in (one-tap Google) and is credited to the right driver before seeing a price. Open mode (`AUTH_ENABLED=false`) is unaffected; the booking flow prompts sign-in on the 401 and resumes automatically.

**"Your Driver" + sharing.** The *Your Driver* tab (`/your-driver`) now resolves to each rider's own designated driver. The public profile gets a **real scannable QR** (`qrcode.react`), save-to-contacts (vCard) and copy-link. Drivers grab their own link/QR from a new **Share your link** panel in dashboard Settings (`/me` now returns `tenant_slug`).

**Verification.** 5 new backend tests (attribution, first-touch permanence, wall 401/200) + full suite green; `ruff`, `tsc`, `next lint` + `build` clean; Playwright e2e (referral cookie capture, wall prompt, QR, share panel) with no JS errors; **security review found no exploitable issues**; code review surfaced only minor/intended notes. No DB migration (attribution rides on the existing per-tenant `Client`).

## v0.24.0 — 2026-06-12 — Team member detail drawer (per-driver usage analytics)

The super-admin can now click any driver in **Team** to open a detail drawer with everything about that driver — turning the access list into an oversight console.

**What it shows.** Access/identity (role, active, added-by, member-since, last login), subscription status (Operator plan, renewal, paid flag), business KPIs (rides by status, all-time revenue, clients, first/last ride, weekly earnings chart), 30-day **platform engagement** (sessions, visitors, pageviews, avg session, booking funnel `started→booked`, sign-ins, devices, countries), recent rides and a recent-activity timeline. Consolidated management actions live in the drawer too: activate/deactivate, change role, resend welcome email, copy invite, remove.

**Backend.** New tenant-scoped read-model `team_member_detail()` (`app/services/dashboard.py`) composed by reusing `stats()`, `analytics.summary()` and the subscription lookup — no new tables, no migration. Exposed at `GET /api/v1/team/{email}/detail` under `require_admin`. A member who's never signed in (no tenant yet) returns `provisioned=false` with empty blocks. Recent rides render read-only — a driver's ride lives in their own tenant, so the tenant-scoped `RideDetail` can't open it cross-tenant (verified in e2e). 192 backend tests pass; `ruff`, `tsc`, `next lint` + `build` clean; security review found no issues.

## v0.23.1 — 2026-06-11 — Driver subscriptions live + webhook signature header fix

Activated Phase 3 in **production** (driver.blackvoltmobility.com) and fixed a webhook bug found during go-live.

**Live activation.** Operator plan created in production Square via the Catalog API (`app/scripts/provision_square_plans.py`; monthly `PAWKFYCZAXQYDWEOWSEU25XC` $29 / annual `6MFM2EBBGE5K663ZD6N6JPWB` $290). `driver.` DNS added as a proxied CNAME to the `blackvolt` tunnel (via the Cloudflare API — the tunnel's `cert.pem` is scoped to another zone, so `cloudflared route dns` can't write the `blackvoltmobility.com` zone). Webhook subscription registered via the API (`app/scripts/provision_square_webhook.py`); `ENTITLEMENTS_ENFORCED=false` (soft launch).

**Webhook signature header fix.** Square sends the HMAC-SHA256 signature in `x-square-hmacsha256-signature`, not the bare `x-square-hmacsha256` the endpoint was reading — so the header arrived empty and **every real webhook 403'd**. Caught by replaying a live Square test event end-to-end (Square → Cloudflare → Next proxy → backend), which now returns 200 and syncs the row. Tests updated to the real header name. 182 backend tests pass; `ruff` clean.

## v0.23.0 — 2026-06-11 — Driver subscriptions: Operator plan landing + checkout

Closes the customer-facing surface of Phase 3 (Square Subscriptions). Other drivers can now subscribe to the **Operator** plan and self-serve by card; the booking/ride payment flow is untouched. Built TDD in simulated/sandbox mode — going live is a manual owner checklist (`docs/subscriptions-activation.md`), no code changes.

**Driver landing (`driver.blackvoltmobility.com`).** Faithful Next.js port of `driver-landing.html`, served via a host rewrite (`DRIVER_HOSTS`, mirroring the `app.`→`/dashboard` pattern) at `/driver` — public, no auth. Styles are scoped under `.bv-driver` (bv-prefixed classes) so nothing leaks globally. Three tiers: Free → dashboard sign-up (`NEXT_PUBLIC_APP_URL`), Operator → checkout modal, Growth → sales mailto (`NEXT_PUBLIC_SALES_EMAIL`). EN + ES (~110 `driver.*` i18n keys).

**Operator checkout (monthly/annual).** A modal reuses `GET /payments/config` + the shared `loadSquareSdk` loader (extracted to `lib/squareSdk.ts`, now shared with `SquareCard.tsx`). A monthly **$29** (`operator`) / annual **$290** (`operator_annual`) toggle switches price and `plan_key` together (the backend already mapped both). Email is validated before tokenizing; the card is tokenized client-side so **only the nonce reaches the backend — the Square secret never touches the frontend**. `lib/subscriptions.ts` posts to `POST /api/v1/subscriptions` over the same-origin `/api` proxy (so the browser never hits CORS) and maps each sanitized `public_code` to a `driver.err.*` message. If Square isn't configured the modal degrades to a "contact us" state.

**Square webhooks.** New `POST /api/v1/webhooks/square` keeps the local row in sync over the subscription lifetime. `verify_signature` reproduces Square's HMAC-SHA256 over (registered URL + raw body), base64, compared in constant time — **fail-closed**: without both the signing key and exact URL (`settings.webhooks_live`) every event is refused with a 403, and the 403 is identical whether the signature is wrong or webhooks aren't configured (no info leak). `apply_event` is idempotent (redelivery-safe), never creates rows, and no-ops on unknown ids or simulated rows. Its own `_WEBHOOK_STATUS_MAP` (ACTIVE/PENDING/PAUSED→past_due/CANCELED+DEACTIVATED→canceled) leaves any unknown status as PENDING so a surprise value can never silently entitle a tenant; `invoice.payment_made`→active, failed/cancelled invoices→past_due.

**Config/env.** `SQUARE_WEBHOOK_SIGNATURE_KEY` + `SQUARE_WEBHOOK_URL` (+ `webhooks_live` property); `https://driver.blackvoltmobility.com` added to the `CORS_ORIGINS` default and the compose passthrough (it was missing). New frontend build args `NEXT_PUBLIC_APP_URL` / `NEXT_PUBLIC_SALES_EMAIL` / `DRIVER_HOSTS` (ARG+ENV in the Dockerfile, baked at build).

182 backend tests pass (new `test_webhooks_square.py` + `test_config_webhooks.py`); `ruff` + `tsc` + `next lint` clean; no autogenerate drift. Live smoke: `/driver` host-rewrite 200, webhook 403 fail-closed, subscribe 400 on an invalid plan.

## v0.22.0 — 2026-06-10 — Team panel upgrade: roles, welcome emails, per-driver activity

Turns the admin-only Team page into a real fleet-management panel. Same multi-tenant model (each driver = their own tenant); no booking/payment paths touched.

**Role management.** `PATCH /api/v1/team/{email}` now accepts `role` (`admin`|`driver`). Promote/demote from the UI (clickable role pill, confirm on promote). Lockout guards reuse `_other_active_admins_remain`: a pinned (env) admin can't be demoted (`pinned_admin_immutable`) and the last active admin can't be demoted (`last_admin`).

**Welcome email (Resend).** New `app/services/email.py` (`send_email` + `send_team_welcome`) mirrors the Eko AI Realtors pattern: Resend over httpx with an `EMAIL_SIMULATED` short-circuit (logs instead of sending). Adding a member triggers a bilingual (ES/EN) welcome email with the dashboard sign-in link; the API returns an `email_status` (`sent`|`simulated`|`failed`) the owner sees. New `POST /api/v1/team/{email}/resend-invite` re-sends it. Config: `EMAIL_SIMULATED` (default true), `RESEND_API_KEY`, `RESEND_FROM` (Black Volt's own verified domain), `PUBLIC_DASHBOARD_URL`; startup WARNs if `APP_ENV=production` + `EMAIL_SIMULATED=true`. **Email goes live once a Resend domain + key are configured** — until then it's safely simulated.

**Per-driver activity.** New `last_login` column on `allowed_users` (migration `0012_allowed_user_last_login`), stamped on every dashboard sign-in. The Team list now shows each member's ride count, paid revenue, and last login — computed per tenant via a new `dashboard.team_stats_by_tenant` (same aggregation pattern as the client CRM).

**Frontend.** `components/bv/dash/Team.tsx` reworked (extracted `MemberRow`): role toggle, activity line, "Copy invite" (clipboard, ready-to-share bilingual message + link) and "Resend email" per row. `lib/team.ts` adds `setRole`/`resendInvite`; new `dash.team.*` i18n keys in EN + ES.

135 backend tests pass (new role/email/stats/last_login coverage in `test_team_onboarding.py`); `ruff` + `tsc` + `next lint` clean; no autogenerate drift.

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
