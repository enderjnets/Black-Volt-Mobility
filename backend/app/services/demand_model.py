"""'Where to wait' — the math, and only the math. Pure functions, no DB/network,
so every rule here is unit-tested in isolation (same idea as zones.py/funnel_math.py).

The quantity we estimate is a RATE: Black + Black SUV offers per minute of `open`
(online-and-waiting) time in a cell/zone at an hour of the week. The probability the
UI shows is P(at least one offer within 15 min) = 1 - exp(-15·rate).

With almost no data of the owner's own, the rate is a PRIOR built from proxies. As
he logs shifts, each cell blends toward his observed rate with a Gamma-Poisson
(empirical-Bayes) update: posterior mean = (α + offers) / (β + minutes), where the
prior mean is α/β and β is "how many of his own minutes it takes to out-vote the
proxies". `own_share` = minutes / (minutes + β) is what the UI shows as "x% from
your data".

All the tunable numbers live in the constants block below, one comment each.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
HOURS_PER_WEEK = 168
WINDOW_MIN = 15

# ── Tunables ────────────────────────────────────────────────────────────────────
# Default offers/min before any data: one Black offer per ~33 minutes of waiting in
# an average cell. Replaced by the owner's global observed rate once he has logged
# ≥ 600 open minutes (see demand.py).
DEFAULT_BASE_RATE = 0.03
# Pseudo-exposure minutes of the prior: 10 hours of his own waiting in a cell make
# his data and the proxies count equally.
PSEUDO_EXPOSURE_MIN = 600.0
# Multiplier bounds (min, max). Affluence 0..1 maps linearly to 0.5..2.5.
AFFLUENCE_RANGE = (0.5, 2.5)
HOTEL_STEP, HOTEL_MAX = 0.25, 2.5        # +25% per luxury hotel within ~1 km, cap ×2.5
GENERATOR_STEP, GENERATOR_MAX = 0.10, 2.0  # +10% per generator within ~1.5 km, cap ×2
FLIGHT_RANGE = (0.5, 3.0)                # hour's DEN flights ÷ daily mean, clamped
EVENT_RANGE = (1.0, 3.0)                 # event windows only ever lift
WEATHER_RANGE = (0.7, 1.5)
# Wilson–Hilferty normal quantiles for the Gamma interval.
_Z = {0.1: -1.2815515655, 0.5: 0.0, 0.9: 1.2815515655}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ── Time ────────────────────────────────────────────────────────────────────────
def hour_of_week(at: datetime) -> int:
    """0 = Monday 00:00 in Denver … 167 = Sunday 23:00. `at` must be tz-aware."""
    local = at.astimezone(DENVER)
    return local.weekday() * 24 + local.hour


def local_hour_starts(day: date) -> list[datetime]:
    """Tz-aware start of every local hour of `day` in Denver. DST days yield 23 or 25
    entries; callers iterate these instead of assuming 24 slots."""
    start = datetime.combine(day, time(0), tzinfo=DENVER)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=DENVER)
    out: list[datetime] = []
    cur = start.astimezone(ZoneInfo("UTC"))
    end_utc = end.astimezone(ZoneInfo("UTC"))
    while cur < end_utc:
        out.append(cur.astimezone(DENVER))
        cur += timedelta(hours=1)
    return out


# ── Rate estimation ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Estimate:
    mean: float        # offers per minute
    lo: float          # 10th percentile
    hi: float          # 90th percentile
    own_share: float   # 0..1, share of the estimate that comes from the owner's data
    offers: float
    exposure_min: float


def prior_rate(
    base: float,
    *,
    affluence: float,
    hotels: int,
    generators: int,
    flight_mult: float = 1.0,
    event_mult: float = 1.0,
    weather_mult: float = 1.0,
) -> float:
    a_lo, a_hi = AFFLUENCE_RANGE
    m_aff = clamp(a_lo + clamp(affluence, 0.0, 1.0) * (a_hi - a_lo), a_lo, a_hi)
    m_hot = clamp(1.0 + HOTEL_STEP * max(0, hotels), 1.0, HOTEL_MAX)
    m_gen = clamp(1.0 + GENERATOR_STEP * max(0, generators), 1.0, GENERATOR_MAX)
    m_fl = clamp(flight_mult, *FLIGHT_RANGE)
    m_ev = clamp(event_mult, *EVENT_RANGE)
    m_we = clamp(weather_mult, *WEATHER_RANGE)
    return max(0.0, base) * m_aff * m_hot * m_gen * m_fl * m_ev * m_we


def gamma_quantile(shape: float, rate: float, p: float) -> float:
    """Approximate Gamma(shape, rate) quantile (Wilson–Hilferty). Good enough for a
    display interval; avoids a scipy dependency."""
    k = max(shape, 1e-9)
    z = _Z[p]
    c = 1.0 / (9.0 * k)
    x = k * (1.0 - c + z * math.sqrt(c)) ** 3
    return max(0.0, x) / max(rate, 1e-9)


def posterior(
    prior: float, offers: float, exposure_min: float, pseudo_min: float = PSEUDO_EXPOSURE_MIN
) -> Estimate:
    alpha = max(prior, 1e-9) * pseudo_min + max(0.0, offers)
    beta = pseudo_min + max(0.0, exposure_min)
    return Estimate(
        mean=alpha / beta,
        lo=gamma_quantile(alpha, beta, 0.1),
        hi=gamma_quantile(alpha, beta, 0.9),
        own_share=max(0.0, exposure_min) / beta,
        offers=offers,
        exposure_min=exposure_min,
    )


def p_within(rate_per_min: float, minutes: int = WINDOW_MIN) -> float:
    return 1.0 - math.exp(-max(0.0, rate_per_min) * minutes)


def pool_hours(values: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Borrow strength from the adjacent hours (weight ½ each), circular over the week."""
    n = len(values)
    out: list[tuple[float, float]] = []
    for i in range(n):
        o, e = values[i]
        for j in (i - 1, (i + 1) % n):
            oj, ej = values[j]
            o += 0.5 * oj
            e += 0.5 * ej
        out.append((o, e))
    return out


# ── Planner ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Block:
    dow: int          # 0 = Monday
    start_hour: int   # inclusive, local
    end_hour: int     # exclusive, local
    expected_offers: float
    mean: float       # average rate over the block


def top_blocks(
    grid: list[Estimate],
    *,
    threshold: float | None = None,
    min_hours: int = 2,
    limit: int = 5,
) -> list[Block]:
    """Contiguous runs (within a day) of hours whose mean ≥ threshold, ranked by
    expected offers. Default threshold = 75th percentile of the week's means."""
    if len(grid) != HOURS_PER_WEEK:
        raise ValueError("grid must have 168 entries")
    if threshold is None:
        means = sorted(e.mean for e in grid)
        threshold = means[int(0.75 * len(means))]
    blocks: list[Block] = []
    for dow in range(7):
        h = 0
        while h < 24:
            if grid[dow * 24 + h].mean >= threshold:
                start = h
                while h < 24 and grid[dow * 24 + h].mean >= threshold:
                    h += 1
                if h - start >= min_hours:
                    hours = [grid[dow * 24 + x] for x in range(start, h)]
                    mean = sum(e.mean for e in hours) / len(hours)
                    blocks.append(
                        Block(dow, start, h, expected_offers=mean * 60 * len(hours), mean=mean)
                    )
            else:
                h += 1
    blocks.sort(key=lambda b: b.expected_offers, reverse=True)
    return blocks[:limit]


def bridge_worth_it(
    fare: float | None, bridge_fare: float, here_mean: float, dest_mean: float
) -> bool:
    """A Comfort ride is a 'bridge' when it pays enough AND lands somewhere clearly
    better (≥ 1.5× the current cell's rate)."""
    if fare is None or fare < bridge_fare:
        return False
    return dest_mean >= 1.5 * max(here_mean, 1e-9)


def travel_penalty_fraction(
    grid_distance_cells: int,
    *,
    edge_m: float = 531.0,
    mph: float = 25.0,
    window_min: int = WINDOW_MIN,
) -> float:
    """Fraction of the decision window spent driving to a cell (0 = here, 1 = out of
    reach). H3 res-8 edge ≈ 531 m; no Directions call, ever."""
    if grid_distance_cells <= 0:
        return 0.0
    miles = grid_distance_cells * edge_m / 1609.344
    minutes = miles / mph * 60.0
    return clamp(minutes / window_min, 0.0, 1.0)
