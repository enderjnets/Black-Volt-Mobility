"""Reading the free text in ``rides.flight_number``.

The column is ``String(40)`` and has never been validated: a widening migration is
literally titled "airline name + number", and a booking test asserts that
``"United Airlines UA 2766"`` round-trips verbatim. Production holds seven shapes of the
same idea — ``UA 1377``, ``UA2085``, ``DL 0346``, ``WN 3018``, ``WN203``, ``SW 1197`` and
six entries that are nothing but digits.

Everything downstream needs one answer to two questions: which airline, and which number.
A number with no airline is not a flight — there is a 976 at every carrier — so this
module never guesses one. It reports the gap and lets the screen ask.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ARRIVAL = "arrival"
DEPARTURE = "departure"

# IATA → the name a driver would recognise. Carriers with a real presence at DEN plus the
# few the owner's own history names. The ICAO designator each one also has is deliberately
# absent: AeroAPI prefers it over IATA, and a wrong ICAO returns 404 for every flight of
# that airline in silence — it gets seeded from the provider's own response in Phase B,
# never from recall.
AIRLINES: dict[str, str] = {
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "DL": "Delta Air Lines",
    "AA": "American Airlines",
    "AS": "Alaska Airlines",
    "F9": "Frontier Airlines",
    "NK": "Spirit Airlines",
    "B6": "JetBlue",
    "SY": "Sun Country Airlines",
    "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines",
    "AC": "Air Canada",
    "LH": "Lufthansa",
    "BA": "British Airways",
    "AM": "Aeroméxico",
    "VB": "Viva Aerobus",
    "Y4": "Volaris",
}

# Codes people write that are not the carrier's IATA code. "SW" for Southwest appears
# twice in the owner's own rides; Southwest is WN, and SW belonged to other airlines.
ALIASES: dict[str, str] = {"SW": "WN", "SWA": "WN", "UAL": "UA", "DAL": "DL", "AAL": "AA"}

# Airline written by name instead of code ("Southwest 1197"). Lower-case, longest match
# first at lookup time so "air canada" beats "air".
NAMES: dict[str, str] = {
    "united": "UA",
    "southwest": "WN",
    "delta": "DL",
    "american": "AA",
    "alaska": "AS",
    "frontier": "F9",
    "spirit": "NK",
    "jetblue": "B6",
    "sun country": "SY",
    "allegiant": "G4",
    "hawaiian": "HA",
    "air canada": "AC",
    "lufthansa": "LH",
    "british airways": "BA",
    "aeromexico": "AM",
    "volaris": "Y4",
}

# Two characters, in the shapes IATA actually issues: LL, L9, 9L.
_CODE = r"(?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z])"
_WHOLE = re.compile(rf"^({_CODE})\s?([0-9]{{1,4}})$")
_DIGITS = re.compile(r"^([0-9]{1,4})$")
_EMBEDDED = re.compile(rf"\b({_CODE})\s?([0-9]{{1,4}})\b")
_TRAILING_NUMBER = re.compile(r"\b([0-9]{1,4})\b\s*$")


@dataclass(frozen=True)
class Designator:
    """One flight number, as far as it could be resolved."""

    number: int
    carrier: str | None = None
    raw: str = ""

    @property
    def airline(self) -> str | None:
        return AIRLINES.get(self.carrier) if self.carrier else None

    @property
    def code(self) -> str:
        """What the screen prints: ``UA 1377``, or the bare number when unresolved."""
        return f"{self.carrier} {self.number}" if self.carrier else str(self.number)

    @property
    def needs_airline(self) -> bool:
        return self.carrier is None


def _carrier(code: str) -> str | None:
    """An alias resolves to its real IATA code; an unknown code stays as written.

    A code we have no name for is still a usable identifier — the provider knows more
    airlines than this file does, and refusing it would drop a valid flight.
    """
    code = ALIASES.get(code, code)
    return code or None


def parse_designator(raw: str | None) -> Designator | None:
    """Free text → airline + number, or ``None`` when there is no number in it at all.

    Order matters. The whole-string forms are tried first because they are the common
    case and the only ones that cannot be ambiguous; only then does it look inside a
    longer string, and only for a code it recognises — scanning loosely turns
    ``"Southwest 1197"`` into flight ST 1197, an airline that does not exist.
    """
    if not raw:
        return None
    s = re.sub(r"\s+", " ", raw.strip().upper())
    if not s:
        return None

    m = _WHOLE.match(s)
    if m:
        return Designator(number=int(m.group(2)), carrier=_carrier(m.group(1)), raw=raw)

    m = _DIGITS.match(s)
    if m:
        return Designator(number=int(m.group(1)), raw=raw)

    # A code inside a longer string, e.g. "United Airlines UA 2766". Only a code this
    # module knows counts, and the last one wins: an airline name can hide a two-letter
    # sequence, but it cannot hide a known code followed by a flight number.
    found = [hit for hit in _EMBEDDED.finditer(s) if (_carrier(hit.group(1)) or "") in AIRLINES]
    if found:
        last = found[-1]
        return Designator(number=int(last.group(2)), carrier=_carrier(last.group(1)), raw=raw)

    # An airline spelled out, with its number somewhere after it.
    num = _TRAILING_NUMBER.search(s)
    if num is None:
        return None
    low = s.lower()
    for name in sorted(NAMES, key=len, reverse=True):
        if name in low:
            return Designator(number=int(num.group(1)), carrier=NAMES[name], raw=raw)
    return Designator(number=int(num.group(1)), raw=raw)


def direction(*, pickup_airport: bool, dropoff_airport: bool) -> str | None:
    """Which end of the trip the flight is on.

    Picking up at the airport means the passenger is landing, so the flight's arrival is
    the hour that matters; dropping off there means they are leaving and the departure is.
    Neither end an airport: the flight number is a note, not a schedule, and the row stays
    off this screen. Both ends: an airport transfer, where the onward departure governs.

    Takes booleans rather than addresses so this module stays free of settings and I/O —
    the caller decides with ``booking._airportish``, the word-boundary test, because the
    substring one matches Garden, Golden and Hidden.
    """
    if pickup_airport and dropoff_airport:
        return DEPARTURE
    if pickup_airport:
        return ARRIVAL
    if dropoff_airport:
        return DEPARTURE
    return None
