# Setup: Google Maps Platform (route distance + duration + autocomplete)

Phase 2's booking engine prices a ride from its **route** (distance + duration)
and the tenant's **rate config**. Routes come from Google Maps Platform. Until a
key is wired the backend runs in **simulated mode** — deterministic stub routes
so the whole booking flow (quote → ride → fare) works in dev/demo without
billing. Flip to live with one key + one flag.

## How it behaves

| Mode | When | Behavior |
|---|---|---|
| **Simulated** (default) | `MAPS_SIMULATED=true` *or* no key | Hash-based deterministic distance/duration; canned Denver autocomplete. Each quote is tagged `route_simulated: true`. |
| **Live** | `MAPS_SIMULATED=false` **and** `GOOGLE_MAPS_API_KEY` set | Real Distance Matrix + Places Autocomplete. Falls back to a simulated route if Google errors, so a transient outage never blocks a booking. |

> NEVER ship `MAPS_SIMULATED=true` with `APP_ENV=production` (anti-pattern #5).

## 1. Create the key (Google Cloud Console — your action)

1. https://console.cloud.google.com → same project as the OAuth client
   (`black-volt-mobility`) is fine.
2. **APIs & Services → Library** → enable **all three**:
   - **Distance Matrix API** (route distance + duration)
   - **Directions API** (multi-stop routing, used as we add stops)
   - **Places API** (address autocomplete)
3. **APIs & Services → Credentials → Create credentials → API key**.
4. **Restrict the key** (recommended):
   - **Application restrictions**: *None* for the server (the backend calls
     Google server-side). Do NOT restrict to HTTP referrers — that's for
     browser keys only.
   - **API restrictions**: limit to the three APIs above.
5. Enable **billing** on the project (Maps Platform requires it; there's a
   monthly free tier that covers MVP traffic).
6. Copy the key. It is a **secret** — server-side only, never expose it in the
   frontend bundle.

## 2. Wire it (the agent does this once you provide the key)

In the ROG `~/Black-Volt-Mobility/.env`:

```
MAPS_SIMULATED=false
GOOGLE_MAPS_API_KEY=<your-server-key>
```

Then rebuild the backend (the key is read at request time):

```bash
docker compose up -d --build backend
```

Verify a live quote (note `route_simulated` flips to `false`):

```bash
curl -s -X POST localhost:8012/api/v1/quote \
  -H 'Content-Type: application/json' \
  -d '{"pickup":"Union Station, Denver, CO","dropoff":"Denver International Airport"}'
```

## API surface (Phase 2)

- `POST /api/v1/quote` — price a candidate trip (open; backs the calculator).
- `GET  /api/v1/places/autocomplete?q=` — address suggestions.
- `GET  /api/v1/rate-config` — current fare engine (open, read-only).
- `PUT  /api/v1/rate-config` — edit fares (staff).
- `POST /api/v1/rides` — create a ride (passenger books own / staff manual).
- `GET  /api/v1/rides` — list (staff: all; passenger: own).
- `GET  /api/v1/rides/{id}` · `PATCH /api/v1/rides/{id}` — detail + status change.
