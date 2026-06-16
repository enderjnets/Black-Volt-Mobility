"""Driver sales-funnel tracking (the "My Stats" tab).

The driver converts Uber/Lyft riders into private clients by pitching a better
deal in the car. Those conversations happen off-platform, so the *top* of the
funnel is logged by hand (one quick row per day): how many people they talked to,
how many got the pitch, how many took their contact. The *bottom* of the funnel
(clients won, rides, revenue) is derived from real Client/Ride data — never typed.

Both tables are tenant-scoped so each driver only ever sees their own numbers.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DriverFunnelLog(Base):
    __tablename__ = "driver_funnel_logs"
    # One row per driver per day (upsert by date).
    __table_args__ = (
        UniqueConstraint("tenant_id", "log_date", name="uq_funnel_log_tenant_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    log_date: Mapped[date] = mapped_column(Date, index=True)

    # The funnel's logged top — counts for that day.
    conversations: Mapped[int] = mapped_column(Integer, default=0)  # people talked to
    pitches: Mapped[int] = mapped_column(Integer, default=0)        # offered the service
    contacts: Mapped[int] = mapped_column(Integer, default=0)       # took the driver's contact

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DriverGoal(Base):
    __tablename__ = "driver_goals"
    # One goal row per tenant.
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_driver_goal_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    # Optional targets the goal calculator works back from.
    target_weekly_revenue: Mapped[float | None] = mapped_column(nullable=True)
    target_monthly_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Days per week the driver actually works (spreads required activity).
    working_days_per_week: Mapped[int] = mapped_column(Integer, default=5)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
