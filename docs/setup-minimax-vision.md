# Setup: Smart reservation (screenshots → reservation, MiniMax-M3 vision)

The **Smart** tab of *Add reservation* (`/dashboard/add`) lets the driver drop,
paste or upload **one or several screenshots** of a client's message (SMS,
WhatsApp, email, a note). A vision model reads them — treating multiple images as
one conversation — and pre-fills a single reservation. Until configured,
`SMART_SIMULATED=true` returns a deterministic demo sample so the flow works
without billing.

## Why MiniMax-M3

Only **MiniMax-M3** accepts image content blocks over the anthropic-compatible
endpoint (`https://api.minimax.io/anthropic`). The M2.x text models (incl.
`MiniMax-M2.7`) and `kimi-for-coding` **silently ignore images** — they will not
work for this. Per the project rule we use MiniMax (not Anthropic OAuth).

- Formats: JPEG, PNG, GIF, WEBP · max **10 MB** per image · up to **5** images.
- Extraction is **best-effort**: a model/timeout failure returns empty fields
  (the driver fills them in) and never blocks the form.

## Activate (on the ROG)

In `~/Black-Volt-Mobility/.env`:

```
SMART_SIMULATED=false
SMART_VISION_BASE_URL=https://api.minimax.io/anthropic
SMART_VISION_MODEL=MiniMax-M3
SMART_VISION_API_KEY=sk-api-…        # MiniMax API key — secret, never commit
SMART_MAX_IMAGES=5
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
