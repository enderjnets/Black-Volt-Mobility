"""Phone normalization to E.164.

The booking operation is US-based (Denver/DIA), so a bare 10-digit number is
assumed to be US (+1). International numbers must be given in `+<country>` form;
a bare non-US number is ambiguous and rejected. The normalized E.164 string is
what we persist — the backend is the source of truth, the frontend only
pre-validates for UX.
"""
from __future__ import annotations

import re

_DIGITS = re.compile(r"\d")
# E.164: leading +, country code starting 1-9, total 8..15 digits.
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class InvalidPhoneError(ValueError):
    """Raised when a phone number cannot be normalized to valid E.164."""


def _us_e164(ten_digits: str) -> str:
    """Validate a 10-digit NANP number and return +1XXXXXXXXXX."""
    area, exchange = ten_digits[0], ten_digits[3]
    if area in "01" or exchange in "01":
        raise InvalidPhoneError("invalid_us_number")
    return "+1" + ten_digits


def normalize_phone(raw: str) -> str:
    """Return the E.164 form of `raw`, or raise InvalidPhoneError.

    - Bare 10 digits → assumed US → +1XXXXXXXXXX
    - 11 digits starting with 1 → US → +1XXXXXXXXXX
    - Already +E.164 → validated and returned (formatting stripped)
    - Bare non-US digits (no +) → ambiguous → rejected
    """
    if not raw or not raw.strip():
        raise InvalidPhoneError("missing_phone")

    has_plus = raw.lstrip().startswith("+")
    digits = "".join(_DIGITS.findall(raw))
    if not digits:
        raise InvalidPhoneError("no_digits")

    if has_plus:
        candidate = "+" + digits
        if digits.startswith("1") and len(digits) == 11:
            return _us_e164(digits[1:])
        if not _E164.match(candidate):
            raise InvalidPhoneError("invalid_e164")
        return candidate

    # No leading "+": only US patterns are unambiguous.
    if len(digits) == 10:
        return _us_e164(digits)
    if len(digits) == 11 and digits.startswith("1"):
        return _us_e164(digits[1:])
    raise InvalidPhoneError("ambiguous_or_invalid")
