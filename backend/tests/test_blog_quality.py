"""The gate that decides whether an article may publish itself.

Every case here is a mistake the engine actually shipped to the owner's dashboard, taken
from the article it generated in production on 2026-07-27: a 67-character brand-first
title, an "all-electric fleet" that does not exist, three FAQ entries that all asked how to
book, and links that pointed at the homepage instead of a page with a price on it.

Pure functions, no DB.
"""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

from app.services import blog_facts, blog_quality  # noqa: E402

ALLOWED = {"/", "/book", "/rides", "/blog"} | blog_facts.route_paths()

_GOOD_BODY = """
## Aurora to DEN in about 20 minutes

Most of Aurora sits 12 miles from Denver International Airport, which is roughly a 20
minute drive down E-470 outside of rush hour. The fare is flat: from $105, quoted before
you book, with no surge pricing when a storm rolls in or four flight banks land at once.
That last part is the whole reason people stop using apps for the airport run. A 5am
pickup on a Monday and a 5pm pickup on a Friday cost the same here, because the price is
attached to the route rather than to how many other people happen to want a car.

## What the drive actually looks like

From Southlands or Saddle Rock you are on E-470 within a few minutes and the rest is one
uninterrupted road. From Heather Gardens the run up Peña Blvd is closer to 25 minutes,
and in the winter it is the stretch most likely to slow down, because the wind comes
across open ground and the plows work east to west. We time the pickup to your flight
rather than to a generic buffer, so you arrive with margin instead of jogging to the gate.
See the full [Aurora to DEN route](/rides/aurora-to-den-airport) for the exact pickup
notes, including where we meet you at each terminal level.

## Arrivals are the part that goes wrong

Departures are easy: you know when you need to leave. Arrivals are where a booking falls
apart, because the flight is late, or early, or you clear customs in nine minutes instead
of forty. We watch the inbound flight and move the pickup automatically, which means you
are not paying for a car that has been circling since your original landing time. If you
land at DEN and want the trip to continue west the same evening, that is a normal
request, not an exception.

## Heading to the mountains instead

If the trip continues to the resorts, Denver to Vail is 97 miles and about 105 minutes,
from $329 flat. Breckenridge is closer, 81 miles and roughly 95 minutes, from $299. Ski
season traffic on I-70 is the reason we leave earlier than the map suggests: the Eisenhower
Tunnel backs up on Saturday mornings in a way no routing app predicts well, and coming
home on Sunday afternoon is worse. Booking the return the night before is usually the
difference between a calm drive and a scramble.

## Luggage, car seats, and six people

The car is a Kia EV9, so there is room for up to six passengers and their bags without
anyone holding a backpack on their lap. Car seats are fine if you tell us in advance. The
cabin is quiet enough to take a call on the way in, which matters more on the 105 minute
run to Vail than on the 20 minute hop to the airport.

## What an early morning departure really costs you

The cheapest airport ride is the one where you do not park. Long-term parking at DEN runs
into real money across a week away, and you still have to drive yourself at 4am, find the
shuttle, and repeat the whole thing in reverse when you land tired. For two people on a
week-long trip the flat $105 each way is usually the cheaper option once the parking days
are added up, and for four people it is not close. That comparison is the honest reason
most of our Aurora regulars started, and it is worth doing with your own numbers rather
than taking our word for it.

## Booking

[Book online](/book) and the price is on screen before you confirm. If your plans are
still loose, book anyway and move the time later; changing a pickup is free and takes
about ten seconds.
""".strip()

_GOOD_FAQ = [
    {
        "q": "How much does an Aurora to DEN ride cost?",
        "a": "Fares start at $105 for a private ride in the Kia EV9. The price is flat and "
             "quoted before you book, so a delayed flight or a snowstorm does not change it.",
    },
    {
        "q": "How long is the drive from Aurora to the airport?",
        "a": "Most of Aurora is 12 miles out, roughly 20 minutes on E-470. We add margin for "
             "morning traffic and for the walk from the curb to your gate.",
    },
    {
        "q": "Do you track flights on arrivals?",
        "a": "Yes. We watch your inbound flight and shift the pickup automatically when it "
             "is early or late, so nobody is waiting at the curb paying for time.",
    },
]


def _article(**over):
    base = {
        "title": "Aurora to DEN Airport: Flat $105 Private EV Ride",
        "excerpt": "Private electric airport transfer from Aurora to DEN.",
        "body_md": _GOOD_BODY,
        "faq": _GOOD_FAQ,
        "internal_links": [{"href": "/book", "text": "Book online"}],
    }
    base.update(over)
    return base


def test_a_good_article_passes_clean():
    assert blog_quality.issues(_article(), keyword="Aurora to DEN airport", allowed=ALLOWED) == []


def test_the_title_that_shipped_is_rejected_for_length():
    """The real one: 67 chars, keyword starting at character 37."""
    bad = "Experience Unmatched Luxury with Our Denver Airport Shuttle Service"
    assert len(bad) > blog_quality.MAX_TITLE
    out = blog_quality.issues(
        _article(title=bad), keyword="luxury airport shuttle Denver", allowed=ALLOWED
    )
    assert any("characters" in i for i in out)


def test_an_off_topic_title_is_rejected():
    out = blog_quality.issues(
        _article(title="Why Electric Cars Are the Future"),
        keyword="Aurora to DEN airport",
        allowed=ALLOWED,
    )
    assert any("did not" in i or "does not name" in i for i in out)


def test_a_spanish_title_stays_on_topic_via_place_names():
    """The ES article targets a translated phrase, so only the place has to survive."""
    out = blog_quality.issues(
        _article(title="Traslado privado de Aurora al aeropuerto DEN desde $105"),
        keyword="Aurora to DEN airport",
        allowed=ALLOWED,
    )
    assert not any("does not name" in i for i in out)


def test_inventing_a_fleet_is_rejected():
    """The engine claimed an all-electric fleet. There is one Kia EV9."""
    body = _GOOD_BODY + "\n\nOur fleet is fully electric and our chauffeurs are trained."
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("our fleet" in i for i in out)
    assert any("our chauffeurs are trained" in i for i in out)


def test_saying_our_chauffeurs_is_allowed():
    """The owner's call: a small vetted team may be described in the plural."""
    body = _GOOD_BODY + "\n\nOur chauffeurs know which DEN door to use at 5am."
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert out == []


def test_an_article_with_no_numbers_is_rejected():
    body = (
        "## Luxury airport transfers in Aurora\n\nWe offer premium door-to-door service for "
        "travellers who value comfort. Our service is designed around you, and every ride is "
        "calm and quiet. [Book online](/book) and [see the route](/rides/aurora-to-den-airport)."
    ) + (" Comfort and care on every trip." * 60)
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("no fare, distance or drive time" in i for i in out)


def test_stock_phrases_in_bulk_are_rejected():
    body = _GOOD_BODY + (
        "\n\nWe deliver a seamless experience with world-class service. When it comes to "
        "travel, rest assured our state-of-the-art approach will elevate your journey."
    )
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("stock phrases" in i for i in out)


def test_a_couple_of_stock_phrases_is_tolerated():
    """The checker must not be so strict the model spends its retry fighting a thesaurus."""
    body = _GOOD_BODY + "\n\nRest assured the timing is world-class."
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert not any("stock phrases" in i for i in out)


def test_brochure_faq_is_rejected():
    """The three that shipped: how do I book, what areas, what vehicle. Nobody searches that."""
    faq = [
        {"q": "How do I book a ride with Black Volt Mobility?",
         "a": "Booking is easy. Visit our booking page and follow the prompts to reserve "
              "your ride today, it only takes a minute to complete."},
        {"q": "What areas do you serve?",
         "a": "We serve the Denver metro area including Boulder, and we offer transfers to "
              "and from Denver International Airport and the mountain resorts."},
        {"q": "What type of vehicle do you use?",
         "a": "We use the all-electric Kia EV9, which offers a quiet premium cabin and "
              "seating for up to six passengers on every trip."},
    ]
    out = blog_quality.issues(
        _article(faq=faq), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("would actually search" in i for i in out)


def test_thin_faq_answers_are_rejected():
    faq = [dict(f, a="Yes.") for f in _GOOD_FAQ]
    out = blog_quality.issues(
        _article(faq=faq), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("one-liners" in i for i in out)


def test_too_few_faq_entries_is_rejected():
    out = blog_quality.issues(
        _article(faq=_GOOD_FAQ[:1]), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("usable FAQ entries" in i for i in out)


def test_links_to_nowhere_useful_are_rejected():
    """Linking the homepage and the blog index is what the engine did. It earns nothing."""
    body = _GOOD_BODY.replace("(/rides/aurora-to-den-airport)", "(/blog)").replace(
        "(/book)", "(/)"
    )
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("no booking or route page" in i for i in out)


def test_invented_links_do_not_count():
    body = _GOOD_BODY.replace("(/rides/aurora-to-den-airport)", "(/pricing-guide)").replace(
        "(/book)", "(/contact-us)"
    )
    out = blog_quality.issues(
        _article(body_md=body), keyword="Aurora to DEN airport", allowed=ALLOWED
    )
    assert any("valid internal links" in i for i in out)


def test_a_thin_article_is_rejected():
    out = blog_quality.issues(
        _article(body_md="## Aurora to DEN\n\nFrom $105, 12 miles, 20 minutes. [Book](/book) "
                         "and [route](/rides/aurora-to-den-airport)."),
        keyword="Aurora to DEN airport",
        allowed=ALLOWED,
    )
    assert any("words of substance" in i for i in out)
