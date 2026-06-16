"""My Stats AI coach — one motivating, actionable nudge for the driver.

The numbers are ALWAYS deterministic: they come straight from the funnel model
(`funnel_math.coach_insight`) built on the driver's real logged activity and
earnings. The AI's only job is to phrase those exact numbers warmly; it can never
invent a figure, and the card still works (template wording) when the AI is off
or unconfigured.

Safety: only numeric/enumerated fields are ever sent to the LLM — never free OCR/
user text (platform period labels, currencies, notes) which arrive from uploaded
screenshots and could carry injected instructions. NEVER use an Anthropic OAuth
token here — Kimi/MiniMax only (CLAUDE.md anti-pattern #1).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services import funnel, llm, platform_stats
from app.services import funnel_math as fm

logger = logging.getLogger("blackvolt.coach")

_LOCALES = {"en", "es"}
_WEEKS_PER_MONTH = 4.345

# Localized phrase for the bottleneck stage (the lever with the most upside).
_STAGE_PHRASE = {
    "en": {
        "pitch": "pitching more of the people you talk to",
        "contact": "getting contact info after a pitch",
        "convert": "closing the contacts you make",
    },
    "es": {
        "pitch": "proponerle el servicio a más gente con la que hablas",
        "contact": "conseguir el contacto tras la propuesta",
        "convert": "cerrar a los contactos que consigues",
    },
}

_SYSTEM = (
    "You are a warm, sharp sales coach for a premium electric-chauffeur driver who "
    "grows the business by converting Uber/Lyft riders into private clients. "
    "You are given a JSON object of the driver's REAL stats and pre-computed "
    "figures. Write 2-3 short motivating sentences that restate EXACTLY those "
    "numbers and point at the single highest-impact lever. Rely ONLY on the JSON; "
    "never invent numbers, names, places, or facts; no markdown, no lists. "
    "Respond in {lang_name}."
)
_LANG_NAME = {"en": "English", "es": "Spanish"}


def _clamp_locale(locale: str | None) -> str:
    loc = (locale or "en").strip().lower()[:2]
    return loc if loc in _LOCALES else "en"


def _providers() -> list[tuple[str, str, str]]:
    """Ordered (model, base_url, api_key) triples: primary then fallback, skipping
    any provider whose key is unset. Empty when no text LLM is configured."""
    s = get_settings()
    by_name = {
        "kimi": (s.KIMI_MODEL, s.KIMI_BASE_URL, s.KIMI_API_KEY),
        "minimax": (s.MINIMAX_MODEL, s.MINIMAX_BASE_URL, s.MINIMAX_API_KEY),
    }
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name in (s.LLM_PRIMARY, s.LLM_FALLBACK):
        key = (name or "").strip().lower()
        if key in by_name and key not in seen:
            seen.add(key)
            triple = by_name[key]
            if triple[2]:  # has an api key
                out.append(triple)
    return out


def _r(v: float | None, d: int = 0) -> float | int:
    if v is None:
        return 0
    return int(round(v)) if d == 0 else round(v, d)


def _goal_target_clients(goal: dict, revenue_per_client: float) -> float | None:
    """A weekly client target derived from whichever goal the driver set, or None."""
    monthly = goal.get("target_monthly_clients")
    if monthly:
        return float(monthly) / _WEEKS_PER_MONTH
    weekly_rev = goal.get("target_weekly_revenue")
    if weekly_rev and revenue_per_client > 0:
        return float(weekly_rev) / revenue_per_client
    return None


def _platform_angle(plat: dict, overall_point: float, revenue_per_client: float) -> dict | None:
    """Deterministic 'convert K of your N platform trips to private ≈ $X' angle."""
    trips = int(plat.get("totals", {}).get("trips") or 0)
    if trips <= 0:
        return None
    k = round(trips * max(0.0, min(1.0, overall_point)))
    if k < 1:
        k = 1
    return {
        "trips": trips,
        "convert_k": k,
        "convert_revenue": _r(k * max(0.0, revenue_per_client)),
        "private_share": plat.get("comparison", {}).get("private_share"),
    }


def _template(insight: fm.CoachInsight, ctx: dict, locale: str) -> str:
    """The always-available localized message, built straight from the figures."""
    has_data = ctx["logged_days"] > 0 or ctx["totals_conversations"] > 0
    plat = ctx.get("platform")
    if not has_data and not plat:
        return (
            "Empieza a registrar tus conversaciones y propuestas diarias — con unos pocos "
            "registros te mostraré exactamente cuántos viajes al día necesitas para tu meta."
            if locale == "es"
            else "Start logging your daily conversations and pitches — a few entries and "
            "I'll show you exactly how many a day gets you to your goal."
        )

    sug = _r(insight.suggested_per_day)
    prob = _r(insight.prob_at_least_one * 100)
    clients = _r(insight.expected_clients, 1)
    rev = _r(insight.expected_revenue)
    stage = _STAGE_PHRASE[locale][insight.focus_stage]

    if locale == "es":
        parts = [
            f"Habla con {sug} personas al día y tienes ~{prob}% de probabilidad de conseguir "
            f"{clients} cliente(s) privado(s) nuevo(s)"
            + (f" (~${rev})" if insight.has_earnings else "")
            + " esta semana.",
            f"Tu mayor palanca ahora es {stage}.",
        ]
        if plat:
            parts.append(
                f"Registraste {plat['trips']} viajes de plataforma — convertir solo "
                f"{plat['convert_k']} a privado sumaría ~${plat['convert_revenue']}."
            )
    else:
        parts = [
            f"Talk to {sug} people a day and you've got a ~{prob}% shot at landing "
            f"{clients} new private client(s)"
            + (f" (~${rev})" if insight.has_earnings else "")
            + " this week.",
            f"Your biggest lever right now is {stage}.",
        ]
        if plat:
            parts.append(
                f"You logged {plat['trips']} platform trips — converting just "
                f"{plat['convert_k']} to private would add ~${plat['convert_revenue']}."
            )
    return " ".join(parts)


def _ai_context(insight: fm.CoachInsight, ctx: dict, locale: str) -> dict:
    """The numeric/enum-only payload the LLM is allowed to see (no free text)."""
    rates = ctx["rates"]
    payload = {
        "locale": locale,
        "current_per_day": _r(insight.current_per_day, 1),
        "suggested_per_day": _r(insight.suggested_per_day),
        "horizon_days": insight.horizon_days,
        "prob_at_least_one_pct": _r(insight.prob_at_least_one * 100),
        "expected_clients": _r(insight.expected_clients, 1),
        "expected_revenue": _r(insight.expected_revenue),
        "bottleneck_stage": insight.focus_stage,  # enum {pitch,contact,convert}
        "has_earnings": insight.has_earnings,
        "rates_pct": {
            "pitch": _r(rates["pitch"] * 100),
            "contact": _r(rates["contact"] * 100),
            "convert": _r(rates["convert"] * 100),
            "overall": _r(rates["overall"] * 100, 1),
        },
        "streak_days": ctx["streak"],
        "logged_days": ctx["logged_days"],
        "week_clients": _r(ctx["week_clients"], 1),
        "week_revenue": _r(ctx["week_revenue"]),
        "goal_weekly_revenue": (
            _r(ctx["goal_weekly_revenue"]) if ctx["goal_weekly_revenue"] else None
        ),
        "goal_monthly_clients": ctx["goal_monthly_clients"],
    }
    if ctx.get("platform"):
        p = ctx["platform"]
        share = p.get("private_share")
        payload["platform"] = {
            "trips": p["trips"],
            "convert_k": p["convert_k"],
            "convert_revenue": p["convert_revenue"],
            "private_share_pct": _r(share * 100) if share is not None else None,
        }
    return payload


async def _ai_message(ai_ctx: dict, locale: str) -> str | None:
    """Write the message with Kimi (primary) → MiniMax (fallback). None if every
    configured provider fails or none is configured."""
    providers = _providers()
    if not providers:
        return None
    system = _SYSTEM.format(lang_name=_LANG_NAME[locale])
    prompt = (
        "Driver stats (use these EXACT numbers, nothing else):\n"
        + json.dumps(ai_ctx, ensure_ascii=False)
    )
    for model, base_url, api_key in providers:
        try:
            return await llm.text_complete(
                prompt=prompt, system=system, model=model, base_url=base_url,
                api_key=api_key, max_tokens=400,
            )
        except Exception as e:  # try the next provider, then degrade to template
            logger.warning("coach LLM provider %s failed: %s", model, e)
    return None


# ── Redis daily cache (best-effort; any failure degrades to recompute) ─────────
def _seconds_to_eod() -> int:
    now = datetime.now(UTC)
    eod = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((eod - now).total_seconds()))


async def _cache_get(key: str) -> dict | None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            raw = await client.get(key)
        finally:
            await client.aclose()
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning("coach cache get failed: %s", e)
        return None


async def _cache_set(key: str, value: dict) -> None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            await client.set(key, json.dumps(value), ex=_seconds_to_eod())
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("coach cache set failed: %s", e)


async def recommend(
    db: AsyncSession, *, tenant_id: int, locale: str = "en", refresh: bool = False
) -> dict:
    """Build the coach card: deterministic insight + (cached) AI-written message,
    falling back to a localized template. Read-only; tenant-scoped."""
    locale = _clamp_locale(locale)
    summary = await funnel.summary(db, tenant_id=tenant_id)
    plat = await platform_stats.summary(db, tenant_id=tenant_id)

    rates = fm.funnel_rates(
        conversations=summary["totals"]["conversations"],
        pitches=summary["totals"]["pitches"],
        contacts=summary["totals"]["contacts"],
        clients=summary["totals"]["clients"],
    )
    revenue_per_client = summary["value_per_client"] or summary["avg_fare"] or 0.0
    goal = summary["goal"]
    insight = fm.coach_insight(
        rates=rates,
        conversations_per_day=summary["projection"]["pace_per_day"],
        working_days=goal["working_days_per_week"],
        revenue_per_client=revenue_per_client,
        target_clients=_goal_target_clients(goal, revenue_per_client),
    )

    ctx = {
        "totals_conversations": summary["totals"]["conversations"],
        "logged_days": summary["totals"]["logged_days"],
        "streak": summary["streak"],
        "week_clients": summary["week"]["clients"],
        "week_revenue": summary["week"]["revenue"],
        "goal_weekly_revenue": goal["target_weekly_revenue"],
        "goal_monthly_clients": goal["target_monthly_clients"],
        "rates": {
            "pitch": rates.pitch.point,
            "contact": rates.contact.point,
            "convert": rates.convert.point,
            "overall": rates.overall_point,
        },
        "platform": _platform_angle(plat, rates.overall_point, revenue_per_client),
    }

    ai_ctx = _ai_context(insight, ctx, locale)
    digest = hashlib.sha256(
        json.dumps(ai_ctx, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
    today = datetime.now(UTC).date().isoformat()
    cache_key = f"coach:{tenant_id}:{locale}:{today}:{digest}"

    insight_out = insight.dict()

    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "insight": insight_out}

    message = await _ai_message(ai_ctx, locale)
    source = "ai" if message else "template"
    if not message:
        message = _template(insight, ctx, locale)

    out = {
        "message": message,
        "source": source,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if source == "ai":  # only the (expensive) AI text is worth caching
        await _cache_set(cache_key, out)
    return {**out, "insight": insight_out}
