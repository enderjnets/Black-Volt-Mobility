"""Featured-events service: approval pipeline + admin/public queries.

Approving a scanner suggestion creates a published `Event` (instant public landing),
downloads the hero image, asks the LLM for an "about the show" blurb, and spawns two
social-post drafts (one video, one photo) through the existing social engine so they
flow through the normal approve/edit/regenerate/publish path.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, EventSuggestion
from app.services import llm, social
from app.services.venue_profiles import get_profile

logger = logging.getLogger("blackvolt.events")

_ARCHIVE_GRACE = dt.timedelta(hours=6)  # keep a landing live a bit past showtime
FLAT_PRICE = 120


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ── serialization ─────────────────────────────────────────────────────────────


def _event_dict(ev: Event) -> dict:
    return {
        "id": ev.id,
        "slug": ev.slug,
        "title": ev.title,
        "performer": ev.performer,
        "venue_key": ev.venue_key,
        "venue_name": ev.venue_name,
        "venue_address": ev.venue_address,
        "starts_at": ev.starts_at,
        "doors_at": ev.doors_at,
        "hero_path": ev.hero_path,
        "about_text": ev.about_text,
        "tips_text": ev.tips_text,
        "status": ev.status,
        "event_url": ev.event_url,
    }


def _suggestion_dict(s: EventSuggestion) -> dict:
    return {
        "id": s.id,
        "source": s.source,
        "title": s.title,
        "performer": s.performer,
        "venue_name": s.venue_name,
        "venue_key": s.venue_key,
        "venue_address": s.venue_address,
        "distance_mi": s.distance_mi,
        "starts_at": s.starts_at,
        "score": s.score,
        "image_url": s.image_url,
        "event_url": s.event_url,
        "status": s.status,
    }


# ── helpers ─────────────────────────────────────────────────────────────────


def _slugify(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in (s or ""))
    return "-".join(p for p in out.split("-") if p)[:70] or "event"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    slug, n = base, 1
    while (
        await db.execute(select(Event.id).where(Event.slug == slug))
    ).scalar_one_or_none() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


async def _download_image(url: str) -> tuple[bytes, str] | None:
    """Fetch a remote event image; sniff/normalize it. None on any error."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
        sniffed = social._sniff_image(r.content)
        if sniffed is None:
            return None
        return r.content, sniffed[0]
    except Exception as e:
        logger.warning("event hero download failed: %s", e)
        return None


def _write_hero(tenant_id: int, slug: str, raw: bytes, ext: str) -> str:
    """Persist the hero image under the tenant's events dir; return the rel path."""
    settings = get_settings()
    rel_dir = os.path.join("tenants", str(tenant_id), "events")
    abs_dir = os.path.join(settings.MEDIA_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    fname = f"{slug}-hero-{int(time.time() * 1000)}.{ext}"
    rel_path = os.path.join(rel_dir, fname)
    abs_path = os.path.join(settings.MEDIA_DIR, rel_path)
    tmp = abs_path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, abs_path)
    return rel_path


def _load_hero_bytes(ev: Event) -> bytes | None:
    if not ev.hero_path:
        return None
    abs_path = os.path.join(get_settings().MEDIA_DIR, ev.hero_path)
    try:
        with open(abs_path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


_ABOUT_FALLBACK = (
    "{title} takes over {venue} on {date}. Skip the parking chaos — your Black Volt "
    "driver drops you right at the door and picks you up after the show, a flat "
    "${price} each way with no surge pricing."
)


async def _about_text(sug: EventSuggestion) -> str:
    prompt = (
        "Write 2 short paragraphs (max 120 words total) for a premium ride service's "
        f"event page about: {sug.title} at {sug.venue_name} on {sug.starts_at:%B %d, %Y}. "
        "Paragraph 1: who's playing and why this show is a big deal. Paragraph 2: a "
        "practical rider tip (arrive early, book the ride ahead of time). Be factual, "
        "avoid hype adjectives, no hashtags, plain text only."
    )
    for model, base_url, api_key in social._providers():
        try:
            text = (
                await llm.text_complete(
                    prompt=prompt, model=model, base_url=base_url, api_key=api_key,
                    max_tokens=400,
                )
            ).strip()
            if len(text) > 40:
                return text
        except Exception as e:
            logger.warning("event about-text provider %s failed: %s", model, e)
    return _ABOUT_FALLBACK.format(
        title=sug.title, venue=sug.venue_name, date=f"{sug.starts_at:%B %d, %Y}", price=FLAT_PRICE
    )


def _event_topic(ev: Event) -> str:
    return (
        f"Event ride: {ev.title} at {ev.venue_name} on {ev.starts_at:%B %d} — flat "
        f"${FLAT_PRICE} each way, no surge, door-to-door and prepaid. Book at "
        f"https://blackvoltmobility.com/events/{ev.slug}"
    )


async def _spawn_post(
    db: AsyncSession, ev: Event, kind: str, hero: tuple[bytes, str] | None
) -> int:
    refs = None
    if kind == "image" and hero:
        saved = social.save_reference_image(ev.tenant_id, raw=hero[0])
        refs = [saved[0]] if saved else None
    out = await social.generate_and_create(
        db, tenant_id=ev.tenant_id, topic=_event_topic(ev), angle=None, lang="en",
        reference_paths=refs, media_kind=kind,
    )
    if out.get("status") == "draft":  # video, or image without a photo → kick the render
        await social.request_render(db, tenant_id=ev.tenant_id, post_id=out["id"])
    return out["id"]


# ── admin operations ──────────────────────────────────────────────────────────


async def list_suggestions(
    db: AsyncSession, *, tenant_id: int, venue_key: str | None = None
) -> list[dict]:
    q = select(EventSuggestion).where(
        EventSuggestion.tenant_id == tenant_id, EventSuggestion.status == "suggested"
    )
    if venue_key:
        q = q.where(EventSuggestion.venue_key == venue_key)
    q = q.order_by(EventSuggestion.starts_at.asc())
    rows = (await db.execute(q)).scalars().all()
    return [_suggestion_dict(r) for r in rows]


async def dismiss_suggestion(db: AsyncSession, *, tenant_id: int, suggestion_id: int) -> bool:
    sug = (
        await db.execute(
            select(EventSuggestion).where(
                EventSuggestion.id == suggestion_id,
                EventSuggestion.tenant_id == tenant_id,
                EventSuggestion.status == "suggested",
            )
        )
    ).scalar_one_or_none()
    if sug is None:
        return False
    sug.status = "dismissed"
    await db.commit()
    return True


async def approve_suggestion(
    db: AsyncSession, *, tenant_id: int, suggestion_id: int
) -> dict | None:
    sug = (
        await db.execute(
            select(EventSuggestion).where(
                EventSuggestion.id == suggestion_id,
                EventSuggestion.tenant_id == tenant_id,
                EventSuggestion.status == "suggested",
            )
        )
    ).scalar_one_or_none()
    if sug is None:
        return None

    hero = await _download_image(sug.image_url) if sug.image_url else None
    base = _slugify(
        f"{sug.performer or sug.title}-{(sug.venue_key or 'denver').replace('_', '-')}"
        f"-{sug.starts_at:%Y}"
    )
    slug = await _unique_slug(db, base)
    ev = Event(
        tenant_id=tenant_id,
        suggestion_id=sug.id,
        slug=slug,
        title=sug.title,
        performer=sug.performer,
        venue_key=sug.venue_key or "generic",
        venue_name=sug.venue_name,
        venue_address=sug.venue_address,
        starts_at=sug.starts_at,
        event_url=sug.event_url,
        status="published",
        about_text=await _about_text(sug),
    )
    if hero:
        try:
            ev.hero_path = _write_hero(tenant_id, slug, hero[0], hero[1])
        except OSError as e:
            logger.warning("failed to write event hero: %s", e)
    db.add(ev)
    sug.status = "approved"
    await db.commit()
    await db.refresh(ev)

    post_ids: list[int] = []
    posts_error: str | None = None
    for kind in ("video", "image"):
        try:
            post_ids.append(await _spawn_post(db, ev, kind, hero))
        except Exception as e:  # a post failure never blocks the (already live) landing
            logger.warning("event post (%s) failed: %s", kind, e)
            posts_error = str(e)
    return {**_event_dict(ev), "post_ids": post_ids, "posts_error": posts_error}


async def list_events(db: AsyncSession, *, tenant_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(Event)
            .where(Event.tenant_id == tenant_id)
            .order_by(Event.starts_at.asc())
        )
    ).scalars().all()
    return [_event_dict(r) for r in rows]


_EDITABLE = {"title", "about_text", "tips_text", "status", "venue_address"}
_ALLOWED_STATUS = {"draft", "published", "archived"}


async def update_event(
    db: AsyncSession, *, tenant_id: int, event_id: int, patch: dict
) -> dict | None:
    ev = (
        await db.execute(
            select(Event).where(Event.id == event_id, Event.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if ev is None:
        return None
    for key, val in patch.items():
        if key not in _EDITABLE or val is None:
            continue
        if key == "status" and val not in _ALLOWED_STATUS:
            continue
        setattr(ev, key, val)
    await db.commit()
    await db.refresh(ev)
    return _event_dict(ev)


async def generate_event_post(
    db: AsyncSession, *, tenant_id: int, event_id: int, kind: str
) -> dict:
    ev = (
        await db.execute(
            select(Event).where(Event.id == event_id, Event.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if ev is None:
        return {"error": "not_found"}
    kind = "image" if kind == "image" else "video"
    hero = None
    if kind == "image":
        raw = _load_hero_bytes(ev)
        if raw:
            sniffed = social._sniff_image(raw)
            if sniffed:
                hero = (raw, sniffed[0])
    post_id = await _spawn_post(db, ev, kind, hero)
    return {"post_id": post_id, "kind": kind}


async def archive_past_events(db: AsyncSession) -> int:
    cutoff = _now() - _ARCHIVE_GRACE
    rows = (
        await db.execute(
            select(Event).where(Event.status == "published", Event.starts_at < cutoff)
        )
    ).scalars().all()
    for ev in rows:
        ev.status = "archived"
    if rows:
        await db.commit()
    return len(rows)


# ── public (landing page) ─────────────────────────────────────────────────────


async def list_public_events(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(Event)
            .where(Event.status == "published", Event.starts_at >= _now())
            .order_by(Event.starts_at.asc())
        )
    ).scalars().all()
    return [_event_dict(r) for r in rows]


async def get_public_event(db: AsyncSession, *, slug: str) -> dict | None:
    ev = (
        await db.execute(select(Event).where(Event.slug == slug))
    ).scalar_one_or_none()
    if ev is None or ev.status == "draft":
        return None
    data = _event_dict(ev)
    data["venue_profile"] = get_profile(ev.venue_key)
    data["passed"] = ev.status == "archived" or ev.starts_at < _now()
    data["flat_price"] = FLAT_PRICE
    return data
