"""Client = a passenger of a tenant. Created on first Google sign-in (or added
manually by the driver). Tenant-scoped; identified by google_sub or email."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "google_sub", name="uq_client_tenant_google_sub"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lang: Mapped[str | None] = mapped_column(String(2), nullable=True)  # preferred EN | ES
    # Saved home/base address — prefilled as the pickup on the Add-ride form. When
    # unset the route is inferred from the client's ride history.
    home_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    sms_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    email_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Standing ride preferences (conversation/temperature/music/luggage/pet/notes).
    # JSONB so the option set can grow without a migration; shape is validated by the
    # RidePreferences schema in services/profile.py before it is ever persisted.
    ride_preferences: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
