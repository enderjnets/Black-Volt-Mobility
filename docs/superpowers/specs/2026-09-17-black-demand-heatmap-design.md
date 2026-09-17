# Design — "Where to wait": Black/Black SUV demand planner and heatmap

Date: 2026-09-17 · Status: approved section by section with the owner on 2026-09-17 · Research: [`docs/research/2026-09-17-black-demand-heatmap.md`](../../research/2026-09-17-black-demand-heatmap.md) and its appendices A–D.

## Context

The owner drives Uber Black / Black SUV in Denver (Kia EV9). He spends hours idle downtown receiving only UberX/Comfort pings. His goal is airport (DEN) rides; second, good short rides that keep him in Black-dense areas or take him to one. His filter practice: Black + Black SUV only; when it is slow he opens Comfort to catch a ≥$35 ride toward DEN and waits there for Black.

The bar he set: **the tool must give an advantage over what the Uber driver app already shows; otherwise it has no point.** What Uber gives him: an earnings heatmap (H3 res-9, 10-minute refresh, 4-week history, internally grouped by vehicle type per Uber's engineering blog but not documented to drivers as product-specific), live surge, an in-lot wait estimate at DEN, and Reserve requests up to 7 days ahead. What Uber does not give him and this tool will: his own Black offer rate per minute waited, net of the competing Black drivers; a 7-day "best hours to work" plan; a value for the destination of a bridge ride; his own DEN queue history.

Key verified facts driving the design (sources in the research report):

- Uber officially supports receiving only Black requests.
- The driver data export (`driver_lifetime_trips`) carries product per trip, request/begin/dropoff timestamps, `is_airport_trip`, fares and surge, but no coordinates in the current format. A separate `Driver Online Offline.csv` (states `open`/`enroute`/`ontrip`/`offline` with begin/end lat/lng and timestamps) was seen in a 2021 sample and **may or may not be present** in his export. A `Driver Dispatches Offered and Accepted.csv` gives per-window offer counts without product or location.
- The Uber Driver API is limited-access and has no product field. Third-party credential linking risks the account. Neither is used.
- An installed PWA cannot log GPS in the background on Android or iOS. Logging is one-tap in the foreground.
- Google Maps' HeatmapLayer was decommissioned in May 2026. The map is MapLibre GL with OpenFreeMap tiles; Google content stays server-side and off that map.
- No public rideshare trip data exists for Denver or Colorado, and no public dataset anywhere has a product tier.

## Decisions (confirmed with the owner)

1. **Approach B, two phases.** Phase 1 "Planner + logging" (no map). Phase 2 "Live map". Approaches A (planner only) and C (scraped surge, paid schedules, native background GPS) rejected: A does not answer "where"; C violates Uber's terms and is a different product.
2. **Uber export is uploaded through the dashboard** (Phase 1 screen). The owner requests it from Uber's "Request your personal Uber data" page.
3. **Owner-only for now**, but every table and query is tenant-scoped like the rest of the app, so opening it to team drivers later needs no schema change.
4. **Android phone, Black Volt installed as a PWA**; logging screen designed for split-screen next to Uber Driver.
5. **No schedule constraints**: the planner ranks the whole week. Confirmed private Black Volt rides are overlaid so blocks don't collide with them.
6. **Bridge threshold** (Comfort fare worth taking toward a good destination) is a per-tenant setting, default $35.
7. **Free data first**: BTS flight baseline, Census ACS, NWS weather, existing Ticketmaster/SeatGeek. Live 7-day flight schedules (AeroAPI ≈ $78/mo by the research estimate, or AeroDataBox $19/mo if its horizon reaches +7 days) are an optional later toggle.
8. **Scoring target**: probability of at least one Black or Black SUV offer within 15 minutes. Comfort never enters the main score; it appears only as a "bridge" when the offer's destination scores well.
9. **Honesty rules**: every cell shows the share that comes from the owner's own data and the hours logged; cells below 20% own share render hatched; no accuracy claim before 4 weeks of logged offers can be scored against predictions.
10. **No commits without the owner asking.** Research docs and this spec are written to the repo uncommitted until he says so.

## Data model

All tables have `tenant_id` (FK `tenants.id`, indexed) and `created_at`. One Alembic migration per phase; Phase 1 is `0050_demand_phase1`.

### `uber_trips` (from export)

| column | type | note |
|---|---|---|
| `id` | int PK | |
| `tenant_id` | int FK | |
| `dedup_key` | varchar(64) unique per tenant | sha256 of `request_at|begin_at|fare_total|distance_mi` — the file has no trip UUID |
| `product` | enum `black_suv, black, comfort, x, xl, other` | normalized from `product_type_name` / `global_product_name` (map kept in code; unknown → `other` with the raw kept) |
| `product_raw` | varchar(80) | as exported |
| `request_at`, `begin_at`, `dropoff_at` | timestamptz | local timestamps converted with the export's `timezone` column |
| `city` | varchar(80) | |
| `is_airport` | bool | `is_airport_trip` |
| `is_scheduled` | bool | `is_scheduled_trip` (Reserve) |
| `status` | varchar(30) | as exported; `is_completed` derived |
| `fare_total` | numeric(10,2) nullable | `original_fare_usd` or local |
| `surge_multiplier` | numeric(5,2) nullable | |
| `distance_mi`, `duration_s` | numeric / int nullable | |
| `imported_at` | timestamptz | |

### `driver_state_segments` (from export file "Online Offline" and from live logging)

| column | type | note |
|---|---|---|
| `id`, `tenant_id` | | |
| `state` | enum `open, enroute, ontrip, offline` | `open` = online and waiting: this is the exposure |
| `begin_at`, `end_at` | timestamptz, `end_at` nullable while live | |
| `begin_lat`, `begin_lng`, `end_lat`, `end_lng` | float nullable | rounded to 5 decimals |
| `h3_r8` | varchar(16) nullable | H3 res-8 cell of `begin` |
| `source` | enum `export, live` | |
| `dedup_key` | varchar(64) unique per tenant | export rows: sha256 of `state|begin_at|end_at`; live rows: uuid |

### `offer_events` (live logging only; the export has no per-offer product)

| column | type | note |
|---|---|---|
| `id`, `tenant_id` | | |
| `at` | timestamptz | |
| `lat`, `lng` | float nullable | null when GPS denied/failed; flagged in UI |
| `h3_r8` | varchar(16) nullable | |
| `product` | enum as above | required |
| `accepted` | bool | |
| `fare` | numeric(10,2) nullable | optional tap-in |
| `dest_text` | varchar(200) nullable | optional, Phase 2 destination scoring |
| `client_event_id` | varchar(64) unique per tenant | generated by the PWA; makes a retried POST idempotent |

Live rows in `driver_state_segments` use the same `client_event_id` of the tap that opened them as their `dedup_key`.

### `dispatch_windows` (from export file "Dispatches Offered and Accepted", optional)

`tenant_id, window_start, window_end, minutes_online, minutes_active, dispatches, rejections, accepts, expireds, completed_trips, dedup_key`. No product, no location; feeds the hour-of-week offer rate only.

### `hex_priors` (static, regenerated by script)

`h3_r8 PK, affluence (float 0–1 from ACS median income and share of households ≥$200k of the containing tract), hotels (int, curated luxury hotels within 1 km), generators (int, FBOs/corporate/shopping/medical within 1.5 km), den_distance_mi (float), zone_key (nullable, from the curated zone list)`. Not tenant-scoped: it is geography.

### `den_flight_baseline` (static, monthly script)

`month (1–12), dow (0–6), hour (0–23), departures (float avg/day), arrivals (float avg/day), source_period (varchar)`. From BTS On-Time (domestic) scaled by T-100 seats; international bank added as a constant per the research caveat.

### `hex_scores` and `week_scores` (computed)

`hex_scores`: `tenant_id, computed_at, slot_start, h3_r8, mean, lo, hi, own_share, reasons (json)`. Kept 7 days for backtests.
`week_scores`: `tenant_id, computed_at, zone_key, dow, hour, mean, lo, hi, own_share, reasons (json)`. Latest run only.

### Curated lists (code constants, like `venue_profiles.py`)

`services/demand_places.py`: luxury hotels (AAA 4–5 Diamond + Forbes list from the research, with public addresses and coordinates typed from OSM, never stored from Places responses), FBOs (Signature APA-South/North, Modern Aviation, Denver jetCenter at KAPA; Signature and Sheltair at KBJC; Signature DEN), corporate/shopping/medical generators, and the DEN Commercial Hold Lot polygon center + radius (configured, confirmed by the owner on site). Zones reuse `TARGET_ZONES` from `uber_research.py` plus `den`, `downtown`, `cherry_creek`, and any zone the import reveals with ≥10 trips.

### Settings (`config.py`, declared in `docker-compose.yml`)

`DEMAND_ENABLED` (default false), `CENSUS_API_KEY`, `DEN_LOT_LAT`, `DEN_LOT_LNG`, `DEN_LOT_RADIUS_M` (default 400), `DEMAND_BRIDGE_FARE_DEFAULT` (35), `DEMAND_RECOMPUTE_MIN` (15), `NWS_USER_AGENT`. Per-tenant `RateConfig.bridge_fare` (nullable numeric, added in migration 0050) overrides the default.

## The model (`services/demand_model.py`, pure functions)

Target per cell `(h3_r8, hour_of_week)`: λ = Black+SUV offers per minute of `open` time. Shown as `P = 1 − exp(−15·λ)`.

1. **Prior** λ⁰ = `base[how]` × `m_affluence` × `m_hotels` × `m_generators` × `m_flights[how]` × `m_events[slot]`. `base[how]` is a 168-value profile: from `dispatch_windows` if imported, else a fixed default derived from the owner's `uber_trips` request-time histogram, else flat. Multipliers are bounded (0.5–3) and their values live in one constants block with a comment per source so they can be tuned.
2. **Own data**: for the cell and its k-ring-1 neighbours (weight ½) and adjacent hours (±1, circular over 168, weight ½), sum `y` = Black+SUV offers and `E` = `open` minutes.
3. **Posterior mean** = `(α + y) / (β + E)` with prior mean `α/β = λ⁰` and `β` = pseudo-exposure minutes (constant, initial 600; re-fit by marginal likelihood once ≥ 2,000 open minutes exist). `lo/hi` = Gamma 10/90 percentiles. `own_share = E / (E + β)`.
4. **Zone aggregation** (planner): same estimator over all cells of a zone, per hour-of-week, in `America/Denver` local time (DST days have 23 and 25 hours; the grid is built from local timestamps, never by adding 24 slots).
5. **Top blocks**: contiguous runs ≥ 2 h where `mean` ≥ the tenant's threshold (default: top quartile of the week), ranked by expected offers = Σ mean × 60. Each block carries `reasons`: the covariates that lifted it (flight bank counts, events with name and time, holiday flag).
6. **Phase 2 ranking from current position**: score − travel penalty, penalty = `grid_distance × 531 m / 25 mph` converted to the fraction of the 15-minute window lost; never a Directions call.
7. **Bridge**: a Comfort offer is "worth it" when `fare ≥ bridge_fare` and the destination cell's mean exceeds the current cell's by ≥ 1.5×.
8. **Later** (not in either phase): Poisson GLM with Fourier hour-of-week terms, `holidays` package, ski-season flag, DEN counts as covariate; then gradient boosting after thousands of exposure hours.

## Backend

### `services/uber_import.py`

- Accepts a ZIP ≤ 50 MB, processed in memory, only `.csv` members read (any other member type is ignored and listed; nothing is executed or written to disk).
- Detects format per file by header: 2021 style (`; `delimiter, `Driver Lifetime Trips*.csv`, `*Driver Online Offline.csv`, `*Dispatches Offered and Accepted.csv`) and 2025 style (`,` delimiter, `driver_lifetime_trips-0.csv`, `driver_payments-0.csv`); tolerant of either delimiter and of the 2022 `Trip details (Driver).csv` (which has `begintrip_latitude/longitude` and `fare_profile`).
- Upserts by `dedup_key`; second import of the same ZIP changes nothing.
- Returns `ImportSummary {files_found: [...], files_missing: [{name, consequence}], trips: {inserted, skipped, date_min, date_max, by_product}, segments: {...}, dispatch_windows: {...}}`. Every run is stored in `demand_imports` (`id, tenant_id, at, summary json`); `/demand/import/status` returns the latest row.

### `services/shift_log.py`

- `log_event(tenant_id, kind, product?, accepted?, lat?, lng?, fare?)`, kinds `online, here, offer, offline, ping`.
- `online`/`here`/`ping` close the previous open segment (`end_at = now`, `end_*` = event position) and open a new `open` segment; `offer` writes an `offer_events` row and, if accepted, closes the `open` segment and opens an `enroute` one; `offline` closes everything.
- A `here` inside the DEN lot polygon tags the segment `zone_key = den_lot`; DEN wait = duration of `open` segments tagged `den_lot`.
- Idempotent per `(tenant_id, client_event_id)` so a retried POST from a flaky connection does not double-log.

### `services/demand_prior.py`

- `load_census(state=08, counties=[001,005,013,014,031,035,059])` via the Census API with `B19013_001E, B19001_001E, B19001_017E` at tract level; joins tract polygons (`cb_2025_08_tract_500k`, converted once to GeoJSON and stored under `backend/data/`); fills `hex_priors` for every res-8 cell in the metro bbox (39.50,-105.35)–(40.10,-104.60).
- `load_places()` from `demand_places.py` increments hotel/generator counts and DEN distance.
- Run: `python -m app.scripts.build_demand_priors`. Idempotent (truncate + rebuild).

### `services/flights_baseline.py`

- Downloads the BTS On-Time monthly zip for the last 13 months, filters `Origin == DEN` / `Dest == DEN`, bins `CRSDepTime`/`CRSArrTime` by month × dow × hour, scales by T-100 seats, writes `den_flight_baseline`. Run monthly: `python -m app.scripts.build_flight_baseline`. Fails soft: if BTS is unreachable the previous table stays.

### `services/demand.py`

- `recompute_hex(tenant_id, now)`: builds the next 12 slots of 15 min for every cell with a prior, writes `hex_scores`, caches `demand:heat:{tenant}:{slot}` in Redis (gzipped compact JSON, TTL 30 min) using the same best-effort Redis pattern as `coach.py`.
- `recompute_week(tenant_id, now)`: zone × hour-of-week grid + top blocks, writes `week_scores`, caches `demand:week:{tenant}` (TTL 2 h). Reads the next 7 days of events (`event_suggestions`/`events` via `events_scan.py` data), the flight baseline, NWS hourly forecast (`api.weather.gov` gridpoint for Denver, cached 1 h), and US/CO holidays.
- Both run in the existing in-process `AsyncIOScheduler` (`services/scheduler.py`) as `_demand_hex_job` every `DEMAND_RECOMPUTE_MIN` and `_demand_week_job` hourly, for tenants with `DEMAND_ENABLED` and any imported or logged data. Own DB session, errors swallowed and logged, like the other jobs. The repo assumes a single backend instance; that caveat is already documented there.

### API — `api/v1/demand.py` (staff session, tenant-scoped)

| method | path | body / query | returns |
|---|---|---|---|
| POST | `/demand/import` | multipart `file` (zip) | `ImportSummary` (201) · 400 on bad zip · 413 over 50 MB |
| GET | `/demand/import/status` | | last `ImportSummary` + `at`, or `{never: true}` |
| POST | `/demand/log` | `{client_event_id, kind, product?, accepted?, lat?, lng?, fare?, at?}` | the stored event (201) · 409 duplicate `client_event_id` returns the existing one |
| GET | `/demand/log/today` | | events since local midnight + current state + open-since |
| GET | `/demand/week` | `zone` (default the tenant's best zone) | `{zone, computed_at, grid: [7][24]{mean,lo,hi,own_share}, top_blocks: [...], zones: [...], private_rides: [...]}` |
| GET | `/demand/heat` | `at` (ISO, default now), `res` (8 or 7) | `{slot, res, computed_at, cells: [[h3, mean, lo, hi, own_share], ...]}` — Phase 2 |
| GET | `/demand/heat/top` | `lat, lng, minutes=15` | top 5 cells with `eta_min`, `p`, `reasons` — Phase 2 |

Responses carry `ETag` = hash of `computed_at`; `Cache-Control: private, max-age=300, stale-while-revalidate=900`. Unknown zone → 404. Nothing under `/demand` is reachable from the client portal.

## Frontend

Route `/dashboard/demand`, nav item "Where to wait" / "Dónde esperar" (icon from the fixed registry in `Icon.tsx`, e.g. `map-pin` added if missing) in `DriverTabBar` and the sidebar, shown only when `DEMAND_ENABLED` is reported by `/me` (add `features.demand` to the `Me` payload). Components under `components/bv/dash/demand/`, API client `lib/demand.ts` (reusing `jsend`, `ApiError`, `fmtApiDetail`), strings under `dash.demand.*` in `lib/i18n.tsx` (EN + ES).

### Tab "Log" (default while driving)

- Four large buttons filling the upper half: Online, Here, Offer, Offline. Offer expands a chip row (Black SUV, Black, Comfort, X, XL) plus an "Accepted" toggle and an optional fare field; tapping a chip sends immediately.
- Every tap: `getCurrentPosition` (timeout 8 s, high accuracy) → POST with a client-generated `client_event_id`; on GPS failure the event is sent without position and the row shows a "no position" badge with a retry.
- While the tab is visible and state is online: a `ping` every 60 s with a Screen Wake Lock request (best effort). Leaving the tab stops pinging; the segment stays open until the next tap.
- Below: today's list (time, kind, product, zone name from `h3_r8` → nearest curated zone, or lat/lng), the current state and "open since".
- Layout: no header, no scroll, thumb-reachable at 390 px and in Android split-screen (~390×400).

### Tab "Week"

- Zone selector (chips), 7×24 grid with cells coloured by `mean` (dataviz skill palette, sequential), hatched when `own_share < 0.2`; tapping a cell shows mean, interval, own share, hours logged, reasons.
- Top blocks list above the grid: day, hours, expected offers, reasons.
- Confirmed private rides (from `/rides`, status confirmed/upcoming within 7 days) overlaid as outlined cells.
- Empty state before any compute: "Import your Uber data or log your first shift".

### Tab "Import"

- Drop zone / file picker for the ZIP, upload progress, then the summary: files found, rows per table, date range, products found, and **files missing in red with their consequence** ("Driver Online Offline.csv not present: waiting locations will come only from your logs and the 30-day GPS file; request a new export monthly").
- Last import status on load.

### Tab "Map" (Phase 2)

- MapLibre GL JS (`maplibre-gl` dependency) with OpenFreeMap style URL, fallback style pointing to a self-hosted PMTiles extract of Colorado on the VPS (served by nginx as static). Attribution shown.
- Hex polygons built client-side from the compact list with `h3-js` (`cellToBoundary`), fill colour by `mean`, hatch pattern when `own_share < 0.2`; res-7 parents when zoomed out.
- Own position marker, slot selector (now / +1 h / +2 h), and a card list of the top-5 cells with ETA and `p`.
- Tap a hex: sheet with `p`, interval, own share, hours logged, reasons.
- No Google key in the browser. Directions/Places remain server-side and are never drawn on this map.

Dependencies added: Phase 1 `h3-js` (for the cell id at log time); Phase 2 `maplibre-gl`. `package-lock.json` is gitignored in this repo (Dockerfile runs `npm install`).

## Error handling summary

| where | failure | behaviour |
|---|---|---|
| import | not a zip / >50 MB / no CSV inside | 400/413 with a plain reason; nothing written |
| import | a known file missing | import proceeds; missing file listed with consequence |
| import | unparseable row | skipped and counted in `skipped_rows`; import continues |
| log | GPS denied/failed | event stored without position; UI badge + retry |
| log | duplicate `client_event_id` | 409 returning the stored event; UI treats as success |
| compute | Redis down | scores served from Postgres; log warning |
| compute | NWS/BTS/events unreachable | multipliers fall back to 1.0 for that layer; `reasons` says "weather unavailable" |
| compute | no priors built | job logs once and skips; UI empty state |
| map | tile server down | fallback style; if both fail, a plain list of top cells is still shown |

## Testing

Backend (`pytest`, ruff, `alembic upgrade head` with no autogenerate drift), ephemeral local docker stack:

- `test_demand_model.py`: prior only → output equals prior; heavy own data → converges to observed rate; 10 logged minutes → stays within 5% of prior; top blocks respect threshold and ≥2 h; DST spring/fall days yield 23 and 25 local hours; bridge rule; travel penalty ranking.
- `test_uber_import.py`: synthetic fixtures with the **real headers** copied from the 2021 Paris (`;`), 2022 US (`,`, with coordinates) and 2025 US (73 columns, no coordinates) samples, 5–10 rows each; double import inserts 0 the second time; missing "Online Offline" reported with consequence; non-CSV member ignored and listed; oversize rejected; summary counts match rows.
- `test_shift_log.py`: sequence online → here → offer(black, accepted) → offline closes segments with correct durations and states; offer without position stored and flagged; duplicate `client_event_id` → 409 with same row; DEN lot tagging; tenant isolation (A cannot read B).
- `test_demand_api.py`: 401 without session; driver sees only own tenant; `week`/`heat` shapes; `ETag` changes after recompute; unknown zone 404.
- `test_demand_jobs.py`: one tick writes `week_scores` (Phase 1) and `hex_scores` (Phase 2) plus their Redis keys; a raising compute does not stop the scheduler.

Frontend: `tsc`, `next lint`, `next build`; Playwright at 390 px with owner login: four buttons visible and responsive (mock geolocation), Week renders seeded grid and blocks, Import shows a summary from a fixture ZIP, no horizontal scroll, zero console errors. Phase 2: map loads with no Google request in the network log and renders seeded hexes.

## Phases

**Phase 1 — Planner + logging (v0.93.0)**: migration 0050, `uber_trips`/`driver_state_segments`/`offer_events`/`dispatch_windows`/`demand_imports`/`hex_priors`/`den_flight_baseline`/`week_scores`/`hex_scores`, `uber_import`, `shift_log`, `demand_prior` + script, `flights_baseline` + script, `demand_model`, `demand.recompute_week` + scheduler job, API (import, log, week), tabs Log/Week/Import, tests, deploy to VPS with migration and both scripts run once.

**Phase 2 — Live map (v0.94.0)**: `demand.recompute_hex` + job, API (heat, heat/top), Map tab with MapLibre + h3-js, bridge destination scoring on the Offer chip (optional `dest_text`), optional push "zone X rises in 40 min" via the existing `push.notify_staff`. Starts only after 4 weeks of Phase 1 logging have been scored against predictions and the result reported to the owner as-is.

Deferred, not planned: paid live flight schedules toggle; Poisson GLM / gradient boosting; team-wide rollout; native wrapper with background GPS.

## Owner TODOs

1. Request the Uber data export ("Request your personal Uber data" in Uber help) and upload the ZIP in the Import tab when Phase 1 is deployed; tell us whether a file with `earner_state` and `begin_lat` was inside.
2. Get a free Census API key (api.census.gov/data/key_signup.html) → `CENSUS_API_KEY` in the VPS `.env`.
3. ✅ 2026-09-17 — DEN Commercial Holding Lot (8500 Peña Blvd, Denver, CO 80249) confirmed by the owner via its Google Maps pin: `DEN_LOT_LAT=39.8399691`, `DEN_LOT_LNG=-104.6698651` (in the local root `.env`; Task 14 copies both to the VPS `.env`, values in the plan's Task 14 env table). The app shows the configured 400 m circle on the Week/Map views.
4. Review the curated hotel/FBO/generator list in `demand_places.py` before the priors are built.
5. Log every shift for 4 weeks: Online, Here on each move, Offer with product on every ping, Offline.
