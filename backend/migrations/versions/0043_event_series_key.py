"""Event series_key: group the dates of one show under a single public page

Adds events.series_key (nullable, indexed) and backfills it for every existing event from the
same base slug the approve flow builds (performer/title - venue_key - Denver year). Two nights of
the same act at the same venue in the same year end up sharing one key, so the public site can
render ONE landing with a date selector instead of one page per date. NULL = ungrouped (stands
alone), which is exactly today's behaviour for anything that doesn't match a sibling.

Revision ID: 0043_event_series_key
Revises: 0042_event_deposit
Create Date: 2026-07-10
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "0043_event_series_key"
down_revision = "0042_event_deposit"
branch_labels = None
depends_on = None

_DENVER = ZoneInfo("America/Denver")


def _slugify(s: str | None) -> str:
    """Inline copy of events._slugify — migrations must not import app code, and this must stay
    byte-for-byte identical to it (and to events.series_key_for)."""
    out = "".join(c.lower() if c.isalnum() else "-" for c in (s or ""))
    return "-".join(p for p in out.split("-") if p)[:70] or "event"


def _series_key(performer: str | None, title: str | None, venue_key: str | None, starts_at) -> str:
    when = starts_at
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    year = when.astimezone(_DENVER).year if when is not None else 0
    return _slugify(
        f"{performer or title or 'event'}-{(venue_key or 'denver').replace('_', '-')}-{year}"
    )


def upgrade() -> None:
    op.add_column("events", sa.Column("series_key", sa.String(length=80), nullable=True))
    op.create_index("ix_events_series_key", "events", ["series_key"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, title, performer, venue_key, starts_at "
            "FROM events WHERE series_key IS NULL"
        )
    ).fetchall()
    for r in rows:
        key = _series_key(r.performer, r.title, r.venue_key, r.starts_at)
        bind.execute(
            sa.text("UPDATE events SET series_key = :k WHERE id = :i"),
            {"k": key, "i": r.id},
        )


def downgrade() -> None:
    op.drop_index("ix_events_series_key", table_name="events")
    op.drop_column("events", "series_key")
