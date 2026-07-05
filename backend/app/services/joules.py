"""Joules — the public-site AI assistant.

Builds the system prompt (brand facts + LIVE zone prices from the tenant's
RateConfig + policies + the signed-in passenger's upcoming rides + Denver time)
and runs the Kimi→MiniMax chat chain (via ``llm.providers`` / ``llm.chat_complete``).
The model is instructed to answer READ-ONLY (direct users to /book and /trips) and
to prefix a reply with ``[ESCALATE]`` when it should hand off to a human; the
caller strips that marker and fires the owner-notification email. If every
provider fails, ``reply`` degrades to a bilingual hand-off message that itself
escalates — Joules never returns a raw error to a passenger.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, RateConfig, Ride, RideStatus, Tenant
from app.services import llm, zones

HISTORY_WINDOW = 12  # messages (≈6 turns) sent to the model — cost control
MAX_TOKENS = 500
MAX_MESSAGE_CHARS = 1000
ESCALATE_MARKER = "[ESCALATE]"

_DENVER_TZ = ZoneInfo("America/Denver")

# Rides that are worth surfacing to the passenger (upcoming / active).
_ACTIVE_STATUSES = (
    RideStatus.REQUESTED,
    RideStatus.QUOTED,
    RideStatus.CONFIRMED,
    RideStatus.ASSIGNED,
    RideStatus.EN_ROUTE,
)


def _fallback(lang: str | None) -> str:
    if (lang or "").lower().startswith("es"):
        return (
            "Estoy teniendo problemas para responder en este momento. Ya avisé a "
            "Ender y te contactará en breve. También puedes reservar en "
            "blackvoltmobility.com/book."
        )
    return (
        "I'm having trouble responding right now. I've let Ender know and he'll "
        "reach out shortly. You can also book at blackvoltmobility.com/book."
    )


async def _load_rate(db: AsyncSession, tenant_id: int) -> RateConfig | None:
    return (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()


def _effective_zone_prices(rc: RateConfig | None) -> dict[str, float]:
    """The same merge the public /rate-config endpoint returns: code defaults
    overlaid with the tenant's saved deviations."""
    merged = dict(zones.DEFAULT_ZONE_PRICES)
    if rc and rc.zone_prices:
        for k, v in rc.zone_prices.items():
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                continue
    return merged


def _pricing_block(rc: RateConfig | None) -> str:
    prices = _effective_zone_prices(rc)
    lines = ["Flat zone prices (one-way, USD, all-in — no surge on flat zones):"]
    for d in zones.ZONE_DESCRIPTORS:
        amount = prices.get(d["key"], d["default_flat"])
        lines.append(f"- {d['name']}: ${round(amount)}")
    if rc:
        lines.append(
            f"Out-of-zone rides are metered: ${round(rc.base)} base + "
            f"${rc.per_mile}/mi, ${round(rc.minimum)} minimum."
        )
        if rc.peak_enabled:
            lines.append(
                f"Peak hours apply a x{rc.peak_multiplier} multiplier to metered "
                "fares only (never to flat zones)."
            )
    return "\n".join(lines)


def _serialize_rides(rides: list[Ride], tenant: Tenant | None) -> str:
    """Compact list of the passenger's upcoming/active rides (max 3), Denver time.
    Driver contact is only exposed once the ride is confirmed/assigned."""
    active = [r for r in rides if r.status in _ACTIVE_STATUSES]
    active.sort(key=lambda r: r.scheduled_at or dt.datetime.max.replace(tzinfo=dt.UTC))
    if not active:
        return "The passenger has no upcoming rides on file."
    driver_phone = (tenant.phone if tenant else None) or None
    out = ["The passenger's upcoming rides:"]
    for r in active[:3]:
        when = "time TBD"
        if r.scheduled_at:
            local = r.scheduled_at.astimezone(_DENVER_TZ)
            when = local.strftime("%a %b %-d, %-I:%M %p") + " Denver time"
        line = (
            f"- Ride #{r.id}: {r.status.value}, {r.pickup_text or '?'} → "
            f"{r.dropoff_text or '?'}, {when}"
        )
        if r.flight_number:
            line += f", flight {r.flight_number}"
        if r.fare_total:
            line += f", ${round(float(r.fare_total))}"
        active_with_driver = r.status in (
            RideStatus.CONFIRMED,
            RideStatus.ASSIGNED,
            RideStatus.EN_ROUTE,
        )
        if active_with_driver and driver_phone:
            line += f" (driver contact: {driver_phone})"
        out.append(line)
    return "\n".join(out)


async def build_system_prompt(
    db: AsyncSession,
    *,
    tenant: Tenant | None,
    client: Client | None,
    rides: list[Ride],
    rc: RateConfig | None,
    lang_hint: str | None,
) -> str:
    brand_name = (tenant.name if tenant else None) or "Black Volt Mobility"
    vehicle = (getattr(tenant, "vehicle", None) if tenant else None) or "Kia EV9"
    city = (getattr(tenant, "city", None) if tenant else None) or "Denver / Aurora, Colorado"
    now_local = dt.datetime.now(_DENVER_TZ)
    passenger_name = (client.first_name if client else None) or "there"

    lang_line = (
        "The passenger's UI language is Spanish — reply in Spanish."
        if (lang_hint or "").lower().startswith("es")
        else "Reply in the passenger's language (English or Spanish); default English."
    )

    return f"""You are Joules, the AI assistant for {brand_name}, a premium electric \
chauffeur service ({vehicle}) in {city}. Voice: calm, precise, premium, concise \
— 1 to 3 short sentences per reply. No emoji, no markdown, no bullet lists.

Service: private door-to-door rides across the Denver metro, DEN airport transfers \
both ways, and mountain transfers (Vail, Breckenridge, Aspen). Silent, spacious, \
always on time. Book at blackvoltmobility.com/book; manage trips at \
blackvoltmobility.com/trips.

{_pricing_block(rc)}

Policies: fixed upfront pricing, no surge on flat zones. Payment by card via Square. \
Cancellations 24h or more before pickup get a full refund; under 24h the driver may \
keep up to a 30% fee. You are the flat/quoted price authority — never invent prices, \
features, or availability beyond the facts above.

The passenger you're chatting with is {passenger_name}.
{_serialize_rides(rides, tenant)}

Current date/time: {now_local.strftime('%A, %B %-d %Y, %-I:%M %p')} Denver time.

Rules:
- You are READ-ONLY: you cannot book, change, cancel, or price-quote a specific new \
trip. For anything actionable, direct the passenger to blackvoltmobility.com/book \
(new ride) or /trips (existing ride).
- Answer only from the facts above. If you don't know, say so.
- {lang_line}
- If the passenger asks to speak with a person, is upset, or you cannot help, begin \
your reply with {ESCALATE_MARKER} (exact text) followed by a brief message telling \
them Ender will reach out shortly. Never show the marker's brackets as part of a \
normal answer.
"""


async def reply(
    db: AsyncSession,
    *,
    tenant: Tenant | None,
    client: Client | None,
    history: list[dict],
    user_text: str,
    lang_hint: str | None,
) -> tuple[str, bool]:
    """Return ``(assistant_text, escalated)``. ``history`` is prior turns as
    ``[{"role": "user"|"assistant", "content": str}]`` (already trimmed to the
    window, excluding the just-received ``user_text`` which is appended here)."""
    tenant_id = tenant.id if tenant else None
    rides: list[Ride] = []
    if client is not None and tenant_id is not None:
        rides = list(
            (
                await db.execute(
                    select(Ride).where(
                        Ride.tenant_id == tenant_id, Ride.client_id == client.id
                    )
                )
            )
            .scalars()
            .all()
        )
    rc = await _load_rate(db, tenant_id) if tenant_id is not None else None
    system = await build_system_prompt(
        db, tenant=tenant, client=client, rides=rides, rc=rc, lang_hint=lang_hint
    )
    messages = [*history[-HISTORY_WINDOW:], {"role": "user", "content": user_text}]

    text: str | None = None
    for model, base_url, api_key in llm.providers():
        try:
            text = await llm.chat_complete(
                messages=messages,
                system=system,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=MAX_TOKENS,
            )
            break
        except llm.LLMError:
            continue
    if not text:
        return _fallback(lang_hint), True

    escalated = ESCALATE_MARKER in text
    if escalated:
        text = text.replace(ESCALATE_MARKER, "").strip()
        if not text:
            text = _fallback(lang_hint)
    return text, escalated
