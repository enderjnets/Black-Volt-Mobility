# Social Media module — setup (going live)

> ## ✅ LIVE: real AI video render (2026-06-18)
> Real rendering is **on in production**. Topology now:
> `VPS backend → Cloudflare quick tunnel → ROG BitTrader worker (real
> produce_single) → 28 MB AI video → HMAC-signed callback (browser UA past
> Cloudflare) → /media`. Tapping **Render video** yields a real ~28 MB AI clip
> (Hailuo/Kling + TTS + karaoke subs + thumbnail) in ~1–2 min.
>
> **Components (already deployed):**
> - **ROG**: systemd `bv-render-worker.service` (real pipeline, `sample_only=false`,
>   reads `~/.bv_render_env`) + `bv-render-tunnel.service` (isolated cloudflared
>   quick tunnel `--config /dev/null --url http://localhost:8090`). Both
>   `enable`d, auto-restart, survive reboot. Worker file: `render_worker.py` in
>   `~/.openclaw/workspace/bittrader` (pull from BitTrader `master`).
> - **VPS `.env`**: `SOCIAL_SIMULATED=false`,
>   `SOCIAL_RENDER_URL=https://<quick-tunnel>.trycloudflare.com/render`,
>   `SOCIAL_RENDER_CALLBACK_URL=https://app.blackvoltmobility.com/api/v1/social/webhooks/render`,
>   shared `SOCIAL_RENDER_SIGNING_KEY`.
>
> **⚠️ Caveat — the quick-tunnel URL is ephemeral.** If cloudflared restarts on
> the ROG, the `*.trycloudflare.com` URL changes and renders will fail until you
> re-point. Re-point with:
> ```bash
> # on the ROG: get the current URL
> sudo journalctl -u bv-render-tunnel | grep -oE 'https://[a-z-]+\.trycloudflare\.com' | tail -1
> # on the VPS: update + restart
> sed -i "s|^SOCIAL_RENDER_URL=.*|SOCIAL_RENDER_URL=<URL>/render|" ~/Black-Volt-Mobility/.env
> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
> ```
> **Robust upgrade (recommended): Tailscale on the VPS** → reach the ROG worker
> directly at `http://100.88.47.99:8090/render` (stable, no tunnel). Needs a
> one-time `sudo tailscale up` login on the VPS. (The VPS-local `render-worker`
> container remains as a simulated fallback.)
>
> ---

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

## Stage 2 — real video render (BitTrader) — IMPLEMENTED

The worker ships in BitTrader as `render_worker.py` (stdlib HTTP + ffmpeg, no extra
deps). It verifies an HMAC-signed render job, runs `agents/producer.produce_single`
(or an ffmpeg sample if the paid video APIs aren't configured: `BV_RENDER_SAMPLE=1`),
and POSTs the finished mp4 back inline as base64 to `SOCIAL_RENDER_CALLBACK_URL` with
header `x-bv-render-signature` = base64 HMAC-SHA256 of the raw body. Black Volt
verifies, magic-sniffs and size-caps it, and writes it under the public `/media`
mount (atomic write) — which is also what later gives Meta/TikTok a public video URL.

1. On a host reachable from the VPS, run:
   ```bash
   BV_RENDER_SIGNING_KEY=<shared-secret> python3 render_worker.py   # listens :8090
   # add BV_RENDER_SAMPLE=1 to emit a placeholder clip without the paid video APIs
   ```
2. In Black Volt `.env` set the same secret + endpoints, then `SOCIAL_SIMULATED=false`:
   ```bash
   SOCIAL_RENDER_URL=https://<worker-host>:8090/render
   SOCIAL_RENDER_SIGNING_KEY=<shared-secret>          # identical on both sides
   SOCIAL_RENDER_CALLBACK_URL=https://app.blackvoltmobility.com/api/v1/social/webhooks/render
   SOCIAL_RENDER_MAX_MB=60
   ```

> The Social module is **admin-only** (`require_admin`): only the owner / admins
> see and manage it. The render callback carries no session — it's HMAC-verified.

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
