"""Decides whether a generated article is allowed to publish itself.

The autopilot's promise is that the owner does not have to read every post. That only holds
if something refuses the bad ones. Each check below exists because the engine actually
shipped that mistake: a 67-character brand-first title, an "all-electric fleet" that does
not exist, three FAQ entries that all asked how to book, and four internal links of which
two pointed at the homepage.

`issues()` returns human-readable sentences, not codes: they are fed straight back to the
model on the retry, and shown to the owner on a drafted post.
"""
from __future__ import annotations

import re

from app.services import blog_facts

# Google truncates around here; a title longer than this is spent copy the rider never sees.
MAX_TITLE = 60
MIN_WORDS = 550
MAX_WORDS = 1500
MIN_FAQ = 3
MIN_FAQ_ANSWER = 80
MIN_INTERNAL_LINKS = 2

_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_SYNTAX = re.compile(r"[#*_`>|\[\]()]")
# A price, a distance or a duration — the cheapest proxy for "this says something concrete".
_CONCRETE = re.compile(r"\$\s?\d|\b\d+\s*(?:mi|mile|miles|min|minute|minutes|minuto)", re.I)
# Questions worth ranking for: what a rider types, not what a brochure answers.
_INTENT_Q = re.compile(
    r"how much|how long|how far|how early|cost|price|cuánto|cuanto|precio|"
    r"qué tan|que tan|cuándo|cuando",
    re.I,
)

_STOP = {
    "the", "a", "an", "and", "or", "to", "from", "in", "of", "for", "with", "your", "our",
    "de", "la", "el", "los", "las", "y", "o", "en", "un", "una", "para", "con", "del", "al",
}


def _words(body: str) -> int:
    return len([w for w in _MD_SYNTAX.sub(" ", body or "").split() if w])


def _links(body: str) -> list[str]:
    return [m.group(2).strip() for m in _MD_LINK.finditer(body or "")]


def _terms(keyword: str) -> list[str]:
    parts = re.split(r"[^\w]+", (keyword or "").lower())
    return [t for t in parts if len(t) > 2 and t not in _STOP]


def _places_in(text: str) -> set[str]:
    low = (text or "").lower()
    return {p for p in blog_facts.PLACES if p in low}


def _on_topic(title: str, keyword: str) -> bool:
    """Is the title actually about the thing we are targeting?

    Place names carry across languages, so the Spanish article is held to the same standard
    as the English one without pretending to translate the keyword.
    """
    kw_places = _places_in(keyword)
    if kw_places:
        return bool(kw_places & _places_in(title))
    terms = _terms(keyword)
    low = (title or "").lower()
    return any(t in low for t in terms) if terms else True


def issues(article: dict, *, keyword: str, allowed: set[str]) -> list[str]:
    """Everything wrong with this article, phrased as an instruction to fix it."""
    out: list[str] = []
    title = (article.get("title") or "").strip()
    body = article.get("body_md") or ""
    low_body = body.lower()

    if not title:
        out.append("The article has no title.")
    elif len(title) > MAX_TITLE:
        out.append(
            f"The title is {len(title)} characters; Google cuts it off at {MAX_TITLE}. "
            "Lead with the search phrase and drop the brand-flavoured opener."
        )
    if title and not _on_topic(title, keyword):
        out.append(
            f'The title does not name what the reader searched for ("{keyword}"). '
            "Put the place and the service in the title."
        )

    n = _words(body)
    if n < MIN_WORDS:
        out.append(f"The body is only {n} words; write 600-900 words of substance.")
    elif n > MAX_WORDS:
        out.append(f"The body is {n} words; tighten it to 600-900.")

    for phrase in blog_facts.BANNED_PHRASES:
        if phrase in low_body:
            out.append(
                f'The article says "{phrase}", which is not true of this business. '
                "There is one Kia EV9 and a small team."
            )
    filler = [p for p in blog_facts.FILLER_PHRASES if p in low_body]
    if len(filler) > blog_facts.MAX_FILLER:
        out.append(
            "The writing leans on stock phrases (" + ", ".join(f'"{p}"' for p in filler[:4])
            + "). Replace them with specifics: fares, drive times, neighbourhoods, logistics."
        )
    if not _CONCRETE.search(body):
        out.append(
            "The article contains no fare, distance or drive time. Use the real numbers from "
            "the route table — that is the whole reason the reader is here."
        )

    faq = article.get("faq") or []
    usable = [f for f in faq if isinstance(f, dict) and f.get("q") and f.get("a")]
    if len(usable) < MIN_FAQ:
        out.append(f"Only {len(usable)} usable FAQ entries; write {MIN_FAQ} with real answers.")
    else:
        thin = [f for f in usable if len(str(f["a"]).strip()) < MIN_FAQ_ANSWER]
        if thin:
            out.append(
                f"{len(thin)} FAQ answers are one-liners; answer each in 2-3 real sentences."
            )
        if not any(_INTENT_Q.search(str(f["q"])) for f in usable):
            out.append(
                "None of the FAQ questions is one a rider would actually search "
                '("how much is it", "how long is the drive", "how early should I book"). '
                "At least one must be."
            )

    used = [h for h in _links(body) if h in allowed]
    if len(set(used)) < MIN_INTERNAL_LINKS:
        out.append(
            f"The body contains {len(set(used))} valid internal links; include at least "
            f"{MIN_INTERNAL_LINKS} as markdown links inside the text."
        )
    if not (set(used) & blog_facts.MONEY_PATHS):
        out.append(
            "The article links to no booking or route page. Link at least one relevant "
            "/rides/... route page or /book."
        )
    return out
