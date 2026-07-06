"""Web Push subscriptions (PWA notifications).

One row per browser/device push endpoint. Tenant-scoped like everything else.

``audience`` distinguishes the two push audiences that share this table:
- ``"staff"`` — a driver/owner device; receives the dashboard-bell events.
- ``"client"`` — a passenger device (``client_id`` set); receives ride events.

The endpoint URL is globally unique (the browser mints one per subscription), so
it is the natural upsert key: re-subscribing the same device refreshes its keys
instead of piling up duplicate rows. Dead endpoints are pruned lazily when a push
comes back 404/410 (see ``services/push.py``).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # "staff" (driver/owner) or "client" (passenger). Kept as a plain string — not a
    # pg enum — so adding an audience later needs no migration.
    audience: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Set only for client subscriptions; NULL for staff.
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The push endpoint + its keys, exactly as the browser's PushSubscription reports.
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    ua: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
