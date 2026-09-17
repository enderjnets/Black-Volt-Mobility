# Demand heatmap for a single-driver PWA: research brief

Checked 2026-09-17 unless noted. Word budget: ~2,150 (over the 1,800 cap by the added 7-day-forecast subsection). Library versions come from the npm/PyPI registries queried today, not from blogs.

## 1. Map rendering

**(a) Google HeatmapLayer status.** Deprecated May 27, 2025 ("no longer supported due to low customer usage") and **decommissioned in Maps JS v3.65.1c on May 20, 2026** ("The Heatmap Layer functionality in the Maps JavaScript API is now decommissioned"). Google's stated replacement: "third-party library integrations like deck.gl, which offers a HeatmapLayer implementation." Google's own sample uses deck.gl 8.9.22 with a `mapId` (vector map). [deprecations, releases, deckgl-heatmap example]

**(b) Options.**

| Stack | Version (today) | Basemap cost/terms | Notes |
|---|---|---|---|
| Google Maps JS + `@deck.gl/google-maps` | 9.4.0 (2026-09-05) | Dynamic Maps: 10,000 free events/month, then **$7.00 per 1,000** (10,001–100,000). A load is "successful map load"; pans/zooms/layer switches don't count. | Vector and raster both supported; vector needs a `mapId`. Old bug #6994 (heatmap covering the map on vector + `interleaved:true`) is closed, workaround `interleaved:false`. deck.gl `HeatmapLayer` on iOS Safari "falls back to an 8-bit low-precision mode" (integer weights, ≤255 per pixel); this affects the KDE layer only, not hex polygons. Requires putting a browser key in the PWA (referrer-restricted). |
| MapLibre GL JS + free vector tiles | 6.10.0 (2026-09-15) | OpenFreeMap: "no limits on the number of map views or requests. There's no registration, no user database, no API keys"; commercial OK; attribution required; one donation-funded operator. Protomaps API: "free for non-commercial use. For commercial use, become a GitHub Sponsor"; key required. MapTiler Free: 5k sessions, 100k requests/month, "personal or non-commercial use", logo required; Flex $30/month. | Native `heatmap` layer type (`heatmap-weight/-radius/-intensity/-color/-opacity`) over a GeoJSON point source; hexes are a plain `fill` layer. No key in the client. |
| Leaflet + leaflet.heat + OSM raster | Leaflet 1.9.4 (2023-05-18); leaflet.heat 0.2.0 (npm, 2015-10-26; last commit 2024-06-28) | tile.openstreetmap.org policy: unique User-Agent, attribution, no bulk/prefetch ("Offline use is not permitted"), and "We may block access, without notice, if your usage degrades the service." | Raster only, canvas heat plugin unmaintained. |

**Terms check (load-bearing for mixing stacks).** Google's Service Specific Terms (last modified June 10, 2026) say, per API: "4.2 No use with a non-Google map. Customer must not use Google Maps Content from the Directions API in conjunction with a non-Google map" and identically for Places (§14.2). The restriction is on *Google content on a non-Google map*, not on an app that contains a non-Google map. Our reading: compliant if the MapLibre page draws only your own model output (no Directions polylines, no Places pins). Confirm before shipping.

**Recommendation:** MapLibre GL JS 6.x + OpenFreeMap tiles, with a self-hosted PMTiles extract of Colorado on your VPS as fallback (OpenFreeMap is one volunteer's servers). Cost does not discriminate: at a few hundred loads/month Google is also free. What discriminates: no browser key to expose, no deprecation risk (Google just removed this exact feature), native heatmap and fill layers cover both hexes and raw-point views, and no deck.gl bundle. Keep Places/Directions server-side and off that map.

## 2. Spatial aggregation

- `h3` (PyPI) **4.5.0**, 2026-05-30 (h3lib 4.5.0, Python ≥3.10). `h3-js` **4.5.0**, 2026-07-01.
- Resolutions (official table): res 7 = 5.161 km², edge 1.41 km; **res 8 = 0.737 km², edge 531 m**; res 9 = 0.105 km², edge 201 m. Uber's driver heatmap uses hex-9, but it has the whole marketplace's data.
- Why hexes: "Hexagons have only one distance between a hexagon centerpoint and its neighbors', compared to two distances for squares" (Uber, 2018). This is what makes k-ring smoothing honest.
- Rendering: (i) deck.gl `H3HexagonLayer` (9.4.0; `highPrecision` default `auto`), or (ii) polygons via `h3.cell_to_boundary`/`cellToBoundary` into a MapLibre `fill` layer. Measured today with h3 4.5.0, 2,000 res-8 cells around downtown Denver, 5-decimal coords, gzip -6:
  - compact `[[h3,score],…]`: 50.6 KB raw / **9.3 KB gzip** (about +30% with a third `sd` field);
  - GeoJSON polygons: 520.1 KB / 72.3 KB gzip;
  - centroid points (for the native heatmap): 210.4 KB / 20.6 KB gzip.
- Alternatives: square grid — simpler but unequal neighbor distances; KDE — good for *displaying* raw pickups, unusable as the *decision unit* because you cannot attach exposure minutes to a continuous surface.

**Recommendation:** score at res 8 (a "wait here" zone you can drive across in a minute), smooth with `grid_disk(k=1)`, roll up to res 7 via `cell_to_parent` for zoomed-out views. Ship the compact list; build polygons in the browser with `h3-js` (one dependency, ~10 KB payload instead of ~72 KB).

## 3. Modeling with sparse data

Target: P(≥1 Black offer within N min | hex H, hour-of-week T). With a Poisson rate λ_{H,T} (offers/min while idle in H), P = 1 − exp(−λN); everything reduces to estimating λ. (Derivation, not a finding.)

**Phase A — proxies only.** Build a prior rate λ⁰_{H,T} = base(T) × Π proxy multipliers (luxury hotels, affluent zones, DEN arrival banks, event windows). It is a prior; render it labeled "no own data yet".

**Phase B — a few hundred trips + logged idle time.** Per (H,T) accumulate y = offers received and E = minutes idle-online in H. Gamma-Poisson empirical Bayes: λ ~ Gamma(α,β) with prior mean λ⁰; posterior mean **(α+y)/(β+E)**. β is "pseudo-exposure": how many of your own minutes it takes to overrule the proxy; fit (α,β) by marginal likelihood across cells. This is textbook small-area shrinkage: "Improved small area estimates are found by 'borrowing strength' from similar neighboring areas" (Datta & Ghosh, Stat. Sci. 2012). Pool neighbors (k-ring 1, weight ½) and adjacent hours (T±1, circular over 168) before shrinking — that *is* the "KDE with a time-of-week kernel", applied to counts and exposure jointly, not to points.

**Negatives = exposure.** Without E you only see pickups where you chose to go. Log **offers**, not only accepted trips, plus online-idle minutes per hex. The academic version of the supply problem: "Without explicitly accounting for this inherent distinction, predictive models of demand would necessarily represent a biased version of true demand" (Gammelli et al., censored GPs, 2020). For one driver the quantity you need is *offers reaching you*, which already nets out competing drivers; that is why offer logs beat any market-demand proxy.

**Overdispersion and growth.** Negative binomial is the same Gamma-Poisson mixture; use it when Var(y) ≫ mean (events, surges). `statsmodels` 0.15.0 GLM supports Poisson and NegativeBinomial families with `offset`/`exposure`. Move to gradient boosting (LightGBM 4.7.0, Poisson objective, log(E) offset, features: res-7 parent, hour, dow, proxies, weather) only after a few thousand exposure-hours; before that it will memorize.

**References, tiny-data takeaways.**
1. Uber, "Enhancing Uber's Guidance Heatmap with Deep Probabilistic Models" (Nov 18, 2025): predicts earnings-per-hour at hex-9, "updates every 10 minutes", a 3-mode GMM, and "By integrating variance as a filtering condition, we prevent misleading signals." → Show uncertainty and hide cells whose spread swamps the mean.
2. DiDi/UMich, "Real-world Ride-hailing Vehicle Repositioning using Deep RL" (arXiv 2103.04555): objective is income-per-hour including deadhead. → Rank hexes by score minus travel-time penalty, not raw probability.
3. Yuan et al., "Where to Find My Next Passenger?" (UbiComp 2011): from 12,000 taxis over 110 days, recommends "locations towards which they are more likely to pick up passengers quickly". → Recommend a few parking spots with expected wait, and note the data scale they needed — strong priors are not optional for you.
4. Gammelli et al. (above). → Observed demand is right-censored by supply.

### 3b. Seven-day "best hours to work" forecast

**(a) Hour-of-week baseline.** Fit a Poisson/NB GLM on your logged (zone × hour-of-week) counts with `exposure=E`, Fourier terms for hour-of-day and day-of-week (Prophet's formulation, in a GLM so the exposure offset is kept), a holiday indicator with ±1-day windows (Prophet docs: `lower_window`/`upper_window` "extend the holiday out"), and a ski-season flag. Holidays from the `holidays` package (0.104, 2026-09-07; US + CO). Ridge-penalize toward the proxy profile; the shrinkage weight `E/(E+β)` is the confidence. Bin in **America/Denver** local time — the DST switch yields a 23- and a 25-hour day; a naive 7×24 grid silently mis-bins.

**(b) Forward-known covariates.**
- DEN flight banks: AeroAPI `airports/{id}/flights/scheduled_arrivals|departures` cost "$0.005/result set", "up to $5 free per month", "10 result sets/minute" (Personal). Horizon of future schedules **not verified**. Free, stable alternative: BTS On-Time Performance (`CRSDepTime`, `CRSArrTime`, `Origin`, `Dest`, `FlightDate`; latest month June 2026) gives a typical-week DEN bank profile; lags ~2–3 months, so it misses season-boundary schedule changes — that is where AeroAPI refines.
- TSA hourly checkpoint throughput, weekly PDFs "for each airport and checkpoint" (e.g., the May 24–30, 2026 file): the best free proxy for departure-side demand by hour-of-week.
- Events: Ticketmaster Discovery, "default quota of 5000 API calls per day and rate limitation of 5 requests per second", free. PredictHQ is the paid, ride-hail-specific option (14-day trial).
- Weather: NWS `/gridpoints/{office}/{x},{y}/forecast/hourly` "over the next seven days", free, User-Agent only. Open-Meteo is "non-commercial purposes" only.

**(c) Confidence, honestly.** Serve three numbers per cell: posterior mean, an 80% interval from the Gamma posterior, and `own_share = E/(E+β)` shown as "x% from your data, y hours logged". Cells with own_share < 0.2 render hatched. No calibration claims until you have ≥4 weeks of offer logs to score against.

**(d) Output shape.** Per zone (res-7 cell or named zone): `grid[7][24] = {mean, lo, hi, own_share}`, plus `top_blocks`: contiguous runs ≥2 h where mean ≥ the driver's threshold, ranked by expected offers/hour × block length, with the covariates that lifted them ("DEN 47 arrivals 21:00–22:00", "Ball Arena 19:00").

**Recommendation:** one rate model, two views. Gamma-Poisson EB with proxy priors now; GLM with Fourier + holidays + DEN banks for the 7-day grid; gradient boosting later. Log offers and exposure from day one — the model is only as good as E.

## 4. Logging shifts from a PWA

**Honest limit: an installed PWA cannot record GPS while Uber Driver is in the foreground, on either platform.**
- iOS: Background Sync and Periodic Background Sync unsupported in Safari iOS through 27.1 (caniuse). Geolocation is Window-only: "A service worker cannot hold a watch, so no web background task can produce a fix"; "A locked screen freezes the page. `watchPosition` stops" (OurHike field report, Aug 29, 2026, three failed field tests). WebKit 211018: "the WebProcess running the service worker stays suspended." Screen Wake Lock works on Safari iOS 16.4+, but it only helps while the PWA is on screen and "does not survive the power button."
- Android Chrome: on geolocation stopping when Chrome is backgrounded, a Chromium engineer: "Yes, that's the intended behavior for Chrome" (issue 585055, 2016; installed-PWA case inferred, not tested). Page Lifecycle freezing also suspends timers and fetches.

**Workarounds, cheapest first.**
1. Manual check-ins: four buttons (online / here / offer received / offline), each one `getCurrentPosition` → hex. Captures exactly the exposure and offer counts the model needs. Zero platform risk.
2. Foreground-while-idle: keep the PWA open with a wake lock while parked waiting; auto-log every 60 s. Idle time is the exposure you need anyway; you don't need GPS during trips (Uber history has the endpoints).
3. Apple Shortcuts: Time of Day is among the triggers that "can run without asking you for confirmation" (with "Allow Running When Locked"); a community thread confirms hourly location logging via 24 Time-of-Day automations. Practical cap: one automation per slot (15-min = 96 automations; feasibility of that density implied, not verified). Coarse breadcrumbs only.
4. Capacitor wrapper: `@capacitor-community/background-geolocation` (MIT, v1.2.26, 2026-01-29; iOS needs the `location` background mode and Always permission; Android "after 5 minutes in the background Android will throttle HTTP requests initiated from the WebView") or `@capgo/background-geolocation` (MPL-2.0, Capacitor 8). Capawesome's is Insiders-only (paid). Costs an Apple developer account (UNVERIFIED), store/TestFlight distribution, and Play's background-location policy review (the Capawesome docs: Google Play "requires a policy declaration and review for every app that requests background location access").

**Recommendation:** ship 1 + 2 now; add 3 on the iPhone for breadcrumbs. Revisit 4 only if, after ~4 weeks, exposure logs are too thin to move the model.

## 5. Serving

- Scheduler: APScheduler 3.11.3 (4.0 is still alpha, a6). Run the job in a **separate process** (`python -m app.jobs.heatmap`, systemd timer or a single-worker container), not inside uvicorn workers, so it runs once.
- Every 15 min: compute the res-8 grid for the next 12 slots (3 h) and, once per hour, the 7-day zone×hour-of-week grid. Write both to Postgres (`hex_scores(computed_at, slot_start, h3, mean, lo, hi, own_share)` and `week_scores(...)`) for audit/backtests, and to Redis as pre-gzipped JSON: `heat:{slot}` (TTL 30 min) and `week:{zone}` (TTL 2 h).
- API: `GET /api/heat?at=…&res=8` → `{slot, res, cells:[[h3,mean,sd,own_share],…]}`; `GET /api/heat/top?lat&lng&minutes=10` → top-5 cells by mean minus travel penalty (use `grid_distance` × edge length, no Directions calls); `GET /api/week?zone=…` → the 7×24 grid + `top_blocks`. `ETag` = hash of `computed_at`; `Cache-Control: max-age=300, stale-while-revalidate=900`.
- Payload: 2,000 cells ≈ 9 KB gzip (compact, 2 fields; ~12 KB with 4 fields), vs 72 KB as GeoJSON — measured above. Per request the only work is one Redis GET and a gzip passthrough; `fastapi-cache2` (0.2.2, 2024) is optional.

**Recommendation:** precompute-to-Redis with Postgres as the record, compact JSON, polygons built client-side.

## URLs (all checked 2026-09-17)

- https://developers.google.com/maps/deprecations
- https://developers.google.com/maps/documentation/javascript/releases
- https://developers.google.com/maps/billing-and-pricing/pricing
- https://developers.google.com/maps/billing-and-pricing/sku-details
- https://developers.google.com/maps/documentation/javascript/examples/deckgl-heatmap
- https://cloud.google.com/maps-platform/terms/maps-service-terms
- https://deck.gl/docs/api-reference/google-maps/overview
- https://github.com/visgl/deck.gl/issues/6994
- https://deck.gl/docs/api-reference/aggregation-layers/heatmap-layer
- https://deck.gl/docs/api-reference/geo-layers/h3-hexagon-layer
- https://maplibre.org/maplibre-style-spec/layers/#heatmap
- https://maplibre.org/maplibre-gl-js/docs/examples/create-a-heatmap-layer/
- https://openfreemap.org/
- https://protomaps.com/api
- https://www.maptiler.com/cloud/pricing/
- https://operations.osmfoundation.org/policies/tiles/
- https://stadiamaps.com/blog/google-maps-heatmap-deprecated-maplibre-migration/ (secondary)
- https://registry.npmjs.org/maplibre-gl , /@deck.gl/google-maps , /@deck.gl/geo-layers , /h3-js , /leaflet , /leaflet.heat (versions/dates)
- https://api.github.com/repos/Leaflet/Leaflet.heat/commits?per_page=1
- https://pypi.org/pypi/h3/json ; https://github.com/uber/h3-py/releases
- https://h3geo.org/docs/core-library/restable
- https://www.uber.com/us/en/blog/h3/
- https://www.uber.com/us/en/blog/enhancing-ubers-guidance-heatmap-with-deep-probabilistic-models/
- https://arxiv.org/abs/2103.04555
- https://arxiv.org/abs/2001.07402
- https://www.microsoft.com/en-us/research/publication/where-to-find-my-next-passenger/
- https://arxiv.org/abs/1203.5233
- https://www.statsmodels.org/stable/glm.html ; https://pypi.org/pypi/statsmodels/json ; /lightgbm/json ; /holidays/json ; /prophet/json
- https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html
- https://www.flightaware.com/commercial/aeroapi/
- https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGK
- https://catalog.data.gov/dataset/tsa-foia-reading-room-weekly-passenger-throughput-data ; https://www.tsa.gov/sites/default/files/foia-readingroom/tsa-throughput-data-to-may-24-2026-to-may-30-2026.pdf (PDF title only; not parsed)
- https://developer.ticketmaster.com/products-and-docs/apis/getting-started/
- https://www.predicthq.com/events/ride-sharing-apps (search-level; pricing not verified)
- https://www.weather.gov/documentation/services-web-api
- https://open-meteo.com/en/terms
- https://caniuse.com/wf-periodic-background-sync ; https://caniuse.com/wake-lock
- https://bugs.webkit.org/show_bug.cgi?id=211018
- https://github.com/OurHike/OurHike/issues/1182
- https://groups.google.com/a/chromium.org/g/chromium-bugs/c/LgjuEMklAbQ
- https://developer.chrome.com/docs/web-platform/page-lifecycle-api
- https://support.apple.com/guide/shortcuts/create-a-new-personal-automation-apdfbdbd7123/ios
- https://discussions.apple.com/thread/255727633
- https://github.com/capacitor-community/background-geolocation
- https://github.com/Cap-go/capacitor-background-geolocation
- https://capawesome.io/docs/sdks/capacitor/background-geolocation/
- https://pypi.org/pypi/APScheduler/json ; https://pypi.org/pypi/fastapi-cache2/json
- https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide (secondary, 2026-03-20)

UNVERIFIED items are marked inline: AeroAPI schedule horizon; 96-slot Shortcuts density; installed-PWA behavior on Android inferred from the Chrome/WebView statement; PredictHQ pricing.
