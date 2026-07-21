"""In-app passenger notifications (the client bell).

A ``ClientNotification`` is a single event for one passenger (``client_id``): a
message from their driver, or the outcome of a cancelled-ride refund. It mirrors
the staff :class:`Notification` but is addressed to a *client*, not a tenant, so
the passenger site can show its own bell with an unread count. As with the staff
feed the human-readable text is NOT stored — only ``kind`` + a small ``data`` blob
— so the frontend renders it in the viewer's language (EN/ES) from i18n templates.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class ClientNotificationKind(str, enum.Enum):
    ride_message = "ride_message"
    refund_full = "refund_full"
    refund_partial = "refund_partial"


class ClientNotification(Base):
    __tablename__ = "client_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[ClientNotificationKind] = mapped_column(
        pg_enum(ClientNotificationKind, name="client_notification_kind"), nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
