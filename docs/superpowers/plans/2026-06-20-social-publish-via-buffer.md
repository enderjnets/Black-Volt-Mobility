# Social Publish via Buffer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish owner-approved Black Volt posts to real Instagram/Facebook/TikTok channels through the owner's Buffer account, replacing the simulated `_do_publish`.

**Architecture:** A thin async Buffer GraphQL adapter (`social_buffer.py`, httpx) exposes `list_channels` + `create_post`. A new `social.sync_buffer_channels` upserts a `SocialAccount` per Buffer channel (Buffer holds the platform tokens — no OAuth in our app). `_do_publish` becomes async and, when Buffer is live, posts each connected target's video-by-URL to Buffer (IG as a Reel), storing the returned Buffer post id. Everything stays admin-only + tenant-scoped; the simulated path is the fallback.

**Tech Stack:** FastAPI + SQLAlchemy 2 async, httpx 0.28, pytest/pytest-asyncio; Next.js 14 + TypeScript frontend.

## Global Constraints

- LLM traffic only via Kimi/MiniMax — never Anthropic OAuth (not touched here, but no new LLM calls).
- No secrets in committed files: `BUFFER_API_KEY` only in `.env` (gitignored), never logged, never returned by any endpoint.
- Every domain query scoped by `tenant_id` (anti-pattern #6).
- Never ship a `*_SIMULATED=true`/live-flag mismatch silently in prod (anti-pattern #5): Buffer publish is gated by `is_buffer_live`; if the flag is on but key/org missing, treat as not-live (simulate), never crash.
- Backend `ruff` line length 100; default to NO comments (only non-obvious *why*). Frontend `tsc --noEmit` + `next lint` zero errors; all UI strings via `t()` in BOTH `en` and `es` dictionaries.
- Verified Buffer facts (introspected live 2026-06-20): endpoint `https://api.buffer.com`; org id `6a36d65cfe97ad6ade6b8e0a`; IG channel `blackvoltmobility` id `6a36dda938b5579345b8dde6`; `createPost(input: CreatePostInput!)` with `channelId`, `schedulingType: automatic`, `mode` (`shareNow`/`customScheduled`/`addToQueue`), `dueAt`, `text`, `assets: [{video:{url,thumbnailUrl}}]`, `metadata.instagram:{type,shouldShareToFeed}`; IG decision = Reel; publish-now = `shareNow`, scheduled = `customScheduled`+`dueAt`.

## File Structure

- Create `backend/app/services/social_buffer.py` — Buffer GraphQL adapter (I/O only, no DB).
- Modify `backend/app/config.py` — add `BUFFER_*` settings + `is_buffer_live` property.
- Modify `backend/app/services/social.py` — `_compose_text`, `_public_media_url`, `sync_buffer_channels`, async `_do_publish` (+ await in callers), import `social_buffer`.
- Modify `backend/app/api/v1/social.py` — `POST /social/accounts/sync`.
- Create `backend/tests/test_social_buffer.py` — adapter tests.
- Modify `backend/tests/test_social_service.py` — helper + sync + publish tests.
- Modify `backend/tests/test_social_api.py` — sync endpoint auth/config tests.
- Modify `frontend/lib/social.ts` — `syncBufferChannels`.
- Modify `frontend/components/bv/dash/SocialMedia.tsx` — Accounts tab Sync + connect-in-buffer.
- Modify `frontend/lib/i18n.tsx` — new account strings (en + es).
- Modify `frontend/lib/version.ts` + `CHANGELOG.md` — v0.34.0.
- Update `.env.example` (backend) — document the new vars.

---

## Task 1: Config — Buffer settings + `is_buffer_live`

**Files:**
- Modify: `backend/app/config.py` (near the TikTok/SOCIAL block, ~line 280–300)
- Modify: `backend/.env.example`
- Test: `backend/tests/test_social_buffer.py` (new)

**Interfaces:**
- Produces: `Settings.BUFFER_API_KEY: str`, `Settings.BUFFER_ORG_ID: str`, `Settings.SOCIAL_PUBLISH_VIA_BUFFER: bool`, `Settings.is_buffer_live -> bool`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_social_buffer.py`:

```python
"""Buffer adapter + config tests (no network; GraphQL layer mocked)."""
import os

os.environ["BUFFER_API_KEY"] = "test-buffer-key"
os.environ["BUFFER_ORG_ID"] = "org-test"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "true"
os.environ["SOCIAL_SIMULATED"] = "false"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


def test_is_buffer_live_true_when_configured():
    s = get_settings()
    assert s.is_buffer_live is True


def test_is_buffer_live_false_without_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "BUFFER_API_KEY", "", raising=False)
    # A fresh Settings with no key is not live.
    from app.config import Settings
    s = Settings(BUFFER_API_KEY="", BUFFER_ORG_ID="org", SOCIAL_PUBLISH_VIA_BUFFER=True)
    assert s.is_buffer_live is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_social_buffer.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'is_buffer_live'`).

- [ ] **Step 3: Add the settings + property**

In `backend/app/config.py`, after the `TIKTOK_DIRECT_PUBLISH` line and before `@property def social_live`:

```python
    # ─── Buffer (social publishing aggregator) ──────────────────────────
    # The owner's Buffer account holds the IG/FB/TikTok OAuth tokens and does the
    # real publishing. We push approved posts to it with a personal API key (read
    # from .env, never logged, never returned). Org id is the Buffer organization.
    BUFFER_API_KEY: str = ""
    BUFFER_ORG_ID: str = ""
    SOCIAL_PUBLISH_VIA_BUFFER: bool = False
```

Then, alongside the other social properties:

```python
    @property
    def is_buffer_live(self) -> bool:
        """Real publishing via Buffer requires the flag plus a key + org id. The
        flag alone (without credentials) falls back to simulation, never crashes."""
        return (
            self.SOCIAL_PUBLISH_VIA_BUFFER
            and bool(self.BUFFER_API_KEY)
            and bool(self.BUFFER_ORG_ID)
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_social_buffer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Document env vars**

In `backend/.env.example`, add under the social section:

```
# Buffer publishing (social). Personal API key from Buffer account settings.
BUFFER_API_KEY=
BUFFER_ORG_ID=
SOCIAL_PUBLISH_VIA_BUFFER=false
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/tests/test_social_buffer.py
git commit -m "feat(config): Buffer publishing settings + is_buffer_live"
```

---

## Task 2: Buffer adapter — `social_buffer.py`

**Files:**
- Create: `backend/app/services/social_buffer.py`
- Test: `backend/tests/test_social_buffer.py` (extend)

**Interfaces:**
- Consumes: `Settings.BUFFER_API_KEY`, `Settings.BUFFER_ORG_ID`, `Settings.is_buffer_live` (Task 1).
- Produces:
  - `class BufferError(Exception)`
  - `is_live() -> bool`
  - `async list_channels() -> list[dict]` → items `{"id", "service", "name", "display_name", "connected"}`
  - `async create_post(*, channel_id: str, service: str, text: str, video_url: str, thumbnail_url: str | None = None, mode: str, due_at=None) -> dict` → `{"id", "status", "due_at"}`
  - `async _gql(query: str, variables: dict) -> dict` (internal; monkeypatched in tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_social_buffer.py`:

```python
import pytest  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from app.services import social_buffer as B  # noqa: E402


@pytest.mark.asyncio
async def test_create_post_builds_ig_reel_sharenow(monkeypatch):
    captured = {}

    async def fake_gql(query, variables):
        captured["v"] = variables
        return {"createPost": {"id": "bufpost1", "status": "queued", "dueAt": None}}

    monkeypatch.setattr(B, "_gql", fake_gql)
    res = await B.create_post(
        channel_id="ch1", service="instagram", text="hi #x",
        video_url="https://app.blackvoltmobility.com/media/a.mp4", mode="shareNow",
    )
    assert res["id"] == "bufpost1"
    inp = captured["v"]["input"]
    assert inp["channelId"] == "ch1"
    assert inp["mode"] == "shareNow"
    assert inp["schedulingType"] == "automatic"
    assert inp["assets"] == [{"video": {"url": "https://app.blackvoltmobility.com/media/a.mp4"}}]
    assert inp["metadata"]["instagram"] == {"type": "reel", "shouldShareToFeed": True}
    assert "dueAt" not in inp


@pytest.mark.asyncio
async def test_create_post_scheduled_sets_dueat(monkeypatch):
    captured = {}

    async def fake_gql(query, variables):
        captured["v"] = variables
        return {"createPost": {"id": "p2", "status": "scheduled"}}

    monkeypatch.setattr(B, "_gql", fake_gql)
    dt = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    await B.create_post(
        channel_id="ch1", service="instagram", text="x",
        video_url="https://h/m.mp4", mode="customScheduled", due_at=dt,
    )
    assert captured["v"]["input"]["dueAt"] == dt.isoformat()


@pytest.mark.asyncio
async def test_list_channels_maps_connected(monkeypatch):
    async def fake_gql(query, variables):
        return {"channels": [
            {"id": "c1", "service": "instagram", "name": "bv",
             "displayName": "bv", "isDisconnected": False, "isLocked": False},
            {"id": "c2", "service": "facebook", "name": "fb",
             "displayName": "fb", "isDisconnected": True, "isLocked": False},
        ]}

    monkeypatch.setattr(B, "_gql", fake_gql)
    chans = await B.list_channels()
    by_id = {c["id"]: c for c in chans}
    assert by_id["c1"]["connected"] is True
    assert by_id["c1"]["display_name"] == "bv"
    assert by_id["c2"]["connected"] is False


@pytest.mark.asyncio
async def test_gql_raises_on_graphql_errors(monkeypatch):
    import httpx

    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "bad"}]})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    with pytest.raises(B.BufferError):
        await B._gql("query { x }", {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_social_buffer.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.services.social_buffer'`).

- [ ] **Step 3: Write the adapter**

Create `backend/app/services/social_buffer.py`:

```python
"""Buffer GraphQL adapter — Black Volt's real social-publishing path.

The owner's Buffer account holds the IG/FB/TikTok OAuth tokens and performs the
actual publishing; we push owner-approved posts to it with a personal API key.
This module is the thin, DB-free client for that handoff (mirrors render_client).

GraphQL endpoint + shapes verified live against the account on 2026-06-20.
The API key is read from settings, never logged, never returned to a client.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("blackvolt.social.buffer")

BUFFER_API_URL = "https://api.buffer.com"

_CHANNELS_Q = """
query Channels($orgId: OrganizationId!) {
  channels(input: { organizationId: $orgId }) {
    id name service displayName isDisconnected isLocked
  }
}
"""

_CREATE_POST_M = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) { id status dueAt channelId }
}
"""

# Per-network metadata builders. Instagram requires type + shouldShareToFeed;
# 9:16 ads publish as a Reel that also shares to the feed. Facebook/TikTok get
# their builders here when those channels are connected in Buffer (YAGNI now).
_NETWORK_META = {
    "instagram": lambda: {"instagram": {"type": "reel", "shouldShareToFeed": True}},
}


class BufferError(Exception):
    """A Buffer HTTP or GraphQL failure (message is sanitized — never the key)."""


def is_live() -> bool:
    return get_settings().is_buffer_live


async def _gql(query: str, variables: dict) -> dict:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.BUFFER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                BUFFER_API_URL, json={"query": query, "variables": variables}, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # network / HTTP — do not leak the key
        logger.error("buffer request failed: %s", type(e).__name__)
        raise BufferError("buffer_request_failed") from e
    if data.get("errors"):
        msgs = "; ".join(str(err.get("message", "?")) for err in data["errors"])
        logger.error("buffer graphql error: %s", msgs)
        raise BufferError(f"buffer_graphql_error: {msgs}")
    return data.get("data") or {}


async def list_channels() -> list[dict]:
    settings = get_settings()
    data = await _gql(_CHANNELS_Q, {"orgId": settings.BUFFER_ORG_ID})
    out = []
    for c in data.get("channels") or []:
        out.append({
            "id": c.get("id"),
            "service": c.get("service"),
            "name": c.get("name"),
            "display_name": c.get("displayName") or c.get("name"),
            "connected": not c.get("isDisconnected") and not c.get("isLocked"),
        })
    return out


async def create_post(
    *,
    channel_id: str,
    service: str,
    text: str,
    video_url: str,
    thumbnail_url: str | None = None,
    mode: str,
    due_at=None,
) -> dict:
    video: dict = {"url": video_url}
    if thumbnail_url:
        video["thumbnailUrl"] = thumbnail_url
    input_obj: dict = {
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": mode,
        "text": text,
        "assets": [{"video": video}],
    }
    if mode == "customScheduled" and due_at is not None:
        input_obj["dueAt"] = due_at.isoformat() if hasattr(due_at, "isoformat") else due_at
    meta_fn = _NETWORK_META.get(service)
    if meta_fn:
        input_obj["metadata"] = meta_fn()
    data = await _gql(_CREATE_POST_M, {"input": input_obj})
    post = data.get("createPost") or {}
    return {"id": post.get("id"), "status": post.get("status"), "due_at": post.get("dueAt")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_social_buffer.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Lint**

Run: `cd backend && ruff check app/services/social_buffer.py tests/test_social_buffer.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/social_buffer.py backend/tests/test_social_buffer.py
git commit -m "feat(social): Buffer GraphQL adapter (list_channels + create_post)"
```

---

## Task 3: Service helpers + `sync_buffer_channels`

**Files:**
- Modify: `backend/app/services/social.py` (import; add helpers + sync near `list_accounts`, ~line 743)
- Test: `backend/tests/test_social_service.py` (extend)

**Interfaces:**
- Consumes: `social_buffer.list_channels` (Task 2); `SocialAccount`, `SOCIAL_PLATFORMS`, `list_accounts`, `get_settings`, `select` (existing in `social.py`).
- Produces:
  - `_compose_text(caption: str | None, hashtags: str | None) -> str`
  - `_public_media_url(media_path: str | None) -> str | None`
  - `async sync_buffer_channels(db, *, tenant_id: int) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_social_service.py`:

```python
def test_compose_text():
    assert S._compose_text("Hi", "#a #b") == "Hi\n\n#a #b"
    assert S._compose_text("Hi", None) == "Hi"
    assert S._compose_text(None, "#a") == "#a"
    assert S._compose_text("  ", "") == ""


def test_public_media_url_rejects_bad_and_builds_good():
    assert S._public_media_url(None) is None
    assert S._public_media_url("simulated://sample.mp4") is None
    assert S._public_media_url("../etc/passwd") is None
    assert S._public_media_url("https://evil.com/x.mp4") is None
    url = S._public_media_url("social/a.mp4")
    assert url is not None and url.endswith("/media/social/a.mp4")


@pytest.mark.asyncio
async def test_sync_buffer_channels_upserts_targets_only(db, monkeypatch):
    from app.services import social_buffer

    async def fake_list():
        return [
            {"id": "ch-ig", "service": "instagram", "name": "bv",
             "display_name": "bv", "connected": True},
            {"id": "ch-yt", "service": "youtube", "name": "yt",
             "display_name": "yt", "connected": True},
        ]

    monkeypatch.setattr(social_buffer, "list_channels", fake_list)
    tid = (await get_default_tenant(db)).id
    out = await S.sync_buffer_channels(db, tenant_id=tid)
    ig = next(a for a in out if a["platform"] == "instagram")
    assert ig["connected"] is True and ig["status"] == "connected"
    # youtube is not a target platform → never becomes an account row.
    assert all(a["platform"] != "youtube" for a in out)
    # The Buffer channel id was stored on the row.
    row = (await db.execute(
        S.select(S.SocialAccount).where(
            S.SocialAccount.tenant_id == tid, S.SocialAccount.platform == "instagram"
        )
    )).scalars().first()
    assert row is not None and row.external_account_id == "ch-ig"
```

(Note: `pytest` is already imported in this file via `pytest_asyncio`; if `import pytest` is absent, add it at the top with the other `# noqa: E402` imports. `S.select` and `S.SocialAccount` are accessible because `social.py` imports both.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_social_service.py -k "compose_text or public_media_url or sync_buffer" -v`
Expected: FAIL (`AttributeError: module 'app.services.social' has no attribute '_compose_text'`).

- [ ] **Step 3: Add import + helpers + sync**

In `backend/app/services/social.py`, change the services import (line ~36):

```python
from app.services import llm, render_client, social_buffer
```

Add the helpers near the other private helpers (e.g. just above `_do_publish`, ~line 476):

```python
def _compose_text(caption: str | None, hashtags: str | None) -> str:
    parts = [p.strip() for p in (caption, hashtags) if p and p.strip()]
    return "\n\n".join(parts)


def _public_media_url(media_path: str | None) -> str | None:
    """Absolute public URL for a rendered asset, or None if it isn't safe to send
    to Buffer. Rejects the simulated sentinel, any scheme/absolute URL, and any
    path that escapes our /media mount (no SSRF, no posting a placeholder)."""
    if not media_path or "://" in media_path or ".." in media_path:
        return None
    rel = media_path.lstrip("/")
    if not rel:
        return None
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/media/{rel}"
```

Add `sync_buffer_channels` next to `list_accounts` (~line 759, after `list_accounts`):

```python
async def sync_buffer_channels(db: AsyncSession, *, tenant_id: int) -> list[dict]:
    """Pull the owner's Buffer channels and upsert a SocialAccount per channel
    whose service we target (IG/FB/TikTok). Buffer holds the OAuth tokens, so we
    only store its channel id + handle + connection state — never a token."""
    channels = await social_buffer.list_channels()
    existing = {
        r.platform: r
        for r in (
            await db.execute(
                select(SocialAccount).where(SocialAccount.tenant_id == tenant_id)
            )
        ).scalars().all()
    }
    for ch in channels:
        platform = ch.get("service")
        if platform not in SOCIAL_PLATFORMS:
            continue
        row = existing.get(platform)
        if row is None:
            row = SocialAccount(tenant_id=tenant_id, platform=platform)
            db.add(row)
            existing[platform] = row
        row.external_account_id = ch.get("id")
        row.display_name = ch.get("display_name")
        row.status = "connected" if ch.get("connected") else "disconnected"
    await db.commit()
    return await list_accounts(db, tenant_id=tenant_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_social_service.py -k "compose_text or public_media_url or sync_buffer" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint**

Run: `cd backend && ruff check app/services/social.py tests/test_social_service.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/social.py backend/tests/test_social_service.py
git commit -m "feat(social): Buffer channel sync + publish text/url helpers"
```

---

## Task 4: Async `_do_publish` Buffer path

**Files:**
- Modify: `backend/app/services/social.py` (`_do_publish` ~line 476; callers `publish_post` ~494, `publish_due` ~814)
- Test: `backend/tests/test_social_service.py` (extend)

**Interfaces:**
- Consumes: `social_buffer.is_live`, `social_buffer.create_post`, `social_buffer.BufferError` (Task 2); `_compose_text`, `_public_media_url` (Task 3).
- Produces: `async _do_publish(db: AsyncSession, row: SocialPost) -> None` (replaces the sync version). Callers now `await _do_publish(db, row)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_social_service.py`:

```python
@pytest_asyncio.fixture
async def _approved_ig_post(db):
    """A post with a real-looking media_path, targeting instagram, approved."""
    tid = (await get_default_tenant(db)).id
    post = await S.create_post(
        db, tenant_id=tid,
        content={"caption": "Ride in style", "hashtags": "#blackvolt"},
        lang="en", targets=["instagram"],
    )
    row = await S._get_post(db, tenant_id=tid, post_id=post["id"])
    row.media_path = "social/test.mp4"
    row.status = "approved"
    await db.commit()
    return tid, post["id"]


@pytest.mark.asyncio
async def test_do_publish_via_buffer(db, monkeypatch, _approved_ig_post):
    from app.services import social_buffer
    tid, pid = _approved_ig_post
    db.add(S.SocialAccount(
        tenant_id=tid, platform="instagram", external_account_id="ch-ig",
        display_name="bv", status="connected",
    ))
    await db.commit()
    calls = []

    async def fake_create(**kw):
        calls.append(kw)
        return {"id": f"buf-{kw['service']}", "status": "queued", "due_at": None}

    monkeypatch.setattr(social_buffer, "is_live", lambda: True)
    monkeypatch.setattr(social_buffer, "create_post", fake_create)

    out = await S.publish_post(db, tenant_id=tid, post_id=pid)
    assert out["status"] == "published"
    assert out["external_ids"]["instagram"] == "buf-instagram"
    assert calls[0]["mode"] == "shareNow"
    assert "/media/social/test.mp4" in calls[0]["video_url"]
    assert calls[0]["text"] == "Ride in style\n\n#blackvolt"


@pytest.mark.asyncio
async def test_do_publish_buffer_no_channel_marks_failed(db, monkeypatch, _approved_ig_post):
    from app.services import social_buffer
    tid, pid = _approved_ig_post
    monkeypatch.setattr(social_buffer, "is_live", lambda: True)
    # No connected SocialAccount for instagram → nothing to publish to.
    out = await S.publish_post(db, tenant_id=tid, post_id=pid)
    assert out["status"] == "failed"
    assert out["external_ids"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_social_service.py -k "do_publish" -v`
Expected: FAIL (`TypeError: object NoneType can't be used in 'await' expression` or assertion error — `_do_publish` is sync and ignores Buffer).

- [ ] **Step 3: Rewrite `_do_publish` async + update callers**

Replace the existing `_do_publish` (lines ~476–485) with:

```python
async def _do_publish(db: AsyncSession, row: SocialPost) -> None:
    """Publish a post. When Buffer is live, push each connected target's video to
    Buffer (IG as a Reel) and store the Buffer post id; otherwise simulate."""
    targets = row.targets or list(_DEFAULT_TARGETS)
    if social_buffer.is_live():
        accounts = {
            r.platform: r
            for r in (
                await db.execute(
                    select(SocialAccount).where(SocialAccount.tenant_id == row.tenant_id)
                )
            ).scalars().all()
        }
        video_url = _public_media_url(row.media_path)
        text = _compose_text(row.caption, row.hashtags)
        mode = "customScheduled" if row.scheduled_at else "shareNow"
        due_at = row.scheduled_at if row.scheduled_at else None
        ext = dict(row.external_ids or {})
        published_any = False
        if video_url:
            for platform in targets:
                acct = accounts.get(platform)
                if not acct or acct.status != "connected" or not acct.external_account_id:
                    continue
                try:
                    res = await social_buffer.create_post(
                        channel_id=acct.external_account_id, service=platform,
                        text=text, video_url=video_url, mode=mode, due_at=due_at,
                    )
                except social_buffer.BufferError as e:
                    logger.error("buffer publish failed post=%s platform=%s: %s", row.id, platform, e)
                    continue
                if res.get("id"):
                    ext[platform] = res["id"]
                    published_any = True
        row.external_ids = ext
        if published_any:
            row.status = "published"
            row.published_at = _now()
        else:
            row.status = "failed"
        return
    # Simulated fallback: deterministic-ish sentinel ids per target.
    ext = dict(row.external_ids or {})
    for t in targets:
        ext[t] = f"sim_{secrets.token_hex(4)}"
    row.external_ids = ext
    row.status = "published"
    row.published_at = _now()
```

In `publish_post` (~line 494) change:

```python
    await _do_publish(db, row)
```

In `publish_due` (~line 814) change:

```python
        await _do_publish(db, row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_social_service.py -k "do_publish or render_approve_publish or publish_due" -v`
Expected: PASS (existing simulated state-machine tests still pass; 2 new pass).

- [ ] **Step 5: Full social suite + lint**

Run: `cd backend && python -m pytest tests/test_social_service.py tests/test_social_api.py tests/test_social_render.py tests/test_social_buffer.py -q && ruff check app/services/social.py`
Expected: all pass; `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/social.py backend/tests/test_social_service.py
git commit -m "feat(social): real publish via Buffer in _do_publish (async)"
```

---

## Task 5: API — `POST /social/accounts/sync`

**Files:**
- Modify: `backend/app/api/v1/social.py` (accounts section ~line 260; import)
- Test: `backend/tests/test_social_api.py` (extend)

**Interfaces:**
- Consumes: `social.sync_buffer_channels` (Task 3), `social_buffer.is_live`, `social_buffer.BufferError` (Task 2), `require_admin`, `resolve_tenant_id` (existing).
- Produces: `POST /api/v1/social/accounts/sync` (admin-only) → token-free account list; `400 buffer_not_configured` if not live; `502 buffer_unavailable` on a Buffer error.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_social_api.py`:

```python
def test_accounts_sync_requires_admin():
    assert client.post("/api/v1/social/accounts/sync").status_code == 401
    d = _driver()
    assert d.post("/api/v1/social/accounts/sync").status_code == 403


def test_accounts_sync_requires_config():
    # This suite runs with SOCIAL_SIMULATED=true and no Buffer key → not live.
    c = _owner()
    r = c.post("/api/v1/social/accounts/sync")
    assert r.status_code == 400
    assert r.json()["detail"] == "buffer_not_configured"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_social_api.py -k "accounts_sync" -v`
Expected: FAIL (`404` — route does not exist yet).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/v1/social.py`, add to the imports:

```python
from app.services import social, social_buffer
```

(replace the existing `from app.services import social` line.)

Add after the `list_accounts` route (~line 268):

```python
@router.post("/social/accounts/sync")
async def sync_accounts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    if not social_buffer.is_live():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="buffer_not_configured"
        )
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        return await social.sync_buffer_channels(db, tenant_id=tenant_id)
    except social_buffer.BufferError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="buffer_unavailable"
        ) from None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_social_api.py -k "accounts_sync or requires_admin" -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `cd backend && ruff check app/api/v1/social.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/social.py backend/tests/test_social_api.py
git commit -m "feat(api): POST /social/accounts/sync (admin, Buffer-gated)"
```

---

## Task 6: Frontend — Sync button + connect-in-Buffer + i18n

**Files:**
- Modify: `frontend/lib/social.ts` (add `syncBufferChannels`)
- Modify: `frontend/components/bv/dash/SocialMedia.tsx` (Accounts tab)
- Modify: `frontend/lib/i18n.tsx` (en + es strings)

**Interfaces:**
- Consumes: `POST /v1/social/accounts/sync` (Task 5), `SocialAccount` type (existing).
- Produces: `syncBufferChannels(): Promise<SocialAccount[]>`; Accounts tab with a working Sync action.

- [ ] **Step 1: Add the lib function**

In `frontend/lib/social.ts`, after `listAccounts`:

```typescript
export async function syncBufferChannels(): Promise<SocialAccount[]> {
  return jsend<SocialAccount[]>("/v1/social/accounts/sync", "POST");
}
```

- [ ] **Step 2: Add i18n strings (both dictionaries)**

In `frontend/lib/i18n.tsx`, next to the existing `"dash.social.accounts.*"` keys, add to the **en** dictionary:

```typescript
    "dash.social.accounts.sync": "Sync from Buffer",
    "dash.social.accounts.syncing": "Syncing…",
    "dash.social.accounts.synced": "Channels synced",
    "dash.social.accounts.connectInBuffer": "Connect in Buffer",
    "dash.social.accounts.viaBuffer": "Channels are connected and published through your Buffer account.",
```

and to the **es** dictionary:

```typescript
    "dash.social.accounts.sync": "Sincronizar desde Buffer",
    "dash.social.accounts.syncing": "Sincronizando…",
    "dash.social.accounts.synced": "Canales sincronizados",
    "dash.social.accounts.connectInBuffer": "Conectar en Buffer",
    "dash.social.accounts.viaBuffer": "Los canales se conectan y publican a través de tu cuenta de Buffer.",
```

- [ ] **Step 3: Wire the Accounts tab**

In `frontend/components/bv/dash/SocialMedia.tsx`:

(a) Add to the imports from `lib/social` (the existing import list near `listAccounts`):

```typescript
  syncBufferChannels,
```

(b) Add state near the other `useState` hooks (e.g. by `const [accounts, setAccounts]`):

```typescript
  const [syncing, setSyncing] = useState(false);
```

(c) Add a handler (near the other handlers in the component body):

```typescript
  const onSyncBuffer = async () => {
    setSyncing(true);
    try {
      const next = await syncBufferChannels();
      setAccounts(next);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  };
```

(d) Replace the Accounts `Panel` block (the `{tab === "accounts" && ( ... )}` region, ~lines 426–462) with:

```tsx
      {tab === "accounts" && (
        <Panel title={t("dash.social.accounts.title")} icon="share-2">
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
            <Button variant="primary" size="sm" icon="refresh-cw" onClick={onSyncBuffer} disabled={syncing}>
              {syncing ? t("dash.social.accounts.syncing") : t("dash.social.accounts.sync")}
            </Button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {accounts.map((a) => (
              <div
                key={a.platform}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--obsidian-2)",
                  border: "1px solid var(--line)",
                  flexWrap: "wrap",
                }}
              >
                <Icon name={PLATFORM_ICON[a.platform] || "share-2"} size={22} color="var(--arctic)" />
                <div style={{ flex: 1, minWidth: 120 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--arctic)", textTransform: "capitalize" }}>
                    {a.display_name || a.platform}
                  </div>
                  <div style={{ fontSize: 12, color: a.connected ? "var(--cyan)" : "var(--fg3)" }}>
                    {a.connected ? t("dash.social.accounts.connected") : t("dash.social.accounts.disconnected")}
                  </div>
                </div>
                {!a.connected && (
                  <a
                    href="https://publish.buffer.com"
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 12, color: "var(--cyan)", textDecoration: "none" }}
                  >
                    {t("dash.social.accounts.connectInBuffer")}
                  </a>
                )}
              </div>
            ))}
          </div>
          <p style={{ fontSize: 12, color: "var(--fg3)", marginTop: 14, lineHeight: 1.5 }}>
            {t("dash.social.accounts.viaBuffer")}
          </p>
        </Panel>
      )}
```

- [ ] **Step 4: Type-check + lint + build**

Run: `cd frontend && npx tsc --noEmit && npx next lint && npm run build`
Expected: zero TS errors, no new lint errors, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/social.ts frontend/components/bv/dash/SocialMedia.tsx frontend/lib/i18n.tsx
git commit -m "feat(frontend): Accounts tab — Sync from Buffer + connect link"
```

---

## Task 7: Verification sweep (backend + frontend + Playwright)

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: all pass (no regressions).

- [ ] **Step 2: Alembic check (no migration expected)**

Run: `cd backend && alembic check`
Expected: "No new upgrade operations detected." (We reuse existing `SocialAccount` columns.)

- [ ] **Step 3: Frontend gates**

Run: `cd frontend && npx tsc --noEmit && npx next lint && npm run build`
Expected: clean.

- [ ] **Step 4: Playwright — Accounts tab renders at 3 viewports**

With the dev stack up (or against the deployed app after Task 8), log in as admin, open `/dashboard/social`, click **Accounts**, and confirm the **Sync from Buffer** button + per-platform rows render at 390 / 820 / 1200 px. Capture one screenshot per viewport. (No real sync needed here — config gating returns 400 until Task 8 wires the key.)

- [ ] **Step 5: Commit (if any snapshot/docs artifacts were added)**

```bash
git add -A && git commit -m "test: verification sweep for Buffer publishing" || echo "nothing to commit"
```

---

## Task 8: Deploy + wire VPS + real E2E + checkmark v0.34.0

**Files:**
- Modify: `frontend/lib/version.ts`, `CHANGELOG.md`
- (Ops) VPS `.env`

- [ ] **Step 1: Bump version + changelog**

In `frontend/lib/version.ts` set the version to `0.34.0`. Prepend to `CHANGELOG.md`:

```markdown
## v0.34.0 — Real publishing via Buffer
- Connect IG/FB/TikTok channels through your Buffer account ("Sync from Buffer").
- Approved posts now publish for real via Buffer (Instagram as a Reel); Buffer post
  ids are stored. Simulated fallback retained when Buffer isn't configured.
```

- [ ] **Step 2: Commit + push + PR + merge**

```bash
git add frontend/lib/version.ts CHANGELOG.md
git commit -m "chore(release): v0.34.0 — publish via Buffer"
git push origin HEAD
```

Open a PR (`phase-social-buffer` → `main`), let the audits in Task 8.5 run, then merge.

- [ ] **Step 3: Wire the VPS env (do NOT commit secrets)**

On `ssh ender-vps`, in `/home/enderj/Black-Volt-Mobility/.env`, set:

```
BUFFER_API_KEY=<the owner's Buffer personal API key>
BUFFER_ORG_ID=6a36d65cfe97ad6ade6b8e0a
SOCIAL_PUBLISH_VIA_BUFFER=true
```

- [ ] **Step 4: Deploy**

```bash
ssh ender-vps "cd /home/enderj/Black-Volt-Mobility && git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend frontend"
```

- [ ] **Step 5: Real E2E**

Log in as admin → Social → **Accounts** → **Sync from Buffer** → Instagram shows **connected** `blackvoltmobility`. Generate a post → render the real video → approve (publish now) → confirm `external_ids.instagram` holds a Buffer post id and the post appears in the Buffer queue / publishes as a Reel.

- [ ] **Step 6: Memory checkmark**

Prepend a one-line v0.34.0 entry to the Black Volt section of MEMORY.md (publish-via-Buffer live; org id; gotcha: only IG connected in Buffer, FB/TikTok added in Buffer UI later).

---

## Task 8.5: Audits (run before merging Task 8's PR)

- [ ] **Step 1: Security review of the diff**

Invoke `/security-review` on the branch diff. Confirm: key never returned/logged, all new routes admin-gated + tenant-scoped, `_public_media_url` blocks SSRF/escape, prod-guard holds.

- [ ] **Step 2: Code review of the diff**

Invoke `/code-review` (high). Address findings via the receiving-code-review skill.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "fix: address review findings (Buffer publishing)" || echo "no fixes needed"
```

---

## Self-Review (completed by author)

- **Spec coverage:** adapter (T2) ✓, config+gating (T1) ✓, sync/connect (T3,T5,T6) ✓, real publish + IG Reel + shareNow/customScheduled (T4) ✓, security/host-validation (T3 `_public_media_url`, T5 gating) ✓, no migration (T7 alembic check) ✓, deploy+E2E+checkmark (T8) ✓, audits (T8.5) ✓. Deferred Inbox/analytics — intentionally not in any task, matches spec.
- **Placeholder scan:** none — every code/test step contains full code and exact commands.
- **Type consistency:** `_do_publish(db, row)` async with both callers awaited; `social_buffer.create_post(**kwargs)` signature identical in adapter, service call, and tests; `sync_buffer_channels(db, *, tenant_id)` consistent across service/API/tests; `syncBufferChannels()` name matches lib + component usage; i18n keys match between dictionaries and JSX `t()` calls.
