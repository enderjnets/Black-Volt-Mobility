# Social Media module — setup (going live)

Stage 1 ships **simulated by default** (`SOCIAL_SIMULATED=true`): the owner can
generate content, approve, "publish", and draft comment replies end-to-end with
**no external accounts or keys**. Nothing leaves the system. To publish for real
you complete the steps below and flip `SOCIAL_SIMULATED=false`. All secrets live
in the VPS `.env` (gitignored) — never commit them (anti-pattern #2).

## Env vars (backend / `.env`)

```bash
SOCIAL_SIMULATED=true            # keep true until everything below is ready

# Hybrid video render → BitTrader worker (Stage 2)
SOCIAL_RENDER_URL=               # BitTrader render endpoint (POST {script,...})
SOCIAL_RENDER_SIGNING_KEY=       # shared HMAC secret for the signed callback
SOCIAL_RENDER_CALLBACK_URL=      # public URL BitTrader posts the finished mp4 to
                                 # → /api/v1/social/webhooks/render

# Meta — Instagram + Facebook Reels (Stage 3)
META_APP_ID=
META_APP_SECRET=
META_GRAPH_VERSION=v21.0

# TikTok (Stage 4)
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
TIKTOK_DIRECT_PUBLISH=false       # true only once your TikTok app is approved
```

Per-platform **access tokens** are stored per-tenant in the `social_accounts`
table via the in-app OAuth connect flow (Stages 3–4), **not** in `.env`.

## Stage 2 — real video render (BitTrader)

1. Stand up the BitTrader render worker reachable from the VPS; it exposes a
   render endpoint that accepts `{job_id, tenant_id, post_id, script, callback_url}`,
   runs `agents/producer.produce_single(...)`, and POSTs the finished mp4 back to
   `SOCIAL_RENDER_CALLBACK_URL` with header `x-bv-render-signature` = base64
   HMAC-SHA256 of the raw body using `SOCIAL_RENDER_SIGNING_KEY`.
2. Set `SOCIAL_RENDER_URL` + `SOCIAL_RENDER_SIGNING_KEY` + `SOCIAL_RENDER_CALLBACK_URL`.
   The mp4 lands under the public `/media` mount (this is what gives Meta/TikTok a
   public video URL to pull from).

## Stage 3 — Instagram + Facebook (Meta Graph API)

1. Create a Meta app; add an **Instagram Business** account + a **Facebook Page**.
2. Set `META_APP_ID` / `META_APP_SECRET`; complete the in-app OAuth connect for the
   tenant (stores the page/IG access token in `social_accounts`).
3. Publishing posts the public `/media` video URL through the Graph API
   (create container → poll → publish).

## Stage 4 — TikTok

1. Register a TikTok developer app and request **Content Posting API** access
   (review required). Until approved, the module prepares an assisted-upload pack.
2. Set `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`; connect the tenant account.
3. Set `TIKTOK_DIRECT_PUBLISH=true` once the app is approved.

## Go live

Set `SOCIAL_SIMULATED=false` and restart the backend. On startup the backend logs
a WARN if it ever sees `APP_ENV=production` with `SOCIAL_SIMULATED=true` — investigate
before green-lighting. Owner approval is still required for every post and every
comment reply.
