# "Where to wait" — setup (Phase 1)

The planner needs three things once, plus the owner's data.

## 1. Environment (`.env` on the VPS)

These are variable names and what they do. **Values here are placeholders — never
write a real key or coordinate into this file, a commit, or the CHANGELOG.** Real
values live only in the server's `.env` (gitignored).

| var | meaning | value |
|---|---|---|
| `DEMAND_ENABLED` | shows the "Where to wait" tab and schedules the hourly recompute | `true` |
| `CENSUS_API_KEY` | free key for the Census API priors used to seed the model | `<your Census API key>` (get one at https://api.census.gov/data/key_signup.html) |
| `DEN_LOT_LAT` | latitude of the DEN commercial holding lot, for tagging waits spent there | `<latitude of the DEN commercial holding lot>` |
| `DEN_LOT_LNG` | longitude of the same lot | `<longitude of the DEN commercial holding lot>` |
| `DEN_LOT_RADIUS_M` | radius (meters) around that point counted as "at the lot" | `400` |
| `DEMAND_HOME_LAT` | the driver's home latitude | `<the home latitude you want excluded>` |
| `DEMAND_HOME_LNG` | the driver's home longitude | `<the home longitude you want excluded>` |
| `DEMAND_HOME_RADIUS_M` | radius (meters) around home excluded from the model | `300` |
| `DEMAND_BRIDGE_FARE_DEFAULT` | minimum fare that makes a lower-tier ride worth taking as a "bridge" into a clearly better-paying zone, when a per-rate-config override isn't set | `35` |

`DEMAND_HOME_LAT` / `DEMAND_HOME_LNG` exist so the hours the driver spends at home
are excluded from the wait statistics — without them, idle time at home would be
counted as "waiting" and would distort every cell in the planner. They are the
driver's actual home coordinates, so they belong **only** in the server's `.env`,
never in this doc, a commit, or the CHANGELOG. Leaving `DEN_LOT_LAT`/`DEN_LOT_LNG`
both empty keeps DEN-lot tagging off.

Restart the backend after changing them (`docker compose up -d backend`).

## 2. Static data (run once, then when the curated list changes)

```bash
docker compose exec -T backend python -m app.scripts.build_demand_priors     # Census + places → hex_priors
docker compose exec -T backend python -m app.scripts.build_flight_baseline   # BTS On-Time → den_flight_baseline (monthly)
```

`backend/data/demand_places.json` is committed; regenerate it locally with
`python -m app.scripts.geocode_places` after editing `app/services/demand_places.py`.

Monthly cron on the VPS (user crontab):

```
15 4 3 * * cd ~/Black-Volt-Mobility && docker compose exec -T backend python -m app.scripts.build_flight_baseline >> ~/bv_flights.log 2>&1
```

## 3. The owner's data

1. Uber → Help → "Request your personal Uber data" → download the ZIP when the email arrives.
2. Dashboard → Where to wait → Import → drop the ZIP. The summary lists the files found and, in
   red, the ones missing and what that means. A complete export contains the trips file
   (`driver_lifetime_trips-0.csv`, or the older `Driver Lifetime Trips` / `Trip details (Driver)`
   layouts), `Driver Online Offline.csv`, `Dispatches Offered and Accepted.csv`, and the 30-day GPS
   analytics file (`driver_app_analytics-0.csv`, under `Driver/` in recent exports) — the source of
   waiting locations and the home-hours exclusion when the other files are missing.
3. Log every shift: Online when going on, I'm here on each move, Offer (with product) on every
   ping, Offline at the end. The Week tab improves as hours accumulate; cells with < 20% own data
   are hatched.

## What it does not do (yet)

No live map (Phase 2), no paid flight schedules, no Uber credential linking, no background GPS.
