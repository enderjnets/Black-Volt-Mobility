# Setup: Smart reservation (screenshots → reservation, MiniMax-M3 vision)

The **Smart** tab of *Add reservation* (`/dashboard/add`) lets the driver drop,
paste or upload **one or several screenshots** of a client's message (SMS,
WhatsApp, email, a note). A vision model reads them — treating multiple images as
one conversation — and pre-fills a single reservation. Until configured,
`SMART_SIMULATED=true` returns a deterministic demo sample so the flow works
without billing.

## Two providers (pick by which MiniMax key you have)

`SMART_VISION_PROVIDER`:

- **`minimax_coding_vlm`** (default) — MiniMax **Coding Plan** (`sk-cp-…` key,
  flat subscription). Calls `POST {SMART_VISION_HOST}/v1/coding_plan/vlm` with one
  image per request (the backend calls it once per screenshot and **merges** the
  results into one reservation, newer images winning). The Coding Plan must be
  **active** for the key — an inactive/expired plan returns
  `base_resp 1004 "token is unusable"`.
- **`minimax_anthropic`** — **MiniMax-M3** over `SMART_VISION_BASE_URL`
  (`…/anthropic`) with a pay-as-you-go `sk-api-…` key. All images go in one call.
  Only M3 reads images; M2.x and `kimi-for-coding` silently ignore them. Needs
  wallet balance, else `402 insufficient_balance`.

Per the project rule we use MiniMax (not Anthropic OAuth). Formats: JPEG, PNG,
GIF, WEBP · max **10 MB**/image · up to **5** images. Extraction is
**best-effort**: a failure leaves the fields empty (the driver fills them in) and
never blocks the form.

## Activate (on the ROG)

In `~/Black-Volt-Mobility/.env` — Coding Plan (default):

```
SMART_SIMULATED=false
SMART_VISION_PROVIDER=minimax_coding_vlm
SMART_VISION_HOST=https://api.minimax.io      # or https://api.minimaxi.com (mainland)
SMART_VISION_API_KEY=sk-cp-…                  # Coding Plan key — secret, never commit
SMART_MAX_IMAGES=5
```

Or pay-as-you-go MiniMax-M3:

```
SMART_SIMULATED=false
SMART_VISION_PROVIDER=minimax_anthropic
SMART_VISION_BASE_URL=https://api.minimax.io/anthropic
SMART_VISION_MODEL=MiniMax-M3
SMART_VISION_API_KEY=sk-api-…                 # secret, never commit
```

Then rebuild the backend:

```bash
docker compose up -d --build backend
```

The Smart tab now runs real extraction. Leaving `SMART_SIMULATED=true` (or an
empty key) keeps the demo sample — the API responds with `"simulated": true` and
the UI shows a subtle "demo mode" note.

## Notes

- The key is read only from `.env` (gitignored). Rotate it if it ever leaks.
- Cost: each extraction is one MiniMax-M3 call over the supplied images. This is
  an internal driver tool (the driver processes their own clients' messages).
