"""Tiny in-memory sliding-window rate limiter for abuse-prone public endpoints.

Single-process by design (the backend runs one uvicorn worker); swap for a
Redis-backed equivalent before scaling horizontally. The clock is injectable
so tests never sleep."""
from __future__ import annotations

import time

_hits: dict[str, list[float]] = {}


def allow(key: str, *, limit: int, window_seconds: float, now: float | None = None) -> bool:
    """Record an attempt under `key`; True while under `limit` per window."""
    ts = time.monotonic() if now is None else now
    bucket = [t for t in _hits.get(key, []) if ts - t < window_seconds]
    if len(bucket) >= limit:
        _hits[key] = bucket
        return False
    bucket.append(ts)
    _hits[key] = bucket
    return True


def reset() -> None:
    """Test hook: drop all counters."""
    _hits.clear()
