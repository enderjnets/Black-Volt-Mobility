"""Client = a passenger of a tenant. Created on first Google sign-in (or added
manually by the driver). Tenant-scoped; identified by google_sub or email."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
