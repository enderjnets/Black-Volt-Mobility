"""Phone normalization → E.164 (US default, international allowed)."""
from __future__ import annotations

import pytest

from app.services.phone import InvalidPhoneError, normalize_phone


def test_bare_us_10_digits_gets_plus_1():
    assert normalize_phone("3035550142") == "+13035550142"


def test_us_with_formatting_is_stripped():
    assert normalize_phone("(303) 555-0142") == "+13035550142"
    assert normalize_phone("303.555.0142") == "+13035550142"


def test_us_11_digits_with_leading_1():
    assert normalize_phone("1 303 555 0142") == "+13035550142"


def test_already_e164_us_unchanged():
    assert normalize_phone("+13035550142") == "+13035550142"


def test_valid_international_e164_preserved():
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_empty_or_blank_rejected():
    for bad in ("", "   ", None):
        with pytest.raises(InvalidPhoneError):
            normalize_phone(bad)  # type: ignore[arg-type]


def test_letters_rejected():
    with pytest.raises(InvalidPhoneError):
        normalize_phone("call-me-now")


def test_too_short_rejected():
    with pytest.raises(InvalidPhoneError):
        normalize_phone("12345")


def test_us_invalid_area_code_first_digit_rejected():
    # NANP area code & exchange must start 2-9; "123…" is invalid.
    with pytest.raises(InvalidPhoneError):
        normalize_phone("1234567890")


def test_international_without_plus_is_rejected_as_ambiguous():
    # 12 digits, not a US pattern, no leading + → ambiguous, reject.
    with pytest.raises(InvalidPhoneError):
        normalize_phone("442079460958")


def test_too_long_rejected():
    with pytest.raises(InvalidPhoneError):
        normalize_phone("+1234567890123456")  # 16 digits > E.164 max 15
