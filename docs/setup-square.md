# Setup: Square payments (Phase 3)

Card payments on the booking flow. The card is tokenized in the browser by the
**Square Web Payments SDK** (card data never touches our backend); the backend
authorizes/captures/refunds via the **Payments API**.

## Behavior

| Mode | When | Behavior |
|---|---|---|
| **Simulated** (default) | `PAYMENTS_SIMULATED=true` *or* no token | Fake payment ids (`SIMUL-…`); booking flow works without Square. |
| **Sandbox** | `PAYMENTS_SIMULATED=false` + sandbox token, `SQUARE_ENV=sandbox` | Real Square sandbox — test cards, no real money. |
| **Production** | sandbox→prod creds + `SQUARE_ENV=production` | Real charges. |

> NEVER ship `PAYMENTS_SIMULATED=true` with `APP_ENV=production`.

## 1. Get credentials (Developer Console — your action)

1. https://developer.squareup.com/apps → create an application (e.g. **Black Volt Mobility**).
2. Toggle **Sandbox** (top). Open **Credentials** and copy the **Sandbox Access
   Token** and **Application ID** (`sandbox-sq0idb-…`).
3. The **Location ID** (`L…`) is on the **Locations** page, or fetch it:
   ```bash
   curl -s https://connect.squareupsandbox.com/v2/locations \
     -H "Square-Version: 2025-04-16" -H "Authorization: Bearer <ACCESS_TOKEN>" | jq '.locations[].id'
   ```
4. Move to production later by switching to Production credentials + `SQUARE_ENV=production`.
   Sandbox and production credentials are NOT interchangeable.

## 2. Wire it (`.env` on the ROG)

```
PAYMENTS_SIMULATED=false
SQUARE_ENV=sandbox
SQUARE_ACCESS_TOKEN=EAAA...        # SECRET — server-side only
SQUARE_LOCATION_ID=L...
SQUARE_APPLICATION_ID=sandbox-sq0idb-...
```

The frontend reads `application_id`/`location_id`/`env` from `GET /api/v1/payments/config`
(no build-time env needed). Rebuild the backend:

```bash
docker compose up -d --build backend
```

## Payment lifecycle

- **Authorize** at booking (`POST /payments`, `autocomplete=false`) → holds funds,
  ride → `confirmed`, Payment row `authorized`.
- **Capture** on ride completion (`POST /payments/{id}/capture`, staff) → `captured`.
- **Void / refund**: cancel an authorization, or `POST /payments/{id}/refund` a
  captured payment (staff) → `refunded`.

## Sandbox test cards

| Scenario | Card | CVV | Exp / Postal |
|---|---|---|---|
| Success | `4111 1111 1111 1111` | `111` | any future / any |
| Decline | `4000 0000 0000 0002` | `111` | any |
| CVV failure | (any) | `911` | any |
| 3D Secure challenge | `4310 0000 0020 1019` | `111` | code `123456` |

## API surface

- `GET  /api/v1/payments/config` — public Web SDK config.
- `POST /api/v1/payments` — authorize (`{ride_id, source_id, amount?}`).
- `POST /api/v1/payments/{id}/capture` — staff.
- `POST /api/v1/payments/{id}/refund` — staff (`{reason?}`).
- `GET  /api/v1/payments/{id}` — status.
