"""Shared Square client factory — ONE source of truth for the payments_live
simulation gate, token, and sandbox/production env, used by both the one-off
payments adapter and the subscriptions adapter (so a cutover change can never
apply to one and silently miss the other)."""
from __future__ import annotations

from app.config import get_settings


def square_client():
    """Async Square client for the configured environment, or None when simulated."""
    settings = get_settings()
    if not settings.payments_live:
        return None
    from square import AsyncSquare
    from square.environment import SquareEnvironment

    env = (
        SquareEnvironment.PRODUCTION
        if settings.SQUARE_ENV == "production"
        else SquareEnvironment.SANDBOX
    )
    return AsyncSquare(token=settings.SQUARE_ACCESS_TOKEN, environment=env)
