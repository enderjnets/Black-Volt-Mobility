"""Reading ``rides.flight_number``.

Every case here is a shape that is in the production table today, or one the booking code
is already on record as producing. The column was never validated, so the parser's job is
not to be clever — it is to be right about the seven ways the same flight has been typed,
and honest about the six entries that are only digits.
"""
import pytest

from app.services import flight_code as fc


@pytest.mark.parametrize(
    ("raw", "carrier", "number"),
    [
        ("UA 1377", "UA", 1377),   # the common shape
        ("UA2085", "UA", 2085),    # no space
        ("WN 3018", "WN", 3018),
        ("WN203", "WN", 203),
        ("DL 0346", "DL", 346),    # zero-padded; APIs want 346
        ("F9 1601", "F9", 1601),   # letter+digit carrier
        ("  ua  1377 ", "UA", 1377),
    ],
)
def test_the_shapes_that_are_in_the_table(raw, carrier, number):
    d = fc.parse_designator(raw)
    assert d is not None
    assert (d.carrier, d.number) == (carrier, number)


def test_sw_is_not_southwest_and_becomes_wn():
    """Two of the owner's rides say SW. Southwest is WN; SW was somebody else. Left
    alone it is a lookup that returns nothing, forever, without an error."""
    assert fc.parse_designator("SW 1197").carrier == "WN"
    assert fc.parse_designator("SW4639").carrier == "WN"


def test_a_bare_number_keeps_the_number_and_admits_it_has_no_airline():
    """Six rides are digits only, two of them still upcoming. There is a 976 at every
    carrier, so the one thing this must never do is pick one."""
    d = fc.parse_designator("976")
    assert d is not None
    assert d.number == 976
    assert d.carrier is None
    assert d.airline is None
    assert d.needs_airline is True
    assert d.code == "976"


def test_an_airline_name_in_front_of_the_code_is_stripped():
    """test_booking_api asserts this exact string survives a round-trip, so it is a
    value the parser will meet."""
    d = fc.parse_designator("United Airlines UA 2766")
    assert (d.carrier, d.number) == ("UA", 2766)
    assert d.airline == "United Airlines"


def test_an_airline_spelled_out_resolves_from_its_name():
    """Scanning loosely would read SOUTHWEST 1197 as flight ST 1197 — two letters and a
    number, an airline that does not exist. The name has to win."""
    assert fc.parse_designator("Southwest 1197").carrier == "WN"
    assert fc.parse_designator("Air Canada 542").carrier == "AC"


def test_an_airline_with_no_number_is_not_a_flight():
    """Mirror of the rule smart.py already enforces in the other direction."""
    assert fc.parse_designator("United") is None
    assert fc.parse_designator("flying Southwest") is None


@pytest.mark.parametrize("raw", [None, "", "   ", "n/a"])
def test_nothing_in_the_field_is_nothing(raw):
    assert fc.parse_designator(raw) is None


def test_an_unknown_carrier_code_is_kept_rather_than_dropped():
    """The provider knows more airlines than this file does. A code we cannot name is
    still a usable identifier — refusing it would silently hide a real flight."""
    d = fc.parse_designator("ZZ 1234")
    assert (d.carrier, d.number) == ("ZZ", 1234)
    assert d.airline is None


def test_the_code_property_is_what_the_screen_prints():
    assert fc.parse_designator("UA1377").code == "UA 1377"
    assert fc.parse_designator("3660").code == "3660"


# ── direction ───────────────────────────────────────────────────────────────────


def test_picking_up_at_the_airport_is_an_arrival():
    assert fc.direction(pickup_airport=True, dropoff_airport=False) == fc.ARRIVAL


def test_dropping_off_at_the_airport_is_a_departure():
    assert fc.direction(pickup_airport=False, dropoff_airport=True) == fc.DEPARTURE


def test_an_airport_transfer_follows_the_onward_departure():
    assert fc.direction(pickup_airport=True, dropoff_airport=True) == fc.DEPARTURE


def test_a_ride_that_never_touches_an_airport_has_no_direction():
    """A flight number typed on a city ride is a note, not a schedule. It stays off
    this screen rather than being sorted by an hour that means nothing."""
    assert fc.direction(pickup_airport=False, dropoff_airport=False) is None
