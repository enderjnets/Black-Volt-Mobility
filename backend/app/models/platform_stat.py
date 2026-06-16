"""Platform stats import — a driver's Uber/Lyft/Co-op earnings summary, read from
an uploaded screenshot by the AI vision model and saved for context.

These are NOT private (Black Volt) rides — they're the driver's gig-platform
activity, stored so the My Stats tab can show platform income/trips over time and
compare it against private income (the whole pitch: convert those riders to
higher-margin private clients). Tenant-scoped; never feeds the sales funnel."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformStat(Base):
    __tablename__ = "platform_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # uber | lyft | coop | other
    platform: Mapped[str] = mapped_column(String(20), default="other")
    # Human period label from the screenshot (e.g. "Jun 9–15", "This week").
    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    trips: Mapped[int | None] = mapped_column(Integer, nullable=True)
    earnings: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
