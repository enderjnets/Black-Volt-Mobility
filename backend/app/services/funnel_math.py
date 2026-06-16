"""Pure, dependency-free math for the driver sales funnel (the "My Stats" tab).

The funnel has three logged conversion stages plus a money tail:

    conversations ──► pitches ──► contacts ──► clients ──► revenue
                 r_pitch     r_contact   r_convert   $/client

With only a handful of conversations a day, raw rates are wildly unstable: one
pitch out of one conversation reads as "100% pitch rate", which would make any
projection nonsense. So each stage rate is computed with **Beta-Binomial
smoothing** (a weak Beta(1,1)/Laplace prior) for a stable point estimate, and a
**Wilson score interval** for an honest 90% confidence band. A `low_data` flag
tells the UI when there simply isn't enough history to trust the number yet.

The projection (effort → expected clients/revenue) and the inverse goal
calculator (target → required daily activity) both fall straight out of the
smoothed chain. Everything here is a pure function so it can be unit-tested in
isolation, with no DB or framework.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

# Weak Beta(1,1) (Laplace) prior — one phantom success and one phantom failure.
# Guarantees every smoothed rate is strictly between 0 and 1, so downstream
# divisions never blow up and a single lucky day never reads as 100%.
_PRIOR_A = 1.0
_PRIOR_B = 1.0
# Fewer than this many trials at a stage → flag it as not-yet-trustworthy.
LOW_DATA_TRIALS = 5
# z-score for a two-sided 90% interval.
_Z90 = 1.6448536269514722
# A coaching nudge must stay human-reachable: never suggest an absurd daily
# cadence (a huge goal or a near-zero conversion rate could otherwise demand
# hundreds of conversations/day). Capping here keeps the suggestion — and the
# clients/revenue projected from it — credible and finite.
COACH_MAX_PER_DAY = 40.0


@dataclass
class Rate:
    """A smoothed conversion rate with a 90% confidence band."""

    num: int      # successes (e.g. pitches)
    den: int      # trials (e.g. conversations)
    point: float  # smoothed posterior-mean rate, in (0, 1)
    low: float    # 90% lower bound (Wilson)
    high: float   # 90% upper bound (Wilson)
    low_data: bool

    def dict(self) -> dict:
        return asdict(self)


def wilson_interval(num: int, den: int, z: float = _Z90) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion — closed form, well-behaved
    at the extremes (no negative bounds, no >1 bounds) and with tiny samples."""
    if den <= 0:
        return (0.0, 1.0)
    p = num / den
    z2 = z * z
    denom = 1.0 + z2 / den
    center = (p + z2 / (2 * den)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * den)) / den)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def smoothed_rate(num: int, den: int) -> Rate:
    """Beta(1,1)-smoothed point estimate + Wilson 90% band for num/den."""
    num = max(0, int(num))
    den = max(0, int(den))
    num = min(num, den)  # successes can never exceed trials
    point = (num + _PRIOR_A) / (den + _PRIOR_A + _PRIOR_B)
    low, high = wilson_interval(num, den)
    return Rate(num=num, den=den, point=point, low=low, high=high, low_data=den < LOW_DATA_TRIALS)


@dataclass
class FunnelRates:
    pitch: Rate      # conversations → pitches
    contact: Rate    # pitches → contacts
    convert: Rate    # contacts → clients (won)
    overall_point: float  # conversations → clients (product of the three)
    overall_low: float
    overall_high: float


def funnel_rates(conversations: int, pitches: int, contacts: int, clients: int) -> FunnelRates:
    """Build the three smoothed stage rates plus the overall conversations→clients
    rate. Stages are chained on the raw counts (pitches are trials for contacts,
    etc.); the overall rate multiplies the smoothed points (and bounds)."""
    pitch = smoothed_rate(pitches, conversations)
    contact = smoothed_rate(contacts, pitches)
    convert = smoothed_rate(clients, contacts)
    return FunnelRates(
        pitch=pitch,
        contact=contact,
        convert=convert,
        overall_point=pitch.point * contact.point * convert.point,
        overall_low=pitch.low * contact.low * convert.low,
        overall_high=pitch.high * contact.high * convert.high,
    )


@dataclass
class Projection:
    horizon_days: int
    working_days: float
    conversations_per_day: float
    expected_clients: float
    expected_clients_low: float
    expected_clients_high: float
    expected_revenue: float
    expected_revenue_low: float
    expected_revenue_high: float


def project(
    *,
    rates: FunnelRates,
    conversations_per_day: float,
    working_days: float,
    revenue_per_client: float,
) -> Projection:
    """Expected clients & revenue over a horizon at the driver's recent pace."""
    conv = max(0.0, conversations_per_day) * max(0.0, working_days)
    clients = conv * rates.overall_point
    clients_lo = conv * rates.overall_low
    clients_hi = conv * rates.overall_high
    rpc = max(0.0, revenue_per_client)
    return Projection(
        horizon_days=int(round(working_days)),
        working_days=working_days,
        conversations_per_day=conversations_per_day,
        expected_clients=clients,
        expected_clients_low=clients_lo,
        expected_clients_high=clients_hi,
        expected_revenue=clients * rpc,
        expected_revenue_low=clients_lo * rpc,
        expected_revenue_high=clients_hi * rpc,
    )


@dataclass
class RequiredActivity:
    target_clients: float
    contacts: float
    pitches: float
    conversations: float
    conversations_per_day: float
    # Conservative (assume worst-case rates) → more effort; optimistic → less.
    conversations_per_day_low: float
    conversations_per_day_high: float


def required_activity(
    *,
    target_clients: float,
    rates: FunnelRates,
    working_days: float,
) -> RequiredActivity:
    """Invert the funnel: how many conversations (total and per working day) are
    needed to win `target_clients`. The smoothed points give the central
    estimate; the interval bounds give an effort range (worst-case rates need
    more conversations, best-case fewer)."""
    target = max(0.0, target_clients)
    days = max(1.0, working_days)

    def conv_for(overall: float) -> float:
        # overall is always > 0 thanks to the Beta prior, so this never divides
        # by zero — but clamp defensively.
        return target / overall if overall > 1e-9 else float("inf")

    contacts = target / rates.convert.point if rates.convert.point > 1e-9 else float("inf")
    pitches = contacts / rates.contact.point if rates.contact.point > 1e-9 else float("inf")
    conversations = conv_for(rates.overall_point)
    return RequiredActivity(
        target_clients=target,
        contacts=contacts,
        pitches=pitches,
        conversations=conversations,
        conversations_per_day=conversations / days,
        # Worst-case (low) rates ⇒ need MORE conversations; best-case ⇒ fewer.
        conversations_per_day_low=conv_for(rates.overall_high) / days,
        conversations_per_day_high=conv_for(rates.overall_low) / days,
    )


def clients_for_revenue(target_revenue: float, revenue_per_client: float) -> float | None:
    """Translate a revenue target into a client target. Returns None when there's
    no earnings history to estimate $/client from."""
    if revenue_per_client <= 0:
        return None
    return max(0.0, target_revenue) / revenue_per_client


@dataclass
class CoachInsight:
    """One actionable nudge derived purely from the funnel model — the numbers the
    AI coach is allowed to talk about (it may rephrase, never invent). Identifies
    the weakest stage (the lever with the most upside), a modestly higher daily
    cadence, and the clients/revenue that cadence is expected to yield over one
    working week, with an honest confidence band and a "land at least one new
    client" probability."""

    focus_stage: str  # "pitch" | "contact" | "convert" — the conversion bottleneck
    focus_rate: float
    current_per_day: float
    suggested_per_day: float
    horizon_days: int
    expected_clients: float
    expected_clients_low: float
    expected_clients_high: float
    expected_revenue: float
    expected_revenue_low: float
    expected_revenue_high: float
    prob_at_least_one: float  # P(≥1 new client) at the suggested cadence over the horizon
    has_earnings: bool

    def dict(self) -> dict:
        return asdict(self)


def coach_insight(
    *,
    rates: FunnelRates,
    conversations_per_day: float,
    working_days: float,
    revenue_per_client: float,
    target_clients: float | None = None,
) -> CoachInsight:
    """Turn the smoothed funnel into a single coaching nudge. The suggested daily
    cadence is the activity needed to hit `target_clients` (when a goal is set),
    else a modest bump over the driver's current pace. Everything is projected
    forward at that cadence over `working_days` so the AI only ever restates real,
    defensible figures."""
    current = max(0.0, conversations_per_day)
    days = max(1.0, working_days)

    # Weakest stage = the bottleneck (smallest smoothed point) → the lever to pull.
    stages = {
        "pitch": rates.pitch.point,
        "contact": rates.contact.point,
        "convert": rates.convert.point,
    }
    focus_stage = min(stages, key=lambda k: stages[k])

    if target_clients is not None and target_clients > 0:
        suggested = required_activity(
            target_clients=target_clients, rates=rates, working_days=days
        ).conversations_per_day
    else:
        # A reachable stretch: at least +2/day (or +50%), and never below 3.
        suggested = max(math.ceil(current * 1.5), current + 2, 3.0)
    suggested = max(suggested, current)
    # Keep it human-reachable (and finite, even if required_activity → inf): never
    # push past the cap unless the driver's own pace is already higher.
    suggested = min(suggested, max(current, COACH_MAX_PER_DAY))

    proj = project(
        rates=rates,
        conversations_per_day=suggested,
        working_days=days,
        revenue_per_client=max(0.0, revenue_per_client),
    )

    # P(≥1 client) over the horizon at the suggested cadence. overall_point is in
    # (0,1) thanks to the Beta prior, so this is always a clean probability.
    trials = suggested * days
    p = min(1.0, max(0.0, rates.overall_point))
    prob = 1.0 - (1.0 - p) ** trials
    prob = min(1.0, max(0.0, prob))

    return CoachInsight(
        focus_stage=focus_stage,
        focus_rate=stages[focus_stage],
        current_per_day=current,
        suggested_per_day=suggested,
        horizon_days=int(round(days)),
        expected_clients=proj.expected_clients,
        expected_clients_low=proj.expected_clients_low,
        expected_clients_high=proj.expected_clients_high,
        expected_revenue=proj.expected_revenue,
        expected_revenue_low=proj.expected_revenue_low,
        expected_revenue_high=proj.expected_revenue_high,
        prob_at_least_one=prob,
        has_earnings=revenue_per_client > 0,
    )
