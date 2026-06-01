"""AnalyticsEvent = one first-party usage event (pageview, page_duration,
booking-funnel step, sign-in, …). Tenant-scoped. Pseudonymous: visitor_id is a
random client id, no raw IP is stored (country comes from Cloudflare's
CF-IPCountry header). event_type is a plain string (not an enum) so new event
kinds need no migration."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Known event types (documentation only — column is free-form String).
EVENT_TYPES = (
    "session_start",
    "pageview",
    "page_duration",
    "book_start",
    "book_review",
    "book_pay",
    "book_confirmed",
    "sign_in",
    "address_pick",
    "lang_switch",
    "cta_click",
)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    visitor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)  # owner|passenger|anon
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(400), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device: Mapped[str | None] = mapped_column(String(12), nullable=True)  # mobile|tablet|desktop
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)  # ISO-2 (CF-IPCountry)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    props: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
