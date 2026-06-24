"""CalendarCredential — a team member's own Google Calendar OAuth connection.

When a non-admin member links their Google Calendar (authorization-code flow,
scope ``calendar.events``), we store their refresh token **encrypted at rest**
(Fernet, see ``app.services.crypto``) keyed by their tenant. Ride sync then
routes that tenant's events to this member's calendar instead of the shared
Black Volt calendar. One row per tenant (the member's own workspace).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CalendarCredential(Base):
    __tablename__ = "calendar_credential"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One connection per tenant (the member's own workspace). Cascade so removing
    # a tenant drops its stored token.
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    # Google OAuth refresh token, ENCRYPTED (never plaintext). Decrypt only at the
    # moment of use to build a short-lived access token.
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # The connected Google account email — shown in the UI; not used as a secret.
    google_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # Target calendar; "primary" is the member's main calendar.
    calendar_id: Mapped[str] = mapped_column(String(254), default="primary", nullable=False)
    scopes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
