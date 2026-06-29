"""Tenant = a driver/company. MVP has one (Black Volt) but every domain row is
tenant-scoped so the SaaS path needs no rewrite."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Public-profile / brand fields (edited from the dashboard Settings page).
    tagline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vehicle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Direct line shown only to registered clients (gated server-side).
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Brand accent (hex) + uploaded asset paths (served from /media).
    brand_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Public-profile vanity stats the owner sets (rides are computed live).
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    since_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Auto review-request reminder: email a rider this many hours after a ride completes.
    # Off by default — the owner opts in from Settings (avoids auto-emailing without consent).
    review_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    review_reminder_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
