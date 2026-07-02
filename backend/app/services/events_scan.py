"""Daily scanner: SeatGeek (base) + Ticketmaster (enrichment/source) → suggestions.

`run_scan` pulls upcoming Denver-metro events, keeps the ones at watchlist venues or
above a popularity bar, dedups across sources, ranks by distance to the driver base,
and upserts into `event_suggestions`. It never touches suggestions the admin already
approved or dismissed. All external calls fail soft: a missing key or a network error
leaves the existing suggestions untouched (stale-but-present beats empty).
"""
from __future__ import annotations

import datetime as dt
import logging
import math

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import EventSuggestion
from app.services.venue_profiles import match_venue_key

logger = logging.getLogger("blackvolt.events.scan")

_SG_URL = "https://api.seatgeek.com/2/events"
_TM_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
_DENVER = (39.7392, -104.9903)  # downtown Denver, search center
_WINDOW_DAYS = 90


def _owner_tenant_id() -> int:
    return get_settings().OWNER_TENANT_ID or 1


def _haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8  # Earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _norm(s: str) -> str:
    """Lowercase, alnum-only, single-spaced — for fuzzy cross-source title matching."""
    return " ".join(
        "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in (s or "")).split()
    )


# ── SeatGeek ────────────────────────────────────────────────────────────────


async def _fetch_seatgeek() -> list[dict]:
    """Next-90-day events within 30 miles of downtown Denver. [] when key missing/error."""
    st = get_settings()
    if not st.SEATGEEK_CLIENT_ID:
        return []
    now = dt.datetime.now(dt.UTC)
    params = {
        "client_id": st.SEATGEEK_CLIENT_ID,
        "lat": _DENVER[0],
        "lon": _DENVER[1],
        "range": "30mi",
        "per_page": 100,
        "datetime_utc.gte": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "datetime_utc.lte": (now + dt.timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%S"),
        "sort": "score.desc",
    }
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for page in (1, 2, 3):
                r = await client.get(_SG_URL, params={**params, "page": page})
                r.raise_for_status()
                evs = r.json().get("events", [])
                out.extend(evs)
                if len(evs) < 100:
                    break
    except Exception as e:
        logger.warning("SeatGeek fetch failed: %s", e)
        return []
    return out


def _parse_seatgeek(ev: dict) -> dict | None:
    """SeatGeek event → suggestion field dict (None = unparseable)."""
    try:
        venue = ev.get("venue") or {}
        loc = venue.get("location") or {}
        when = dt.datetime.strptime(ev["datetime_utc"], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=dt.UTC
        )
        perfs = ev.get("performers") or []
        image = next((p.get("image") for p in perfs if p.get("image")), None)
        addr = ", ".join(x for x in (venue.get("address"), venue.get("extended_address")) if x)
        venue_name = (venue.get("name") or "Unknown venue")[:160]
        return {
            "source": "seatgeek",
            "source_id": str(ev["id"]),
            "title": (ev.get("title") or "")[:200] or "Untitled event",
            "performer": (perfs[0].get("name") if perfs else None),
            "venue_name": venue_name,
            "venue_key": match_venue_key(venue_name),
            "venue_address": (addr[:240] or None),
            "venue_lat": loc.get("lat"),
            "venue_lng": loc.get("lon"),
            "starts_at": when,
            "score": ev.get("score"),
            "image_url": image,
            "event_url": ev.get("url"),
            "raw": {"seatgeek": ev},
        }
    except Exception:
        return None


# ── Ticketmaster (real impl lives here; T5 fleshes out _fetch/_enrich) ────────


async def _fetch_ticketmaster() -> list[dict]:
    """Discovery API events near Denver → parsed suggestion dicts. [] when key missing/error."""
    st = get_settings()
    if not st.TICKETMASTER_API_KEY:
        return []
    now = dt.datetime.now(dt.UTC)
    params = {
        "apikey": st.TICKETMASTER_API_KEY,
        "geoPoint": "9xj64",  # precision-5 geohash of downtown Denver (latlong is deprecated)
        "radius": "30",
        "unit": "miles",
        "size": "100",
        "sort": "date,asc",
        "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": (now + dt.timedelta(days=_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for page in (0, 1, 2):  # size*page must stay < 1000
                r = await client.get(_TM_URL, params={**params, "page": str(page)})
                r.raise_for_status()
                evs = ((r.json().get("_embedded") or {}).get("events")) or []
                out.extend(p for e in evs if (p := _parse_ticketmaster(e)))
                if len(evs) < 100:
                    break
    except Exception as e:
        logger.warning("Ticketmaster fetch failed: %s", e)
        return []
    return out


def _tm_best_image(images: list[dict]) -> str | None:
    """Widest real (non-fallback) 16:9 image; else widest of any ratio; else None."""
    if not images:
        return None
    real = [i for i in images if not i.get("fallback")]
    pool = real or images
    wide = [i for i in pool if i.get("ratio") == "16_9"] or pool
    best = max(wide, key=lambda i: i.get("width") or 0)
    return best.get("url")


def _parse_ticketmaster(ev: dict) -> dict | None:
    try:
        start = ((ev.get("dates") or {}).get("start") or {}).get("dateTime")
        if not start:
            return None
        when = dt.datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
        venues = ((ev.get("_embedded") or {}).get("venues")) or []
        venue = venues[0] if venues else {}
        vloc = venue.get("location") or {}
        vname = (venue.get("name") or "Unknown venue")[:160]
        addr_line = ((venue.get("address") or {}).get("line1"))
        city = ((venue.get("city") or {}).get("name"))
        state = ((venue.get("state") or {}).get("stateCode"))
        addr = ", ".join(x for x in (addr_line, city, state) if x)
        lat = vloc.get("latitude")
        lng = vloc.get("longitude")
        return {
            "source": "ticketmaster",
            "source_id": str(ev["id"]),
            "title": (ev.get("name") or "")[:200] or "Untitled event",
            "performer": (ev.get("name") or None),
            "venue_name": vname,
            "venue_key": match_venue_key(vname),
            "venue_address": (addr[:240] or None),
            "venue_lat": (float(lat) if lat else None),
            "venue_lng": (float(lng) if lng else None),
            "starts_at": when,
            "score": None,  # TM has no popularity score
            "image_url": _tm_best_image(ev.get("images") or []),
            "event_url": ev.get("url"),
            "raw": {"ticketmaster": ev},
        }
    except Exception:
        return None


async def _enrich_ticketmaster(items: list[dict]) -> list[dict]:
    """Merge Ticketmaster data into the SeatGeek-derived list.

    - A TM event matching a kept item (same normalized title + same UTC date) *enriches*
      it: official `event_url`, a better 16:9 image, and the TM payload in `raw`.
    - A TM event at a **watchlist venue** with no counterpart is *added* as its own
      suggestion (so the module is useful before the SeatGeek key exists).
    Any error returns `items` unchanged.
    """
    try:
        tm = await _fetch_ticketmaster()
        if not tm:
            return items
        index: dict[tuple[str, dt.date], dict] = {
            (_norm(it["title"]), it["starts_at"].date()): it for it in items
        }
        extra: list[dict] = []
        for t in tm:
            key = (_norm(t["title"]), t["starts_at"].date())
            match = index.get(key)
            if match is not None:
                if t.get("event_url"):
                    match["event_url"] = t["event_url"]
                if t.get("image_url"):
                    match["image_url"] = t["image_url"]
                match.setdefault("raw", {})["ticketmaster"] = t["raw"].get("ticketmaster")
            elif t["venue_key"]:  # TM-only, but at a watchlist venue → add it
                extra.append(t)
                index[key] = t
        return items + extra
    except Exception as e:
        logger.warning("Ticketmaster enrichment failed: %s", e)
        return items


# ── Orchestration ─────────────────────────────────────────────────────────────


def _keep(item: dict) -> bool:
    return bool(item["venue_key"]) or (item["score"] or 0) >= get_settings().EVENTS_MIN_SCORE


async def run_scan(db: AsyncSession) -> dict:
    """Fetch, filter, dedup, rank and upsert event suggestions. Returns counters."""
    st = get_settings()
    tid = _owner_tenant_id()
    raw = await _fetch_seatgeek()
    items = [p for e in raw if (p := _parse_seatgeek(e))]
    kept = [i for i in items if _keep(i)]
    kept = await _enrich_ticketmaster(kept)

    created = updated = 0
    for it in kept:
        if it.get("venue_lat") and it.get("venue_lng"):
            it["distance_mi"] = round(
                _haversine_mi(st.EVENTS_BASE_LAT, st.EVENTS_BASE_LNG,
                              it["venue_lat"], it["venue_lng"]),
                1,
            )
        row = (
            await db.execute(
                select(EventSuggestion).where(
                    EventSuggestion.tenant_id == tid,
                    EventSuggestion.source == it["source"],
                    EventSuggestion.source_id == it["source_id"],
                )
            )
        ).scalar_one_or_none()
        if row is None:
            # Cross-source fuzzy dedup: same date + venue + normalized title → skip.
            same = (
                await db.execute(
                    select(EventSuggestion).where(
                        EventSuggestion.tenant_id == tid,
                        EventSuggestion.starts_at == it["starts_at"],
                        EventSuggestion.venue_name == it["venue_name"],
                    )
                )
            ).scalars().all()
            if any(_norm(d.title) == _norm(it["title"]) for d in same):
                continue
            db.add(EventSuggestion(tenant_id=tid, **it))
            created += 1
        elif row.status == "suggested":  # never disturb approved/dismissed rows
            for k in (
                "title", "performer", "starts_at", "score", "image_url",
                "event_url", "venue_address", "distance_mi", "raw",
            ):
                if it.get(k) is not None:
                    setattr(row, k, it[k])
            updated += 1

    pruned = (
        await db.execute(
            delete(EventSuggestion).where(
                EventSuggestion.tenant_id == tid,
                EventSuggestion.status == "suggested",
                EventSuggestion.starts_at < dt.datetime.now(dt.UTC),
            )
        )
    ).rowcount or 0

    await db.commit()
    result = {
        "fetched": len(raw),
        "kept": len(kept),
        "created": created,
        "updated": updated,
        "pruned": pruned,
    }
    logger.info("events scan complete: %s", result)
    return result
