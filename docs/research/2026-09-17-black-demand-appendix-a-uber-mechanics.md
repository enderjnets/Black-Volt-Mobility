# Uber Black / Black SUV demand-prediction tool (Denver) — research report


## 1. Driver data export (privacy portal) — what is actually in it

**Official description (thin).** Uber's driver help page says the download contains "Details on each trip, including start and end times, distance traveled and fare information", app analytics "from the last 30 days", and excludes weekly pay statements. The rider/driver data dictionary lists for drivers "Times at which each trip started and ended, as well as distance traveled and fare information" — note that the *rider* entry says "Times and locations", the driver entry does not say locations.

**Actual files and headers (confirmed from two independent real exports on GitHub).**

- `driver_lifetime_trips-0.csv` (US naming; EU naming "02 - Driver Lifetime Trips.csv"). French export header (65 cols, semicolon-separated): `city_id; currency_code; timezone; flow; source_tag; product_type_name; global_product_name; request_timestamp_local; request_timestamp_utc; begintrip_timestamp_local; begintrip_timestamp_utc; dropoff_timestamp_local; dropoff_timestamp_utc; eta; surge_multiplier; is_surged; has_destination; ... request_to_begin_distance_miles; request_to_begin_duration_seconds; trip_distance_miles; trip_duration_seconds; status; is_completed; ... original_fare_local/usd; base_fare; surge_fare; per_mile_fare; per_minute_fare; cancellation_fee; service_fee; toll_amount; booking_fee; earnings_boost; fare_distance_miles; fare_duration_minutes; request_date`.
- A Los Angeles driver's export (trips May 2022–May 2025, repo created May 2026) documents the same file as "3,745 rows, 73 columns" and adds `city_name, license_plate, driver_trip_number, vehicle_trip_number, is_airport_trip, is_scheduled_trip, is_directed_dispatch_trip, is_multidestination, wait_duration_minutes, driver_surge_multiplier, ufp_type, concierge_source_type`. His schema notes "Uber export has no UUID in this file" (payments link via a `Trip UUID` that is only in `driver_payments-0.csv`). I saw 53 of the 73 columns named in his code; the remaining ~20 are unverified but the FR header suggests `_local` currency duplicates and flags.
- **No pickup latitude/longitude and no address column in either header.** Product type IS present (`product_type_name`, `global_product_name`), as are request/begin/dropoff timestamps and fares.
- Other files in the export (FR sample; US naming inferred): `Driver Online Offline.csv` = `earner_state; city_id; begin_lat; begin_lng; end_lat; end_lng; begin_timestamp_utc; end_timestamp_utc; duration_ms` — status segments P1/P2/P3 with coordinates, i.e. the start of each "on trip" segment is the pickup point. **Seen only in the FR sample; no US-named equivalent surfaced in GitHub code search — verify in his own ZIP by looking for a header containing `earner_state` and `begin_lat`.** `Driver Dispatches Offered and Accepted.csv` = per-window `dispatches; rejections; accepts; expireds; ... completed_trips; flow_type` — aggregated, **no product, no location**. `driver_app_analytics-0.csv` = GPS breadcrumbs (`lat, lng, gps_time_ms, speed, driver_status ...`), officially limited to the last 30 days. Also `driver_payments-0.csv`, `driver_lifetime_ratings_received-0.csv`, `Driver App Restrictions.csv`, `Driver Performance Badges.csv`. An older-format sample ("Trip details (Driver).csv") did carry `begintrip_latitude/longitude` and `fare_profile`, so coordinates were removed from the trips file at some point.
- Request path: myprivacy.uber.com/exploreyourdata/download, 24–72 h turnaround — UNVERIFIED (search-index snippet; the Princeton guide PDF now 404s).

**Driver app / portal.** Help says statements show a "List of trips with amounts. Tap on the Trip ID to see more about a trip" and offer "Download CSV" (one period at a time). A 2019 forum post listing the weekly CSV columns (Driver Name, Date/Time, Trip ID, Type, Fare ...) says "I don't think the CSV file shows time, 'area', or location data" (Hugh G, uberpeople, 2019-06-06). No evidence the in-app trip list can be bulk-exported.

**Driver API (2026).** Docs state "Access to the Driver API is currently limited access"; `GET /v1/partners/trips` returns `trip_id, vehicle_id, pickup.timestamp, dropoff.timestamp, fare, distance, duration, start_city{latitude, longitude, display_name}, status_changes` — city-level coordinates only, no product field. No deprecation notice found.

**What this means for the tool:** The export gives per-trip product type + timestamps + fares (enough to time-profile his Black trips) but no pickup coordinates in the trips file; location must come from `Driver Online Offline` (if present in his ZIP) or the 30-day GPS file, so request exports on a schedule. Crucially it only contains trips he took — declined/unseen Black requests are not recoverable, so request-side data must be captured live.

## 2. How Uber dispatches Black

- Black-only is official: "When you're online, you can choose to receive only Uber Black trip requests. Or you can also accept UberX and/or UberXL trips" (uber.com Black page). Requirements pages disagree on rating: product page and Business Black say 4.85; the help requirements page says "a rating of 4.9 or higher" over "the driver's most recent 500 rated trips", US model year 2020+, black exterior, commercial insurance, city livery permits. Trip-type preferences caveat: "some preferences can't be toggled. For example, Comfort and Premier may be included in UberX preferences"; "It is not possible to opt in or out of receiving requests from specific locations or businesses." No evidence found of an Uber Pro tier gating the Black filter.
- Matching: Uber says "Closest doesn't always mean quickest" and batches requests for a few seconds to optimize ETAs; no product-specific logic is published. No official statement that unfilled Black requests are widened to farther drivers; the two documented widening mechanisms are Trip Radar (declined trips relisted to nearby drivers, "up to five trips", first to tap; Rideshare Guy saw offers "12-15 miles away", 2023) and Reserve (drivers "can see Reserve trip requests up to a week ahead"; premium drivers must be online 45 min before pickup; matching respects trip-type filters). Business Black's "$120 ... if no driver is matched within 8 minutes" applies to reserved trips in NYC/LA/SF/Chicago/DC only.
- Demand character: Gridwise (2026-04-01): "Weekday mornings (6am-9am): Business travelers heading to meetings and airports", demand "near airports, convention centers, and high-end hotels", 0.8–1.2 Black trips/hr vs 1.7 overall. Boston Black driver (CaptainToo, uberpeople, 2024-05-03): "60 UberX requests, 30 Comfort, 9 XLs before I get one Black"; Black requests "mostly limited to the busy times, 4PM to 11PM"; "I have never received a Black request waiting at Logan airport". Thread 501684 (snippet only): matching is proximity-based, position near sources such as executive airports.

**What this means for the tool:** Model Black as a sparse, ETA-matched, hotel/airport/corporate-hours signal; the driver should run Black-only during modeled windows and rely on Reserve visibility (7 days) as a scheduled-demand feed rather than expecting distant on-demand pings.

## 3. DEN rules and queue

- Uber's DEN driver page: pickups on "Level 5, Island 5", FIFO queue in the commercial holding lot, "Rematch means you can drop off at the airport, and pick up without having to return to the Airport staging lot", plus ExpressMatch prompts toward the terminal. Lyft's Colorado page (same lot): "The queue is first in-first out", rematch "up to 2 minutes after dropping off", three missed requests send you to the back, and a "short ride bump" SMS offers a preferred spot.
- Black-specific: no separate Black queue is documented by Uber. Third parties: Gridwise (page now 404; search index) said UberBLACK stages at the south end of the Commercial Holding Lot, 7800 Shady Grove Drive; visitdenver's rule text: "Limos and sedans pick up and drop off at Level 5, Island 2, outside Door 511 (east side) and Door 506 (west side)"; carserviceofdenver (2026-07-21) says Uber Black riders meet at "Level 5, Island 2". Part 100 (Feb 2026 PDF, 403 today; snippet): TNC vehicles use the fifth level; commercial operators may not sit in the cell-phone lot more than 15 minutes. Per-trip TNC fee: $3.00 since Jan 2022 with a $4.00 draft — current adopted figure UNVERIFIED.
- Is it worth it: Denver driver Frontier Guy (uberpeople, 2024-01-20) on Black at DIA: "at least 50 or 60 at any time, if they are lucky they get one or two rides per day". The app's DEN queue screen is shown per tier: "comfort cars, we have 170 cars waiting ... shared vehicles ... 281 to 285" (Rideshare Professor transcript, 2025-06-05; Black tier not mentioned). Airport timing (UberX-oriented): "Early morning flights 4:30-8 AM" on Fridays (Rideshare Guy Denver guide, 2024-09-06).

**What this means for the tool:** Treat DEN as a long FIFO with dozens of Black cars and no documented Black-only lane; the tool should favor *drop-off-then-rematch* windows and Reserve airport pickups over sitting in the lot, and read the live per-tier queue count from the app as an input.

## 4. Denver community wisdom

- Supply side (strongest evidence): "Denver is saturated with Uber black, at any given time there's at least 75 online" (Frontier Guy, 2024-01-20); livery friends "sometimes struggle to compete with the ultra cheap fares"; "the Denver market is totally saturated ... You can make decent money in Vail or Aspen during ski season" (Stanley B, same thread).
- Location/time wisdom found is UberX-oriented: Rideshare Guy Denver guide (2024-09-06) — western suburbs busier, "pick up a ride from one of the malls or larger hotels" to return, Boulder = short trips/high tips but fills with drivers, downtown only late-night, Friday early flights 4:30–8 AM, best Fri 9 PM–2 AM. Uber's own Denver Black page names airport transfers, hotel transfers, business travel, Coors Field/Ball Arena. gigglefinance (2025-12-01, weak SEO source): DTC "during business hours for corporate travelers", Cherry Creek, Union Station, ski season Dec–Mar. **No dated Denver quote naming Cherry Creek/DTC/hotels specifically as Black sources was found.**

**What this means for the tool:** Prior weights should come from the driver's own export plus Uber's hotel/airport/business framing, not from forum lore; the community signal that is solid is saturation (75+ Black online, 50–60 at DIA in 2024).

## 5. Uber's own tools

- Rides Heatmap (nationwide from 2025-10-17): red = shortest waits, then orange/yellow, purple = surge, showing "how long drivers waited on average for a trip based on recent data"; estimates use the past 30 minutes, refresh every 10 minutes, earnings shading uses 28 days. **No product/tier differentiation is documented anywhere.** Drivers' reaction: "Now that everything is purple how tf do we know where the biggest surge starts ??" (piunikaweb, 2025-10-13). Surge pools can differ by tier (Gridwise: Comfort surge "may not always coincide" with X; a 2014 forum report of a Black-only surge block).
- Also: Hourly Trends by city in the app; Destination Mode now "flexible route ... or the fastest route"; longer offer window with upfront details; new Uber Pro from March 2026; Trip Radar; per-tier airport queue counts. The offline delivery-zone heatmap (June 2026) is delivery-only. The "orange to dark red" surge page predates October 2025 and may be stale.

**What this means for the tool:** Nothing in the app predicts Black demand specifically; the tool's edge is a product-filtered model, and the heatmap should be consumed only as a generic demand/surge covariate.

## URLs consulted (all checked 2026-09-17)
- https://help.uber.com/driving-and-delivering/article/request-your-personal-uber-data?nodeId=fbf08e68-65ba-456b-9bc6-1369eb9d2c44
- https://help.uber.com/riders/article/whats-in-your-data-download?nodeId=3d476006-87a4-4404-ac1e-216825414e05
- https://github.com/digipower-academy/hestialabs-experiences (packages/packages/experiences/uber-driver/src/index.ts; packages/lib/data-samples/uber-driver-fr-paris.zip and uber-driver.zip)
- https://github.com/evgeniimatveev/uber-driver-analytics (sql/schema.sql; ingestion/load_data.py; README.md)
- https://github.com/UT-HAI/giginsights ; https://github.com/ste-hue/uberdriver_dashboard (US file names)
- https://www.uberpeople.net/threads/export-earnings-and-trip-data-from-the-uber-driver-app.332644/
- https://help.uber.com/en/driving-and-delivering/article/uber-driver-account-information?nodeId=9239ff04-6aab-4e83-91e5-fdb80378639c
- https://developer.uber.com/docs/drivers/references/api/v1/partners-trips-get ; https://developer.uber.com/docs/drivers/introduction
- https://www.uber.com/us/en/drive/services/uberblack/
- https://help.uber.com/en/driving-and-delivering/article/uber-black--suv-requirements?nodeId=c4d7d4a3-0c86-481a-ab3e-4dda597c987c
- https://help.uber.com/driving-and-delivering/article/select-trip-or-delivery-options?nodeId=2e6ebbdc-7ba5-4da9-9778-1fe02e0b9519
- https://www.uber.com/us/en/marketplace/matching/
- https://help.uber.com/en/driving-and-delivering/article/what-is-trip-radar-and-how-does-it-work?nodeId=b6fb7065-ce66-490c-a911-d4e6d5c10d29 ; https://therideshareguy.com/uber-trip-radar/
- https://help.uber.com/en/driving-and-delivering/article/reserve-faq?nodeId=edd655fe-d600-44bf-97cf-e917fbd6cc72
- https://www.uber.com/us/en/business/sign-up/premium-rides/
- https://gridwise.io/blog/how-much-do-uber-black-drivers-make ; https://gridwise.io/blog/uberx-vs-uber-comfort-vs-uber-black
- https://www.uberpeople.net/threads/uber-black.496466/ (read in Chrome) ; https://www.uberpeople.net/threads/not-receiving-trip-request-fo-my-uber-black.501684/ (snippet only)
- https://www.uber.com/global/en/r/airports/den/driver-information
- https://help.lyft.com/hc/en-us/all/articles/115012929647
- https://visitdenver.com/about-denver/transportation/airport-info/
- https://www.carserviceofdenver.com/blog/private-black-car-service-vs-uber-black-denver/
- https://gridwise.io/blog/denver/uber-and-lyft-driver-instructions-for-denver-international-airport-den/ (404 today; snippet)
- https://cdn.flydenver.com/app/uploads/2023/09/25092935/100_gt1.pdf (403 today; snippet) ; https://dwuconsulting.com/info/data/tnc
- https://www.uberpeople.net/threads/hello-everyone.493149/ (read in Chrome)
- https://www.youtube.com/watch?v=ZmN3_B8TKTg (transcript) ; https://www.youtube.com/watch?v=2mqkvq32fBY (transcript)
- https://therideshareguy.com/uber-drivers-guide-to-denver/ ; https://gigglefinance.com/best-time-to-drive-uber-in-denver-pay-requirements-tips/
- https://www.uber.com/global/en/r/cities/car-service/denver-co-us
- https://www.uber.com/us/en/newsroom/onlyonuber25/ ; https://dmnews.co.uk/uber-launches-new-rides-heatmap-to-help-uk-drivers-find-busy-areas-and-boost-earnings/ ; https://piunikaweb.com/2025/10/13/new-uber-heat-map-released-drivers-react/
- https://help.uber.com/driving-and-delivering/article/when-and-where-are-the-most-riders?nodeId=456fcc51-39ad-4b7d-999d-6c78c3a388bf ; https://www.uber.com/us/en/drive/driver-app/how-surge-works/ ; https://www.uber.com/us/en/blog/offline-delivery-heatmap/ ; https://www.uber.com/us/en/blog/uber-encore-faqs/ (California-only)
