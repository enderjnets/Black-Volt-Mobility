"""In-app staff notifications (the dashboard bell).

A ``Notification`` is a single actionable event for a driver tenant: a new ride,
a cancellation, a chat that needs a human, a new review, a redeemed discount, or
a failed subscription charge. Rows are per-tenant (mirroring
``ChatConversation.unread_for_staff``): any active staff of the tenant sees them
and marking one read clears it for the tenant. The human-readable text is NOT
stored — only ``kind`` + a small ``data`` blob — so the frontend renders it in the
viewer's language (EN/ES) from i18n templates.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class NotificationKind(str, enum.Enum):
    ride_new = "ride_new"
    ride_cancelled = "ride_cancelled"
    chat_escalated = "chat_escalated"
    chat_message = "chat_message"
    ride_message = "ride_message"
    ride_assigned = "ride_assigned"
    review_new = "review_new"
    discount_redeemed = "discount_redeemed"
    subscription_payment_failed = "subscription_payment_failed"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[NotificationKind] = mapped_column(
        pg_enum(NotificationKind, name="notification_kind"), nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
