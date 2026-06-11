"""Sliding-window limiter unit tests (injected clock — no sleeps)."""
from app.services import ratelimit


def setup_function():
    ratelimit.reset()


def test_allows_up_to_limit_then_blocks():
    for i in range(3):
        assert ratelimit.allow("k", limit=3, window_seconds=60, now=float(i)) is True
    assert ratelimit.allow("k", limit=3, window_seconds=60, now=3.0) is False


def test_window_slides():
    for i in range(3):
        assert ratelimit.allow("k", limit=3, window_seconds=60, now=float(i)) is True
    assert ratelimit.allow("k", limit=3, window_seconds=60, now=61.5) is True


def test_keys_are_independent():
    assert ratelimit.allow("a", limit=1, window_seconds=60, now=0.0) is True
    assert ratelimit.allow("b", limit=1, window_seconds=60, now=0.0) is True
    assert ratelimit.allow("a", limit=1, window_seconds=60, now=1.0) is False
