"""A passenger's saved address-book entry. Tenant- and client-scoped. Exactly
one default per client is enforced in the service layer (see app/services/
addresses.py) — never two, never zero while rows remain."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientAddress(Base):
    __tablename__ = "client_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str] = mapped_column(String(400), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
