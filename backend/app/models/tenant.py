"""Tenant = a driver/company. MVP has one (Black Volt) but every domain row is
tenant-scoped so the SaaS path needs no rewrite."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Public-profile / brand fields (extended in later phases).
    tagline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vehicle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
