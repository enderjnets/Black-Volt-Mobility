"""Featured events: scanner suggestions + approved/published event landing pages.

`EventSuggestion` rows are produced by the daily scanner (SeatGeek + Ticketmaster).
When the admin approves one, an `Event` row is created that drives a public landing
page at `/events/<slug>`. Both live under the owner tenant (single-brand public site).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Scanner suggestion lifecycle.
SUGGESTION_STATUSES = ("suggested", "approved", "dismissed")
# Published-event lifecycle.
EVENT_STATUSES = ("draft", "published", "archived")


class EventSuggestion(Base):
    """A candidate event surfaced by the scanner, awaiting admin approval/dismissal."""

    __tablename__ = "event_suggestions"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_event_suggestion_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(16))  # seatgeek | ticketmaster
    source_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    performer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    venue_name: Mapped[str] = mapped_column(String(160))
    venue_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    venue_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    venue_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_mi: Mapped[float | None] = mapped_column(Float, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="suggested", server_default="suggested"
    )
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Event(Base):
    """An approved event with a public landing page."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_suggestions.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    performer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    venue_key: Mapped[str] = mapped_column(
        String(40), default="generic", server_default="generic"
    )
    venue_name: Mapped[str] = mapped_column(String(160))
    venue_address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    doors_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hero_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    about_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tips_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    event_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Event pricing (per-event surcharges over the base zone/metered fare) ---
    event_fee: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    night_fee: Mapped[float] = mapped_column(Float, default=25.0, server_default="25")
    night_cutoff: Mapped[str] = mapped_column(String(5), default="21:00", server_default="21:00")
    wait_fee_per_hour: Mapped[float] = mapped_column(Float, default=30.0, server_default="30")
    est_duration_hours: Mapped[float] = mapped_column(Float, default=3.0, server_default="3")
    round_trip_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pricing_research: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Groups the dates of one show (e.g. two Red Rocks nights) so the public site can render a
    # single page with a date selector instead of one landing per date. NULL = ungrouped (stands
    # alone). Derived from the base slug (performer-venue-year); see events.series_key_for.
    series_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
