"""Ground truth the blog writer must stand on — real routes, real fares, real business.

The articles were generic because the model was handed a tagline and a city and asked to be
specific. Everything it needed already existed in `frontend/lib/seoRoutes.ts`: eight
hand-written landing pages with real fares, distances and drive times taken from the live
quote engine. This module mirrors that data for the backend so an article can say
"Denver to Vail is a 105-minute drive, from $329 flat" instead of "we offer luxury mountain
transfers".

`tests/test_blog_facts.py` parses the TypeScript file and fails if this mirror drifts.

It also encodes what the business is NOT. The writer had been claiming an "all-electric
fleet" and "our chauffeurs are trained" — there is one Kia EV9. Inventing capacity is the
one error a service business cannot ship, so it is checked, not merely discouraged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The single vehicle. Plural-vehicle language is a factual error, not a style choice.
VEHICLE = "Kia EV9"
MAX_PASSENGERS = 6


@dataclass(frozen=True)
class Route:
    """A published landing page with a real, quotable fare."""

    slug: str
    label: str
    origin: str
    destination: str
    price_from: int
    distance_mi: int
    duration_min: int

    @property
    def path(self) -> str:
        return f"/rides/{self.slug}"


ROUTES: tuple[Route, ...] = (
    Route("aurora-to-den-airport", "Aurora → DEN", "Aurora, CO",
          "Denver International Airport (DEN)", 105, 12, 20),
    Route("cherry-creek-to-den-airport", "Cherry Creek → DEN", "Cherry Creek, Denver, CO",
          "Denver International Airport (DEN)", 105, 20, 31),
    Route("dtc-corporate-airport-transfer", "DTC → DEN",
          "Denver Tech Center, Greenwood Village, CO",
          "Denver International Airport (DEN)", 105, 22, 25),
    Route("boulder-to-den-airport", "Boulder → DEN", "Boulder, CO",
          "Denver International Airport (DEN)", 140, 39, 45),
    Route("red-rocks-concert-transportation", "Red Rocks concert rides", "Downtown Denver, CO",
          "Red Rocks Amphitheatre, Morrison, CO", 115, 15, 25),
    Route("denver-to-vail-private-transfer", "Denver → Vail", "Denver, CO", "Vail, CO",
          329, 97, 105),
    Route("denver-to-breckenridge-private-transfer", "Denver → Breckenridge", "Denver, CO",
          "Breckenridge, CO", 299, 81, 95),
    Route("denver-to-aspen-private-transfer", "Denver → Aspen", "Denver, CO", "Aspen, CO",
          790, 159, 205),
)

# Pages that earn money. An article that links only to "/" and "/blog" is SEO-inert.
MONEY_PATHS: frozenset[str] = frozenset({r.path for r in ROUTES} | {"/book"})

# Claims that are simply false. Checked against the finished article, not just asked for.
BANNED_PHRASES: tuple[str, ...] = (
    "our fleet", "the fleet", "fleet of", "our vehicles", "our cars", "our suvs",
    "vehicle fleet", "our drivers are trained", "our chauffeurs are trained",
    "years of experience", "award-winning", "voted best",
)

# Filler that reads as machine-written. Tolerated in small doses, failed in bulk — banning
# each one outright makes the model fight the checker instead of writing.
FILLER_PHRASES: tuple[str, ...] = (
    "epitome of", "unmatched luxury", "seamless experience", "the future of transportation",
    "discerning travel", "exceed your expectations", "at your disposal", "world-class",
    "state-of-the-art", "elevate your", "look no further", "in today's fast-paced",
    "nestled in", "when it comes to", "rest assured", "peace of mind",
)
MAX_FILLER = 2

# Place names that survive translation, so a Spanish article can be held to the same
# on-topic standard as the English one.
PLACES: tuple[str, ...] = (
    "denver", "den", "aurora", "boulder", "vail", "aspen", "breckenridge", "red rocks",
    "morrison", "cherry creek", "dtc", "greenwood village", "colorado", "keystone",
    "copper mountain", "winter park", "steamboat", "loveland", "golden", "littleton",
)


# Function words are the cheapest reliable language tell in a 500-word article: no article
# about Denver transfers avoids "the/and/your" or "de/la/que" for long.
_EN_WORDS = frozenset(
    "the and you your for with from that this are our have will can when been".split()
)
_ES_WORDS = frozenset(
    "de la el que en para con los las una por del al es su como más tu nuestro".split()
)


def detect_lang(text: str) -> str:
    """Which language this actually is: "en", "es", or "unknown" when there is no signal.

    Needed because the model has silently returned a fully English article for the Spanish
    slot — which would publish as duplicate content on the /es page, worse than publishing
    nothing at all.
    """
    words = re.findall(r"[a-záéíóúñü]+", (text or "").lower())
    en = sum(1 for w in words if w in _EN_WORDS)
    es = sum(1 for w in words if w in _ES_WORDS)
    if en == es:
        return "unknown"
    return "en" if en > es else "es"


def route_paths() -> set[str]:
    return {r.path for r in ROUTES}


def routes_block() -> str:
    """The fare table, phrased so the model quotes it instead of inventing numbers."""
    lines = [
        f"- {r.path} — {r.label} ({r.origin} → {r.destination}): "
        f"from ${r.price_from} flat, {r.distance_mi} miles, about {r.duration_min} minutes"
        for r in ROUTES
    ]
    return "\n".join(lines)


def truth_block() -> str:
    """Non-negotiable facts. Placed near the top of the prompt because it is what the model
    got wrong when it was left to fill the gaps itself."""
    return (
        f"- ONE vehicle: a single {VEHICLE} — all-electric, quiet premium cabin, up to "
        f"{MAX_PASSENGERS} passengers. There is no fleet. NEVER write \"our fleet\", "
        "\"our vehicles\" or \"our cars\": it is one car.\n"
        "- Chauffeurs: you MAY say \"our chauffeurs\" or \"our drivers\" — a small vetted "
        "team. Do NOT describe training programs, uniforms, or hiring standards you were "
        "not given.\n"
        "- Fares are FLAT and quoted upfront before booking. There is no surge pricing.\n"
        "- Quote ONLY the published \"from\" fares in the route table below, and always as "
        "\"from $X\". Never invent a price, a discount, or a fee.\n"
        "- Never invent phone numbers, email addresses, awards, ratings, years in business, "
        "or how many passengers have been driven.\n"
        "- Riders book online at /book; the fare is shown before they confirm.\n"
        "- These exact phrases are FORBIDDEN anywhere in the article: "
        + ", ".join(f'"{p}"' for p in BANNED_PHRASES)
        + "."
    )
