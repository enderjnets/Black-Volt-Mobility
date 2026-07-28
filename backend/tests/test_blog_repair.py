"""Fix what is mechanically fixable before grading the writing.

All three cases came out of the first production run on the new engine (post 22): the model
wrote three good FAQ questions as `##` headings and left the JSON field empty, left
`internal_links` empty while the body linked correctly, and produced a 65-character title
whose first 29 characters were the whole point. Rejecting an article for any of those would
send the owner a draft over a formatting slip.

Pure functions, no DB.
"""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

from app.services import blog_facts, blog_writer  # noqa: E402

ALLOWED = {"/", "/book", "/rides", "/blog"} | blog_facts.route_paths()


# ─── Titles ────────────────────────────────────────────────────────────────────


def test_a_subtitle_is_dropped_when_the_title_runs_long():
    """The real one: 65 characters, and the search phrase is the first 29."""
    long = "Luxury Airport Shuttle Denver: Premium Electric Chauffeur Service"
    out = blog_writer._shorten_title(long, "luxury airport shuttle Denver")
    assert out == "Luxury Airport Shuttle Denver"


def test_an_em_dash_subtitle_is_dropped_too():
    long = "Boulder to DEN Airport — The Complete Guide to Getting There On Time"
    out = blog_writer._shorten_title(long, "Boulder to DEN airport")
    assert out == "Boulder to DEN Airport"


def test_a_short_title_is_left_alone():
    good = "Aurora to DEN: Flat $105 Private EV Ride"
    assert blog_writer._shorten_title(good, "Aurora to DEN airport") == good


def test_a_long_title_with_no_subtitle_is_left_for_the_gate():
    """No safe cut means no cut — better a flagged draft than a mangled headline."""
    long = "Everything You Have Ever Wanted To Know About Getting To Denver Airport"
    assert blog_writer._shorten_title(long, "Denver airport") == long


def test_a_head_that_loses_the_topic_is_not_used():
    long = "The Complete Guide: Boulder to DEN Airport Private Transfers Explained"
    out = blog_writer._shorten_title(long, "Boulder to DEN airport")
    assert out == long  # cutting at the colon would drop Boulder and DEN


# ─── FAQ harvesting ────────────────────────────────────────────────────────────

_BODY_WITH_HEADING_FAQ = """
## Getting to DEN from Boulder

Boulder is 39 miles out, about 45 minutes, from $140 flat.

## How much does a Boulder to DEN ride cost?

Fares start at $140 flat for the whole car. The price is quoted before you book and does
not move with demand.

## How long does it take to get from Boulder to DEN?

About 45 minutes for the 39 miles, longer in snow. We build in margin for early flights.

## Can I book the night before?

Yes, and for a 5am departure that is what we recommend. Same-day requests are taken when
the car is free.
""".strip()


def test_a_faq_written_as_headings_is_harvested():
    out = blog_writer._harvest_faq(_BODY_WITH_HEADING_FAQ)
    assert len(out) == 3
    assert out[0]["q"] == "How much does a Boulder to DEN ride cost?"
    assert "$140" in out[0]["a"]
    # The non-question section is not mistaken for a FAQ entry.
    assert all(f["q"].endswith("?") for f in out)


def test_a_question_with_no_real_answer_is_skipped():
    body = "## Is this a question?\n\nYes.\n\n## Another one?\n\n" + "x" * 60
    out = blog_writer._harvest_faq(body)
    assert [f["q"] for f in out] == ["Another one?"]


def test_the_q_and_a_prefixes_are_stripped():
    body = (
        "### Q: How early should I book my airport pickup?\n\n"
        "A: The night before for an early flight. We time the pickup to the flight so you "
        "arrive with margin rather than a scramble.\n"
    )
    out = blog_writer._harvest_faq(body)
    assert out[0]["q"] == "How early should I book my airport pickup?"
    assert out[0]["a"].startswith("The night before")


def test_a_body_with_no_questions_harvests_nothing():
    assert blog_writer._harvest_faq("## Just a section\n\nSome prose here.") == []


# ─── Links ─────────────────────────────────────────────────────────────────────


def test_links_are_read_from_the_body_not_the_models_list():
    body = (
        "See the [Boulder route](/rides/boulder-to-den-airport) or just "
        "[book online](/book). Ignore [this](/made-up-page) and [that](https://example.com)."
    )
    out = blog_writer._links_in_body(body, ALLOWED)
    assert [x["href"] for x in out] == ["/rides/boulder-to-den-airport", "/book"]
    assert out[0]["text"] == "Boulder route"


def test_a_repeated_link_is_listed_once():
    body = "[book](/book) and later [book again](/book)"
    assert len(blog_writer._links_in_body(body, ALLOWED)) == 1


# ─── The repair as a whole ─────────────────────────────────────────────────────


def test_repair_fills_in_what_the_model_left_empty():
    data = {
        "title": "Luxury Airport Shuttle Denver: Premium Electric Chauffeur Service",
        "body_md": _BODY_WITH_HEADING_FAQ + "\n\n[Book online](/book)",
        "faq": [],
        "internal_links": [],
    }
    out = blog_writer._repair(data, "luxury airport shuttle Denver", ALLOWED)
    assert out["title"] == "Luxury Airport Shuttle Denver"
    assert len(out["faq"]) == 3
    assert [x["href"] for x in out["internal_links"]] == ["/book"]


def test_repair_does_not_overwrite_a_faq_the_model_supplied():
    supplied = [{"q": "How much?", "a": "From $105 flat, quoted before you book."}]
    data = {
        "title": "Aurora to DEN: Flat $105 Private EV Ride",
        "body_md": _BODY_WITH_HEADING_FAQ,
        "faq": supplied,
        "internal_links": [],
    }
    out = blog_writer._repair(data, "Aurora to DEN airport", ALLOWED)
    assert out["faq"] == supplied
