"""Featured-events service: approval pipeline + admin/public queries.

Approving a scanner suggestion creates a published `Event` (instant public landing),
downloads the hero image, asks the LLM for an "about the show" blurb, and spawns two
social-post drafts (one video, one photo) through the existing social engine so they
flow through the normal approve/edit/regenerate/publish path.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
import re
import socket
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, EventSuggestion, RateConfig
from app.services import event_pricing, llm, maps, social
from app.services.tenancy import owner_tenant_id
from app.services.venue_profiles import get_profile
from app.services.zones import DEFAULT_ZONE_PRICES

logger = logging.getLogger("blackvolt.events")

_ARCHIVE_GRACE = dt.timedelta(hours=6)  # keep a landing live a bit past showtime
_DENVER_TZ = ZoneInfo("America/Denver")
# Single source of truth: the metered engine's flat Denver-metro fare (owner-editable
# default), not a magic number. Events fall in the denver_metro zone.
FLAT_PRICE = int(DEFAULT_ZONE_PRICES.get("denver_metro", 110))


async def live_flat_price(db: AsyncSession, tenant_id: int | None = None) -> float:
    """Effective DEN/metro flat for the owner tenant — the tenant's Rates override wins
    over the code default, exactly like quotes (the owner tunes fares live in the
    dashboard, so anything published must read the same source)."""
    tid = tenant_id if tenant_id is not None else await owner_tenant_id(db)
    rc = (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == tid))
    ).scalar_one_or_none()
    prices = (rc.zone_prices or {}) if rc else {}
    try:
        return float(prices.get("denver_metro", FLAT_PRICE))
    except (TypeError, ValueError):
        return float(FLAT_PRICE)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _local(when: dt.datetime) -> dt.datetime:
    """A UTC event time rendered in Denver local time (for human-facing copy)."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return when.astimezone(_DENVER_TZ)


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
        "event_fee": ev.event_fee,
        "night_fee": ev.night_fee,
        "night_cutoff": ev.night_cutoff,
        "wait_fee_per_hour": ev.wait_fee_per_hour,
        "est_duration_hours": ev.est_duration_hours,
        "round_trip_price": ev.round_trip_price,
        "pricing_research": ev.pricing_research,
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


def _is_safe_public_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves to public IPs.

    Defense-in-depth against SSRF: the image URL comes from the events API, but we
    never fetch file://, localhost, cloud-metadata (169.254.169.254), or private/
    reserved ranges even if a source is compromised.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 0, proto=socket.IPPROTO_TCP)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


async def _download_image(url: str) -> tuple[bytes, str] | None:
    """Fetch a remote event image; sniff/normalize it. None on any error.

    SSRF guard: redirects are followed manually and EVERY hop (including the initial
    URL) is validated to a public http(s) host BEFORE the request is issued, so an
    attacker cannot bounce us through a public host into an internal one. The bytes must
    sniff as a real image or they are discarded.
    """
    if not _is_safe_public_url(url):
        logger.warning("event hero URL rejected (unsafe/non-public): %s", url)
        return None
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            current = url
            for _ in range(4):  # initial request + up to 3 redirects
                r = await client.get(current)
                if r.is_redirect:
                    loc = r.headers.get("location")
                    if not loc:
                        return None
                    nxt = str(httpx.URL(current).join(loc))
                    if not _is_safe_public_url(nxt):  # validate BEFORE following
                        logger.warning("event hero redirect rejected: %s", nxt)
                        return None
                    current = nxt
                    continue
                r.raise_for_status()
                sniffed = social._sniff_image(r.content)
                if sniffed is None:
                    return None
                return r.content, sniffed[0]
            logger.warning("event hero too many redirects: %s", url)
            return None
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


async def _about_text(sug: EventSuggestion, flat: float | None = None) -> str:
    prompt = (
        "Write 2 short paragraphs (max 120 words total) for a premium ride service's "
        f"event page about: {sug.title} at {sug.venue_name} on {_local(sug.starts_at):%B %d, %Y}. "
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
        title=sug.title, venue=sug.venue_name,
        date=f"{_local(sug.starts_at):%B %d, %Y}", price=round(flat) if flat else FLAT_PRICE
    )


_DURATION_MIN = 1.5
_DURATION_MAX = 6.0
_DURATION_FALLBACK = 3.0


async def _estimate_duration_hours(sug: EventSuggestion) -> float:
    """Ask the LLM how long THIS specific show typically runs (incl. opener), so the driver's
    wait time (`est_duration_hours`) is pre-filled from research, not a flat default.

    Best-effort: any failure or unparseable answer falls back to 3.0h. Clamped to a sane range.
    The driver can still edit it in the pricing panel.
    """
    kind = "concert"
    raw = sug.raw if isinstance(sug.raw, dict) else {}
    taxonomy = " ".join(
        str(v) for v in (raw.get("type"), raw.get("taxonomy"), raw.get("genre")) if v
    )
    prompt = (
        "You estimate how long a live event runs door-to-door for a ride service planning driver "
        "wait time. Consider the specific act and venue. Reply with ONLY a single number of hours "
        "(e.g. 2.5), no words.\n"
        f"Event: {sug.title}\nPerformer: {sug.performer or 'n/a'}\nVenue: {sug.venue_name}\n"
        f"Type: {taxonomy or kind}\n"
        "Typical total time from doors to end including opener/half-time."
    )
    for model, base_url, api_key in social._providers():
        try:
            text = (
                await llm.text_complete(
                    prompt=prompt, model=model, base_url=base_url, api_key=api_key, max_tokens=16
                )
            ).strip()
            m = re.search(r"\d+(?:\.\d+)?", text)
            if m:
                val = float(m.group(0))
                return max(_DURATION_MIN, min(_DURATION_MAX, round(val, 1)))
        except Exception as e:  # noqa: BLE001 — never block approval on the estimate
            logger.warning("event duration estimate provider %s failed: %s", model, e)
    return _DURATION_FALLBACK


def _event_topic(ev: Event, flat: float) -> str:
    return (
        f"Event ride: {ev.title} at {ev.venue_name} on {_local(ev.starts_at):%B %d} — flat "
        f"${round(flat)} each way, no surge, door-to-door and prepaid. Book at "
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
        db, tenant_id=ev.tenant_id, topic=_event_topic(ev, await live_flat_price(db, ev.tenant_id)),
        angle=None, lang="en",
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
        f"-{_local(sug.starts_at):%Y}"
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
        est_duration_hours=await _estimate_duration_hours(sug),
        about_text=await _about_text(sug, await live_flat_price(db, sug.tenant_id)),
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


_PRICING_NUMERIC = {
    "event_fee",
    "night_fee",
    "wait_fee_per_hour",
    "est_duration_hours",
    "round_trip_price",
}
_EDITABLE = {
    "title",
    "about_text",
    "tips_text",
    "status",
    "venue_address",
    "night_cutoff",
    *_PRICING_NUMERIC,
}
_ALLOWED_STATUS = {"draft", "published", "archived"}
_CUTOFF_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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
        if key in _PRICING_NUMERIC:
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if val < 0:
                continue
        if key == "night_cutoff" and not _CUTOFF_RE.match(str(val)):
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
    tid = await owner_tenant_id(db)
    rows = (
        await db.execute(
            select(Event).where(
                Event.tenant_id == tid,
                Event.status == "published",
                Event.starts_at < cutoff,
            )
        )
    ).scalars().all()
    for ev in rows:
        ev.status = "archived"
    if rows:
        await db.commit()
    return len(rows)


# ── public (landing page) ─────────────────────────────────────────────────────


async def list_public_events(db: AsyncSession) -> list[dict]:
    tid = await owner_tenant_id(db)
    rows = (
        await db.execute(
            select(Event)
            .where(
                Event.tenant_id == tid,
                Event.status == "published",
                Event.starts_at >= _now(),
            )
            .order_by(Event.starts_at.asc())
        )
    ).scalars().all()
    return [_event_dict(r) for r in rows]


async def get_public_event(db: AsyncSession, *, slug: str) -> dict | None:
    tid = await owner_tenant_id(db)
    ev = (
        await db.execute(
            select(Event).where(Event.tenant_id == tid, Event.slug == slug)
        )
    ).scalar_one_or_none()
    if ev is None or ev.status == "draft":
        return None
    data = _event_dict(ev)
    # Internal pricing/strategy fields must not leak to the public landing.
    for k in ("pricing_research", "night_fee", "night_cutoff", "wait_fee_per_hour",
              "est_duration_hours"):
        data.pop(k, None)
    data["venue_profile"] = get_profile(ev.venue_key)
    # "passed" only once the landing is actually retired (archive grace window), so the
    # post-show pickup CTA stays live during and just after the show.
    data["passed"] = ev.status == "archived" or ev.starts_at < _now() - _ARCHIVE_GRACE
    flat = await live_flat_price(db, tid)
    data["flat_price"] = flat
    data["one_way_from"] = round(flat + (ev.event_fee or 0), 2)
    data["round_trip_price"] = _public_round_trip_price(ev, flat)
    data["return_at"] = event_pricing.default_return_dt(ev).isoformat()
    return data


def _public_round_trip_price(ev: Event, flat: float | None = None) -> float:
    """Effective published round-trip price: admin override, else a metro-origin estimate
    (both legs at the flat zone fare, so it's origin-independent). No maps calls."""
    if ev.round_trip_price is not None:
        return round(float(ev.round_trip_price), 2)
    ret_dt = event_pricing.default_return_dt(ev)
    total = 2 * (flat if flat is not None else FLAT_PRICE) + float(ev.event_fee or 0)
    total += float(ev.wait_fee_per_hour or 0) * float(ev.est_duration_hours or 3)
    if ev.night_fee and event_pricing._after_cutoff(ret_dt, ev.night_cutoff):
        total += float(ev.night_fee)
    return round(total, 2)


# Arrive this many minutes before showtime (parking, security, seats — owner decision).
ARRIVAL_BUFFER_MIN = 30


async def pickup_suggestion(db: AsyncSession, *, slug: str, origin: str) -> dict | None:
    """Suggest an optimal outbound pickup time (and return info) for a rider's address.

    Uses traffic-aware travel time so the rider reaches the venue ~30 min before showtime.
    Public/landing helper — returns only times/minutes, never internal pricing. None if the
    event is unknown or still a draft.
    """
    tid = await owner_tenant_id(db)
    ev = (
        await db.execute(select(Event).where(Event.tenant_id == tid, Event.slug == slug))
    ).scalar_one_or_none()
    if ev is None or ev.status == "draft":
        return None

    venue = ev.venue_address or ev.venue_name
    starts = ev.starts_at if ev.starts_at.tzinfo else ev.starts_at.replace(tzinfo=dt.UTC)
    arrive_by = starts - dt.timedelta(minutes=ARRIVAL_BUFFER_MIN)
    # Anchor the traffic estimate near the trip itself (an hour before the show).
    out = await maps.route(origin, venue, depart_at=starts - dt.timedelta(hours=1))
    pickup_at = arrive_by - dt.timedelta(minutes=out.duration_minutes)

    return_pickup_at = event_pricing.default_return_dt(ev)
    try:
        home = await maps.route(venue, origin, depart_at=return_pickup_at)
        drop_home_minutes = round(home.duration_minutes)
        traffic_aware = bool(out.traffic_aware and home.traffic_aware)
    except maps.MapsError:  # return leg is informational; never fail the suggestion on it
        drop_home_minutes = None
        traffic_aware = bool(out.traffic_aware)

    return {
        "pickup_at": pickup_at.isoformat(),
        "arrive_by": arrive_by.isoformat(),
        "travel_minutes_out": round(out.duration_minutes),
        "return_pickup_at": return_pickup_at.isoformat(),
        "drop_home_minutes": drop_home_minutes,
        "traffic_aware": traffic_aware,
    }
