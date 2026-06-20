# Design — Publish to IG/FB/TikTok via Buffer

> Status: approved-for-spec-review · 2026-06-20 · Phase "Social" Stage 3 (real publish)

## Goal

Connect Black Volt's real social channels (Instagram, Facebook, TikTok) through
the owner's **Buffer** account and publish **owner-approved** posts to them for
real — replacing the simulated `_do_publish` (`sim_xxxx` external ids) with real
Buffer post ids. Buffer holds the platform OAuth tokens and performs the actual
publishing, so Black Volt never touches Meta App Review or the TikTok Content
Posting audit.

Non-goal this round (explicitly deferred): pulling comments/DMs back into the
Inbox and real engagement analytics from Buffer. Buffer's API exposes those
poorly; Inbox + analytics stay on their current (simulated) path.

## Why Buffer (decided with owner)

The owner already runs Buffer (`blackvoltmobility@gmail.com`) with Instagram
connected. Native per-platform OAuth + publishing APIs are gated by weeks of
Meta/TikTok app review and business verification. Buffer's GraphQL API lets a
single account push posts to its own connected channels with a **personal API
key** — exactly our single-operator case (third-party OAuth, which a resale SaaS
would need, is not yet open in Buffer, and we do not need it here).

## Verified Buffer API contract (introspected live, 2026-06-20)

- Endpoint: `https://api.buffer.com` (GraphQL). Auth: `Authorization: Bearer <key>`.
- Account → `account { id email organizations { id name } }`.
  - Org id: `6a36d65cfe97ad6ade6b8e0a` (the owner's only org).
- Channels → `channels(input:{ organizationId }) { id name service type displayName isDisconnected isLocked serviceId }`.
  - Currently connected: Instagram `blackvoltmobility` (type `business`),
    id `6a36dda938b5579345b8dde6`. FB/TikTok appear here once added in Buffer's UI.
- `createPost(input: CreatePostInput!) { id status dueAt channelId error }`:
  - `channelId: ChannelId!` — **one channel per call** (loop per target).
  - `schedulingType: SchedulingType!` — use `automatic` (Buffer auto-publishes;
    `notification` would require a phone confirmation).
  - `mode: ShareMode!` — `shareNow` | `addToQueue` | `customScheduled` | `shareNext`.
  - `dueAt: DateTime` — required when `mode = customScheduled`.
  - `text: String` — caption + hashtags.
  - `assets: [AssetInput!]!` — `[{ video: { url, thumbnailUrl, metadata { title } } }]`.
    Media is fetched **by URL**; our rendered mp4 is already public at
    `https://app.blackvoltmobility.com/media/<media_path>`.
  - `metadata: PostInputMetaData` — per network. **Instagram requires**
    `instagram: { type: PostType!, shouldShareToFeed: Boolean! }`.
    `PostType` includes `reel`, `post`, `story`, ...; Facebook/TikTok have their
    own metadata inputs added when those channels exist.

## Owner decisions

1. Instagram: publish 9:16 video as **Reel** (`type: reel`, `shouldShareToFeed: true`).
2. Publish-now (approved, no `scheduled_at`) → `mode: shareNow`. Scheduled
   (`scheduled_at` set) → `mode: customScheduled` + `dueAt`.

## Architecture

### Backend adapter — `backend/app/services/social_buffer.py` (new)

A thin async GraphQL client over `httpx` (mirrors `render_client.py`). Pure I/O,
no DB. One clear purpose: talk to Buffer.

- `is_live() -> bool` — `SOCIAL_PUBLISH_VIA_BUFFER` true AND `BUFFER_API_KEY` and
  `BUFFER_ORG_ID` set.
- `async list_channels() -> list[dict]` — returns `[{id, service, name, display_name, connected}]`
  (`connected = not isDisconnected and not isLocked`).
- `async create_post(*, channel_id, service, text, video_url, thumbnail_url=None, mode, due_at=None) -> dict`
  — builds the network-correct `metadata` (IG → reel), posts, returns
  `{id, status, due_at}` or raises `BufferError` on a GraphQL/HTTP error.
- Internal `_gql(query, variables)` with a short timeout + one retry on transient
  network error; raises `BufferError(message)` (message is sanitized — never
  leaks the key). The key is read from settings, never logged, never returned.

### Config — `backend/app/config.py`

```
BUFFER_API_KEY: str = ""          # personal API key (.env, server-side only)
BUFFER_ORG_ID: str = ""           # Buffer organization id
SOCIAL_PUBLISH_VIA_BUFFER: bool = False
```

`Settings` gains `is_buffer_live` (mirrors `is_social_render_live`). Guard rule
(anti-pattern #5): if `APP_ENV=production` and `SOCIAL_PUBLISH_VIA_BUFFER` is
true but the key/org are missing, log a WARN and treat as not-live (simulate),
never crash.

### Connect = "Sync from Buffer" (no OAuth in our app)

New service `social.sync_buffer_channels(db, *, tenant_id) -> list[dict]`:
- Calls `social_buffer.list_channels()`.
- For each channel whose `service` is in `SOCIAL_PLATFORMS`
  (instagram/facebook/tiktok), upsert a `SocialAccount` for the tenant:
  - `external_account_id = <buffer channel id>`, `display_name = <handle>`,
    `status = "connected"` (or `"disconnected"` if Buffer reports it disconnected).
  - `access_token` / `refresh_token` stay **null** — Buffer holds the real tokens.
- Channels on services we do not target are ignored.
- Returns the refreshed account list (`_account_out`, token-free).

New endpoint `POST /social/accounts/sync` (admin-only) → `sync_buffer_channels`.
`GET /social/accounts` unchanged (still token-free).

### Real publish — `backend/app/services/social.py`

`_do_publish` becomes **async** (both callers — `publish_post` and the scheduler
`publish_due` — are already async):

```
async def _do_publish(db, row) -> None:
    targets = row.targets or _DEFAULT_TARGETS
    if social_buffer.is_live():
        accounts = { connected SocialAccount by platform for this tenant }
        ext = dict(row.external_ids or {})
        published_any = False
        for platform in targets:
            acct = accounts.get(platform)
            if not acct or acct.status != "connected":
                continue                     # skip targets not connected in Buffer
            text = _compose_text(row.caption, row.hashtags)
            video_url = _public_media_url(row.media_path)   # validated own-host
            mode, due_at = ("customScheduled", row.scheduled_at) if row.scheduled_at else ("shareNow", None)
            res = await social_buffer.create_post(
                channel_id=acct.external_account_id, service=platform,
                text=text, video_url=video_url, mode=mode, due_at=due_at)
            ext[platform] = res["id"]
            published_any = True
        row.external_ids = ext
        row.status = "published" if published_any else "failed"
        row.published_at = _now() if published_any else None
        return
    # simulated fallback (unchanged): sim_<hex> per target
```

Helpers:
- `_compose_text(caption, hashtags)` → caption + `"\n\n"` + hashtags (trimmed).
- `_public_media_url(media_path)` → `f"{settings.PUBLIC_BASE_URL}/media/{media_path}"`
  (`PUBLIC_BASE_URL` already exists, defaults to `https://app.blackvoltmobility.com`).
  **Validation:** if `media_path` is missing, a `simulated://` sentinel, or is an
  absolute/`..`-escaping path that would resolve off `PUBLIC_BASE_URL`, raise /
  skip Buffer (no SSRF, no posting a placeholder).

`publish_post` and `publish_due` change their `_do_publish(row)` calls to
`await _do_publish(db, row)`. `publish_due`'s idempotency guard (re-assert
`status == "scheduled"` inside the loop) is unchanged; a Buffer failure marks the
row `failed` and does not raise out of the scheduler loop.

### Frontend — `components/bv/dash/SocialMedia.tsx` + `lib/social.ts`

- `lib/social.ts`: add `syncBufferChannels(): Promise<SocialAccount[]>` →
  `POST /v1/social/accounts/sync`.
- Accounts tab:
  - A **"Sync from Buffer"** button (calls `syncBufferChannels`, refreshes list,
    shows a toast with count synced).
  - Per platform: ✅ connected with handle, or "Connect in Buffer" → external
    link to `https://publish.buffer.com` (open Buffer to add the channel).
  - Replace the static "soon" badge with the real connected/disconnected state.
- i18n: add EN + ES strings for the new labels (sync button, connect-in-buffer,
  synced toast). Both dictionaries.

## Data flow

```
Owner approves post (optionally with scheduled_at)
   → social.publish_post / scheduler.publish_due
       → _do_publish (buffer live?)
           → social_buffer.create_post(channel_id, video_url=/media/..., mode, IG→reel)
               → Buffer GraphQL  → Buffer publishes to IG/FB/TikTok
           → store Buffer post id in SocialPost.external_ids[platform]
           → status = published
```

## Error handling

- Buffer GraphQL/HTTP error → `BufferError` (sanitized). In `_do_publish`, a
  target that errors is skipped; if no target succeeds the post is marked
  `failed` (owner can retry). Errors are logged without the key or token.
- Not-live (flag off / key missing) → simulated fallback, prod-guard WARN.
- Media URL invalid / off-host → that target is skipped (never POST a bad/foreign
  URL to Buffer).
- Channel not connected in Buffer for a requested target → skipped (the post can
  still publish to the targets that are connected).

## Security

- `BUFFER_API_KEY` only in `.env` (gitignored), read via settings, never logged,
  never returned by any endpoint (`_account_out` already omits tokens).
- All new endpoints are `require_admin` + tenant-scoped (the whole module is).
- `_public_media_url` host-validates before sending to Buffer (no SSRF / no
  arbitrary external URL).
- Every query stays tenant-scoped (anti-pattern #6).

## Testing

TDD, service-level with the Buffer HTTP layer mocked (mirror existing social
tests):
1. `social_buffer.create_post` builds the correct GraphQL for IG (reel,
   shouldShareToFeed, shareNow vs customScheduled+dueAt) — assert variables.
2. `sync_buffer_channels` upserts one `SocialAccount` per targeted channel,
   stores the Buffer channel id, marks connected, ignores non-target services,
   returns token-free output.
3. `_do_publish` (buffer live, mocked adapter): publishes to each connected
   target, stores Buffer ids in `external_ids`, sets `published`; marks `failed`
   when no target is connected; falls back to simulated when not live.
4. Endpoint `POST /social/accounts/sync` is admin-gated and returns token-free
   accounts.
5. `_public_media_url` rejects `simulated://`, empty, and off-host paths.

Then ruff + `alembic check` (no migration expected — reusing existing columns).

## Deployment / verification (real E2E)

- No DB migration (reuse `external_account_id`/`display_name`/`status`).
- VPS `.env`: set `BUFFER_API_KEY`, `BUFFER_ORG_ID=6a36d65cfe97ad6ade6b8e0a`,
  `SOCIAL_PUBLISH_VIA_BUFFER=true`; rebuild backend.
- Live E2E: login admin → Accounts → **Sync from Buffer** → Instagram shows
  connected `blackvoltmobility` → generate a post → render real video → approve
  (publish now) → confirm a Buffer post id is stored and the post appears in the
  Buffer queue / publishes to Instagram as a Reel.
- Checkmark: bump `version.ts` + CHANGELOG (v0.34.0 — "real publishing via
  Buffer: connect channels + publish approved posts to IG/FB/TikTok"), commit,
  push, deploy, tag, memory.

## Risks / notes

- Buffer's GraphQL API is in public beta; field names verified live today but
  could shift — the adapter is the single point to adjust.
- Only Instagram is connected in Buffer now; FB/TikTok require the owner to add
  them in Buffer (and TikTok's own Buffer-side connection). The code handles them
  automatically once present.
- IG automatic publishing requires the IG channel be a Business account (it is,
  `type: business`).
- Buffer plan limits the number of API keys and may rate-limit; the adapter uses
  a short timeout + single retry and surfaces a clean error to the owner.
