"""Fare engine. Pure functions over a RateConfig + route facts → a fare and a
line-item breakdown. No DB or network here, so it's trivially unit-testable.

Formula (matches the plan + dashboard Rates editor):

    metered  = base + miles*per_mile + minutes*per_minute
    floor    = airport_flat   (airport ride)   |   minimum   (otherwise)
    subtotal = MAX(metered, floor)
             + extra_stop_fee * extra_stops
             + group_surcharge        (when pax > group_threshold)
    peaked   = subtotal * peak_multiplier      (when peak applies)
    total    = peaked - loyalty_discount_pct%  (when client is loyalty)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings
from app.models.rate_config import RateConfig


@dataclass
class RouteFacts:
    distance_miles: float
    duration_minutes: float
    is_airport: bool = False
    pax: int | None = None
    extra_stops: int = 0
    scheduled_at: datetime | None = None
    is_peak: bool | None = None  # explicit override; else derived from scheduled_at
    is_loyalty: bool = False
    discount_pct: float | None = None


def is_peak_time(dt: datetime | None) -> bool:
    """Default peak window: Fri/Sat 22:00–05:00 (late-night weekend demand).
    A starting heuristic — drivers can refine the rule later."""
    if dt is None:
        return False
    late = dt.hour >= 22 or dt.hour < 5
    weekend_night = dt.weekday() in (4, 5)  # Fri, Sat
    return late and weekend_night


def _round(x: float) -> float:
    return round(x + 1e-9, 2)


def quote(rates: RateConfig, facts: RouteFacts) -> dict:
    """Return a fare breakdown dict. `total` is the charged amount; `lines` is an
    ordered list of {label, amount} for display + storage."""
    miles = max(0.0, facts.distance_miles or 0.0)
    minutes = max(0.0, facts.duration_minutes or 0.0)

    distance_charge = _round(miles * rates.per_mile)
    time_charge = _round(minutes * rates.per_minute)
    metered = _round(rates.base + distance_charge + time_charge)

    floor = rates.airport_flat if facts.is_airport else rates.minimum
    floored = max(metered, floor)
    floor_applied = floored > metered

    lines: list[dict] = [
        {"label": "base", "amount": _round(rates.base)},
        {"label": "distance", "amount": distance_charge, "qty": _round(miles)},
        {"label": "time", "amount": time_charge, "qty": _round(minutes)},
    ]
    if floor_applied:
        lines.append(
            {
                "label": "airport_flat" if facts.is_airport else "minimum",
                "amount": _round(floored - metered),
            }
        )

    subtotal = floored

    extra_stops = max(0, facts.extra_stops or 0)
    if extra_stops and rates.extra_stop_fee:
        stop_charge = _round(rates.extra_stop_fee * extra_stops)
        subtotal = _round(subtotal + stop_charge)
        lines.append({"label": "extra_stops", "amount": stop_charge, "qty": extra_stops})

    if facts.pax and facts.pax > rates.group_threshold and rates.group_surcharge:
        subtotal = _round(subtotal + rates.group_surcharge)
        lines.append({"label": "group_surcharge", "amount": _round(rates.group_surcharge)})

    peak = facts.is_peak if facts.is_peak is not None else is_peak_time(facts.scheduled_at)
    peak = bool(peak) and rates.peak_enabled and rates.peak_multiplier > 1.0
    if peak:
        bumped = _round(subtotal * rates.peak_multiplier)
        lines.append(
            {
                "label": "peak",
                "amount": _round(bumped - subtotal),
                "multiplier": rates.peak_multiplier,
            }
        )
        subtotal = bumped

    total = subtotal
    if facts.discount_pct and facts.discount_pct > 0:
        discount = _round(subtotal * facts.discount_pct / 100.0)
        lines.append({"label": "discount_code", "amount": -discount, "pct": facts.discount_pct})
        total = _round(subtotal - discount)
    elif facts.is_loyalty and rates.loyalty_discount_pct > 0:
        discount = _round(subtotal * rates.loyalty_discount_pct / 100.0)
        lines.append(
            {"label": "loyalty_discount", "amount": -discount, "pct": rates.loyalty_discount_pct}
        )
        total = _round(subtotal - discount)

    return {
        "currency": rates.currency,
        "total": total,
        "distance_miles": _round(miles),
        "duration_minutes": _round(minutes),
        "is_airport": facts.is_airport,
        "is_peak": peak,
        "is_loyalty": facts.is_loyalty,
        "lines": lines,
    }


def looks_like_airport(*texts: str | None) -> bool:
    """Heuristic: does any endpoint reference an airport (DEN/DIA/etc.)?"""
    keywords = get_settings().airport_keywords_list
    blob = " ".join(t.lower() for t in texts if t)
    return any(k in blob for k in keywords)
