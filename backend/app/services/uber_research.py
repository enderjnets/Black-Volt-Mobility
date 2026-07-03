"""Competitive pricing research for events.

Estimates Uber Black / Black SUV fares from affluent Denver origins to an event venue,
compares them to our own quote, and recommends which origin zones to target ads on —
weighing our margin, area affluence, and how far the driver has to travel from base.

Live prices come from the ``pricing-scout`` container (Playwright over uber.com) when it's
configured and reachable; otherwise a published-rate formula is used. Either way the run
never raises — a keyless/blocked deployment still produces a full, useful table.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.models import Event
from app.services import booking, maps
from app.services.event_pricing import suggest_round_trip
from app.services.tenancy import owner_tenant_id

logger = logging.getLogger("blackvolt.events.research")

# Affluent / high-propensity origins for premium event transport around Denver.
# affluence 1-3 (3 = highest median home value / propensity to pay for Uber Black).
TARGET_ZONES: list[dict] = [
    {"key": "cherry_hills", "name": "Cherry Hills Village",
     "address": "Cherry Hills Village, CO", "lat": 39.6425, "lng": -104.9550, "affluence": 3},
    {"key": "greenwood_dtc", "name": "Greenwood Village / DTC",
     "address": "Greenwood Village, CO", "lat": 39.6172, "lng": -104.9508, "affluence": 3},
    {"key": "castle_pines", "name": "Castle Pines",
     "address": "Castle Pines, CO", "lat": 39.4680, "lng": -104.8961, "affluence": 3},
    {"key": "lone_tree", "name": "Lone Tree",
     "address": "Lone Tree, CO", "lat": 39.5316, "lng": -104.8860, "affluence": 2},
    {"key": "highlands_ranch", "name": "Highlands Ranch",
     "address": "Highlands Ranch, CO", "lat": 39.5539, "lng": -104.9689, "affluence": 2},
    {"key": "cherry_creek", "name": "Cherry Creek",
     "address": "Cherry Creek, Denver, CO", "lat": 39.7195, "lng": -104.9536, "affluence": 3},
    {"key": "wash_park", "name": "Washington Park",
     "address": "Washington Park, Denver, CO", "lat": 39.7005, "lng": -104.9700, "affluence": 2},
    {"key": "lodo", "name": "LoDo / Union Station",
     "address": "Union Station, Denver, CO", "lat": 39.7527, "lng": -105.0004, "affluence": 2},
    {"key": "boulder", "name": "Boulder",
     "address": "Boulder, CO", "lat": 40.0150, "lng": -105.2705, "affluence": 3},
    {"key": "golden", "name": "Golden",
     "address": "Golden, CO", "lat": 39.7555, "lng": -105.2211, "affluence": 2},
]


def _haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def estimate_uber_formula(distance_mi: float, duration_min: float) -> dict:
    """Estimate one-way Uber Black + Black SUV fares from published Denver rates."""
    s = get_settings()
    black = s.UBER_BLACK_BASE + distance_mi * s.UBER_BLACK_PER_MILE
    black += duration_min * s.UBER_BLACK_PER_MINUTE + s.UBER_BLACK_BOOKING_FEE
    black = max(black, s.UBER_BLACK_MINIMUM)
    return {"black": round(black, 2), "black_suv": round(black * s.UBER_SUV_MULTIPLIER, 2)}


async def scrape_uber(origins: list[str], destination: str, when_iso: str | None) -> dict:
    """Ask the pricing-scout container for live Uber prices per origin. Returns a map
    ``origin -> {"black": float, "black_suv": float}`` (missing/failed origins omitted).
    Empty/unset URL → ``{}`` with zero network."""
    s = get_settings()
    if not s.PRICING_SCOUT_URL or not s.PRICING_SCOUT_SECRET:
        return {}
    payload = {"origins": origins, "destination": destination, "when": when_iso}
    body = json.dumps(payload).encode("utf-8")
    sig = base64.b64encode(
        hmac.new(s.PRICING_SCOUT_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=45.0) as http:
            resp = await http.post(
                s.PRICING_SCOUT_URL,
                content=body,
                headers={"Content-Type": "application/json", "x-bv-scout-signature": sig},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("prices", {}) if isinstance(data, dict) else {}
    except Exception as e:  # never let a blocked scrape break research
        logger.warning("pricing-scout unavailable, using formula: %s", e)
        return {}


def _score(*, margin: float, affluence: int, distance_from_base_mi: float) -> float:
    """Rank an origin for ad targeting. Margin advantage vs Uber dominates, then affluence,
    then how reasonable the trip is from base (far-but-lucrative like Boulder still scores
    via the upside baked into `margin`)."""
    # Normalize: margin advantage as a fraction (cap at 0.5), affluence 0-1, proximity 0-1.
    margin_norm = max(0.0, min(margin, 0.5)) / 0.5
    aff_norm = (affluence - 1) / 2
    prox_norm = max(0.0, 1 - distance_from_base_mi / 40.0)
    return round(0.45 * margin_norm + 0.35 * aff_norm + 0.20 * prox_norm, 4)


async def _recommendation_text(event: Event, rows: list[dict]) -> str:
    """A short Spanish ad-targeting recommendation. LLM via the Kimi→MiniMax chain, with a
    deterministic template fallback."""
    from app.services import llm, social

    ranked = sorted(rows, key=lambda r: r["score"], reverse=True)
    top = ranked[:3]
    summary = "; ".join(
        f"{r['name']}: nuestro RT ${r['our_round_trip']:.0f} vs Uber Black "
        f"${r['uber_black']:.0f} ({r['method']})" for r in top
    )
    prompt = (
        "Eres estratega de marketing de un servicio premium de transporte (categoría Uber "
        f"Black). Para el evento '{event.title}' en {event.venue_name}, estos son los datos "
        f"por zona de origen (ordenadas por atractivo): {summary}. Escribe 2 párrafos cortos "
        "en español recomendando en cuáles 1-2 zonas enfocar la publicidad y por qué "
        "(margen vs Uber, poder adquisitivo, distancia). Texto plano, sin viñetas."
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
            logger.warning("research recommendation provider %s failed: %s", model, e)
    if not top:
        return "Aún no hay datos suficientes para recomendar zonas."
    names = ", ".join(r["name"] for r in top[:2])
    return (
        f"Enfoca la publicidad en {names}: ofrecen el mejor margen frente a Uber Black y "
        f"mayor poder adquisitivo para {event.title}. Ajusta el gasto según la conversión."
    )


async def run_research(db: AsyncSession, *, event_id: int) -> dict | None:
    """Research every target zone for an event, persist and return the result."""
    s = get_settings()
    tid = await owner_tenant_id(db)
    event = await db.get(Event, event_id)
    if event is None or event.tenant_id != tid:
        return None
    venue = event.venue_address or event.venue_name
    when_iso = event.starts_at.isoformat() if event.starts_at else None

    live = await scrape_uber([z["address"] for z in TARGET_ZONES], venue, when_iso)

    rows: list[dict] = []
    for z in TARGET_ZONES:
        try:
            rr = await maps.route(z["address"], venue)
            uber_live = live.get(z["address"])
            if uber_live and uber_live.get("black"):
                black = float(uber_live["black"])
                suv = float(uber_live.get("black_suv") or black * s.UBER_SUV_MULTIPLIER)
                method = "live"
            else:
                est = estimate_uber_formula(rr.distance_miles, rr.duration_minutes)
                black, suv, method = est["black"], est["black_suv"], "estimate"
            # Uber round trip ≈ 2× one-way (Uber has no wait product).
            uber_rt = round(black * 2, 2)
            rt = await suggest_round_trip(db, event=event, origin=z["address"], uber_black=uber_rt)
            our_one_way = await booking.build_quote(
                db, tenant_id=tid, pickup=z["address"], dropoff=venue,
                scheduled_at=event.starts_at,
            )
            dist_base = round(
                _haversine_mi(s.EVENTS_BASE_LAT, s.EVENTS_BASE_LNG, z["lat"], z["lng"]), 1
            )
            margin = (uber_rt - rt["total"]) / uber_rt if uber_rt else 0.0
            rows.append({
                "key": z["key"], "name": z["name"], "affluence": z["affluence"],
                "our_one_way": round(our_one_way["total"], 2),
                "our_round_trip": rt["total"],
                "uber_black": black, "uber_black_suv": suv, "uber_round_trip": uber_rt,
                "method": method, "distance_from_base_mi": dist_base,
                "margin_pct": round(margin * 100, 1),
                "score": _score(margin=margin, affluence=z["affluence"],
                                distance_from_base_mi=dist_base),
            })
        except Exception as e:
            logger.warning("research zone %s failed: %s", z["key"], e)

    rows.sort(key=lambda r: r["score"], reverse=True)
    recommendation = await _recommendation_text(event, rows)
    result = {
        "zones": rows,
        "recommendation": recommendation,
        "method": "live" if live else "estimate",
        "venue": venue,
    }
    event.pricing_research = result
    flag_modified(event, "pricing_research")
    await db.commit()
    return result
