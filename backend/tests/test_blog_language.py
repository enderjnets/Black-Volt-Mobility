"""The Spanish article has to actually be in Spanish.

Found in production on the first clean run: post 23 passed every other check and was
scheduled to publish, with a `body_md_es` that opened "If you're looking for a reliable and
luxurious way to travel from Boulder to Denver International Airport". That would have put a
duplicate of the English article on the /es page — worse for search than publishing nothing.
Nothing in the gate looked at the language.

Pure functions, no DB.
"""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

from app.services import blog_facts, blog_quality, blog_writer  # noqa: E402

ALLOWED = {"/", "/book", "/rides", "/blog"} | blog_facts.route_paths()

_EN = (
    "If you are looking for a reliable way to travel from Boulder to Denver International "
    "Airport, the ride is 39 miles and about 45 minutes, and the fare starts at $140 flat. "
    "You can book online and the price is on your screen before you confirm it. "
    "[Book online](/book) or see the [Boulder route](/rides/boulder-to-den-airport)."
)
_ES = (
    "Si buscas una forma confiable de viajar de Boulder al Aeropuerto Internacional de "
    "Denver, el trayecto es de 39 millas y unos 45 minutos, y la tarifa parte desde $140 "
    "fija. Puedes reservar en línea y ves el precio antes de confirmar. "
    "[Reserva en línea](/book) o mira la [ruta de Boulder](/rides/boulder-to-den-airport)."
)


def test_detects_english():
    assert blog_facts.detect_lang(_EN) == "en"


def test_detects_spanish():
    assert blog_facts.detect_lang(_ES) == "es"


def test_no_signal_is_unknown_rather_than_a_guess():
    assert blog_facts.detect_lang("Boulder DEN Airport Shuttle") == "unknown"
    assert blog_facts.detect_lang("") == "unknown"


def test_an_english_body_in_the_spanish_slot_is_rejected():
    """The exact production failure."""
    out = blog_quality.issues(
        {"title": "Boulder a DEN", "body_md": _EN * 6, "faq": [], "internal_links": []},
        keyword="Boulder to DEN airport",
        allowed=ALLOWED,
        lang="es",
    )
    assert any("written in English" in i and "Spanish version" in i for i in out)


def test_a_spanish_body_in_the_spanish_slot_is_not_flagged_for_language():
    out = blog_quality.issues(
        {"title": "Boulder a DEN", "body_md": _ES * 6, "faq": [], "internal_links": []},
        keyword="Boulder to DEN airport",
        allowed=ALLOWED,
        lang="es",
    )
    assert not any("written in" in i for i in out)


def test_a_spanish_body_in_the_english_slot_is_rejected_too():
    out = blog_quality.issues(
        {"title": "Boulder to DEN", "body_md": _ES * 6, "faq": [], "internal_links": []},
        keyword="Boulder to DEN airport",
        allowed=ALLOWED,
        lang="en",
    )
    assert any("written in Spanish" in i for i in out)


def test_a_short_body_is_not_language_checked():
    """Too little text to tell, and the word-count check already catches it."""
    out = blog_quality.issues(
        {"title": "Boulder a DEN", "body_md": "Corto.", "faq": [], "internal_links": []},
        keyword="Boulder to DEN airport",
        allowed=ALLOWED,
        lang="es",
    )
    assert not any("written in" in i for i in out)


def test_shortening_never_leaves_a_spanish_page_with_an_english_headline():
    """The regression the title repair introduced: cutting at the colon kept the English
    half and threw away the Spanish description."""
    long_es = "Boulder to DEN Airport Shuttle: Traslados Privados en Vehículo Eléctrico"
    assert len(long_es) > blog_quality.MAX_TITLE
    out = blog_writer._shorten_title(long_es, "Boulder to DEN airport", "es")
    assert out == long_es  # left long, so the gate flags it instead of mangling it


def test_shortening_still_works_when_the_head_is_spanish():
    long_es = "Traslado de Boulder al aeropuerto DEN: la guía completa para viajeros"
    out = blog_writer._shorten_title(long_es, "Boulder to DEN airport", "es")
    assert out == "Traslado de Boulder al aeropuerto DEN"


def test_shortening_still_works_for_english():
    long_en = "Boulder to DEN Airport Shuttle: Premium Electric Rides for Every Traveller"
    out = blog_writer._shorten_title(long_en, "Boulder to DEN airport", "en")
    assert out == "Boulder to DEN Airport Shuttle"
