"""Subscription = a driver's recurring Square subscription to a Black Volt SaaS
plan (e.g. Operator). Tenant-scoped: an active row marks the tenant as paid,
which unlocks the paid-plan entitlements (AI features + public profile).

`email` is the subscriber's address; it's kept on the row so a brand-new driver
(who has no session yet when they subscribe from the landing) can be deduplicated
without a separate identity lookup."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"        # paid + current
    PAST_DUE = "past_due"    # payment failed, grace period
    CANCELED = "canceled"    # ended
    # Square returned the subscription but the first charge hasn't settled —
    # NOT yet entitled. Appended last to mirror ALTER TYPE ADD VALUE order.
    PENDING = "pending"


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        # One OPEN (non-canceled) subscription per email+plan — the DB enforces
        # idempotency under concurrency; app-level SELECT-then-INSERT can race.
        Index(
            "uq_subscriptions_email_plan_open",
            "email",
            "plan_key",
            unique=True,
            postgresql_where=text("status != 'canceled'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    plan_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[SubscriptionStatus] = mapped_column(
        pg_enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.ACTIVE,
    )
    square_subscription_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    square_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    simulated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
