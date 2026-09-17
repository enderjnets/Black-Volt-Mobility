# Rideshare driver positioning tools — benchmark (checked 2026-09-17)

All URLs checked 2026-09-17. Relative App Store dates ("6 days ago") converted against that date.

## 1. Which tools are alive (Sept 2026)

- Gridwise — ALIVE. iOS v3.81.1, updated ≈Sept 11 2026, 28k ratings. "Where to Drive" (neighborhood earnings, 4-week historical), "When to Drive", Airports (arrivals/departures, plane seat capacity, delay alerts), Events (7 days, 25-mi radius). Plus $14.99/mo or $107.99/yr (help center; /plus page shows "$9/mo" billed annually). Where to Drive is "only available in select major cities"; Denver coverage UNVERIFIED.
- Solo — ALIVE. v6.0.7, ≈Sept 15 2026, 13k ratings. "pay predictions by hour and by job", Smart Schedule; no map; airport = flight arrivals only. $10–20/mo, Pro annual $119.99. Argyle account linking.
- Mystro — ALIVE. v2026.9.2, Sept 8 2026, 10k ratings. Multi-app auto-accept; only a free DoorDash restaurant-density heatmap. $18.99/mo, $139.99/yr. Lyft blocked it in 2019 (Fast Company).
- Maxymo — ALIVE, degraded. v2026.09.15, ≈Sept 16 2026, 10 iOS ratings. New "Events section". Own support page (updated Apr 1 2025): "your auto functions are being blocked by Uber for your market. This is outside of our control." $4.99.
- Para — ZOMBIE. iOS last update May 9 2024; Business Insider (Jul 17 2025): "Para, which shut down last year" (per Reddit users); website still markets it. Never had heatmap/airport.
- SherpaShare — DEAD. iOS last update Aug 15 2019; removed from Google Play Aug 27 2024 (MileageWise).
- Stride — ALIVE, mileage/tax only. v26.9.2, ≈Sept 15 2026, 97k ratings. No demand features.
- Driver's Seat Cooperative — became Princeton's Workers' Algorithm Observatory; "WAO Driver's Seat" iOS v1.0.4, last updated Apr 3 2024; research tool, "best times to work", no heatmap.
- Newer: Radar: Rideshare Hotspots (OCUTECH; event-driven hotspot signal; SF/LA/NY; $6.99/wk, $19.99/mo; update "June 22", year not shown; too few ratings to display). GigU (Brazil; US launch May 2025; offer scoring, no heatmap).
- Uber's own driver app: Earnings Heatmap (Oct 2022) "combines data from the previous 4 weeks with current conditions"; Nov 18 2025 engineering post: predicts earnings-per-hour at H3 hex-9, "updates every 10 minutes". Offline heatmap pilot (Jun 10 2026) is delivery-only.

What this means: no third party has a live per-product demand map. The two survivors with positioning features (Gridwise, Solo) are backward-looking crowdsourced medians plus flight schedules and event calendars, and the category is shrinking under platform hostility. A single-driver personal tool avoids that fight.

## 2. Gridwise mechanics

- Source: "The data you see in Insights is crowdsourced from Gridwise users who track their mileage, time and earnings in the app." Medians, not averages; "Each stat in Insights is based on data from the past four weeks." Where to Drive is historical, neighborhood-level; filters "rideshare, food delivery, or grocery/package delivery" — service type, not product tier. Thin markets fall back to "Nationwide view".
- Airport: "Arrivals and departures data show upcoming passenger activity"; Plus adds "seat capacity, origin, and status"; free users "view the next 4 hours with updates every 24 hours", Plus "24-hour data with frequent updates". Flight-data vendor not named.
- Queue lengths: launched Sept 29 2017 as manual crowdsourcing — "Drivers have the ability to enter their position in the queue using the 'Queue Lengths' tab" — per platform ("31–40 Uber drivers and 21–30 Lyft drivers"), not per product. Still described in a Jul 2022 RideshareGuy review; absent from the current help article and /plus page → 2026 status unconfirmed.
- Events: events within 25 miles, next 7 days, sortable by size; source undisclosed.
- Per-product: NO. Gridwise's Apr 1 2026 Uber Black post uses "real earnings data from 66,952 Uber drivers tracked through Gridwise as a baseline, then explain how Uber Black pay differs from the aggregate" — it cannot isolate Black trips.
- API/export: no public API. Gridwise Analytics sells B2B "record level data"; ToS (Jun 3 2022): linked data used for "anonymization, analysis, and aggregation of such data for ultimate sale to third-parties."

What this means: Gridwise's edge is crowd scale plus a flight feed, not modeling. For one Black driver in Denver the crowd is the wrong product; the two inputs it does use (flight arrivals by time bucket, an events calendar) are cheap to replicate.

## 3. How apps get trip data

- Gridwise, Solo: Argyle credential-based linking. Gridwise ToS: "you are electronically retrieving, through Gridwise and our third-party service providers (including Argyle), your account information". Gridwise help: "Enter your login information", "Enter your verification code (if required)"; "Linking accounts syncs earnings only". Argyle docs list platform-side failure modes ("Some platforms impose limits on the number of active sessions").
- Mystro, Maxymo, GigU, Para: Android accessibility services — "Use phones' accessibility features to read drivers' screens" (The Hustle, Jul 28 2025).
- Official Uber Driver API: /partners/me, /partners/payments, /partners/trips exist, but "Access to the Driver API is currently limited." Trips schema: trip_id, vehicle_id, fare, surge_multiplier, distance, duration, start_city, status — no product/vehicle-class field.
- Blocking 2024–26: Lyft threatened deactivation for users of Maxymo, Mystro, GigU, Solo, Gridwise citing "unauthorized credential sharing" (RideshareGuy, Jun 20 2025). Uber: "Using automation tools, apps, or bots to manipulate the Uber app or access Uber data in any way isn't allowed" (BI, Jul 17 2025). Uber blocks Maxymo automation (Maxymo support, Apr 2025). No fetched source shows Uber blocking Argyle-style earnings syncing specifically.
- Colorado SB24-075 (effective Feb 1 2025) requires TNCs to disclose per-trip pay/fare to drivers (CITP).

What this means: ingest his own data — Uber driver-side trip history / weekly statements (CSV export or screenshot/paste importer), which carry product name that no API exposes. Avoid credential-sharing integrations and anything that automates the Uber app.

## 4. Demand by product tier — what exists

- Chicago TNP Trips (2025–): 24 columns, rows updated Aug 31 2026; "Shared Trip Authorized", "Shared Trip Match", "Trips Pooled" — no tier, no company; fare rounded to $2.50, times to 15 min.
- NYC TLC HVFHV (dictionary Mar 18 2025): hvfhs_license_num (HV0003 Uber, HV0005 Lyft), shared_request_flag, shared_match_flag, access_a_ride_flag, wav_request_flag, wav_match_flag — no tier.
- Uber Movement: discontinued (QGIS tutorial; Uber's decommissioning page now 404); it only ever published "average travel times, speeds" — never demand or product data. Shutdown date UNVERIFIED.
- RideAustin 2016–17: Kaggle shows "29 columns"; data.world retired Jul 13 2026; a requested-car-category column (Regular/SUV/Premium/Luxury) is recollection only — UNVERIFIED.
- Uber internal: guidance heatmap uses "our own categorization based on dispatchability information that could encompass and differentiate between lines of business and vehicle types" — exists internally, not exposed.
- Academic (DOIs via Crossref, abstracts not read): "Upgrading in ride-sourcing markets with multi-class services" (Travel Behaviour and Society 2024, 10.1016/j.tbs.2024.100845); "Identifying the factors influencing the choice of different ride-hailing services in Shenzhen, China" (TBS 2022, 10.1016/j.tbs.2022.05.006); "The dynamic ride-hailing sharing problem with multiple vehicle types and user classes" (TR-E 2022, 10.1016/j.tre.2022.102891). None found using US Uber Black trip records.

What this means: no public or commercial per-tier demand dataset for Denver exists. The only Black/SUV-specific signal reachable is his own trip history, plus proxies (premium-heavy flight arrivals, hotel/convention/corporate events, aggregate TNC patterns as a base layer).

## 5. Airport queue at DEN

- Uber app: DEN driver page — FIFO in the Commercial Hold Lot; "Proximity to the terminal within the FIFO area does not create an advantage"; Rematch and ExpressMatch. Help: "Once you join the airport queue, you will be shown a dynamic estimated wait time until your next offer", updated by riders requesting, drivers ahead, "Recent flight arrivals and cancellations". Pre-entry visibility: Uber's Hong Kong blog says tap the plane icon to see drivers waiting; Ridester (Feb 2024) says US drivers "can't view the airport queue or estimate your waiting time" before entering — CONFLICTING, US UNVERIFIED.
- Lyft app: "you'll see how many drivers are ahead of you towards the top of the app"; color-coded wait; checkable via the map bubble before entering.
- Gridwise: flights/passenger waves, seat capacity; queue lengths were manual per-platform reports (2017), 2026 status unconfirmed; nothing per product. Solo: flight arrivals only.
- No DEN-specific third-party queue tool found; no product-tier (Black/SUV) queue data anywhere.

What this means: live queue depth exists only inside the Uber app once in the lot. Build (a) one-tap logging of his own Black/SUV queue position, wait and timestamp at DEN, (b) flight arrivals by 30-min bucket, (c) his own wait-vs-arrivals history as the predictor — Gridwise's 2017 trick, scoped to one product.

## Comparison table

| Tool | Alive? | Heatmap / where-to-go | Airport queue | Events | Per-product demand | Data source | Price |
|---|---|---|---|---|---|---|---|
| Gridwise | Yes (≈Sept 11 2026) | Where to Drive: neighborhood medians, 4-wk historical | Flights + seat capacity; manual queue reports (2017, status unconfirmed) | Yes, 7-day, 25 mi | No | Crowdsourced via Argyle linking | Free / $14.99 mo / $107.99 yr |
| Solo | Yes (≈Sept 15 2026) | No map; pay predictions by hour | Flight arrivals only | No | No | Argyle linking | $10–20 mo; $119.99 yr |
| Mystro | Yes (Sept 8 2026) | DoorDash-only heatmap | No | No | No | Accessibility/screen reading | $18.99 mo / $139.99 yr |
| Maxymo | Yes; automation blocked by Uber | No | No | Events list | No | Accessibility | $4.99 |
| Para | Zombie (last update May 2024; reported shut down) | No | No | No | No | Accessibility | Free |
| SherpaShare | Dead (iOS 2019; Play removed 2024) | Legacy heatmap | No | No | No | GPS | — |
| Stride | Yes (≈Sept 15 2026) | No | No | No | No | GPS | Free |
| WAO Driver's Seat | Research; last update Apr 2024 | "best times to work" | No | No | No | GPS + linking | Free |
| Radar | Yes; update "June 22" (year unshown) | Event-driven hotspot signal | No | Yes | No | Event feeds (unspecified) | $6.99 wk / $19.99 mo |
| GigU | Yes (US May 2025) | No | No | No | No | Accessibility | n/a |
| Uber Driver app | — | Earnings heatmap, 4 wk + live, 10-min refresh | In-queue wait estimate | No | Internal vehicle-type categorization, not exposed | Uber | — |
| Lyft Driver app | — | Prime Time zones | Drivers ahead + color wait, pre-entry | No | No | Lyft | — |

Footnote: Gridwise Analytics sells B2B "record level data"; no public API; no evidence it carries tier.
