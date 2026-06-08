"""AllowedUser — DB-backed access list for the driver dashboard (Google Sign-In).

Each row is an email allowed to sign into the dashboard, with a role
(`admin` = super-admin / `driver` = a friend running their own tenant) and an
`active` flag the super-admin toggles to grant or revoke access without losing
the driver's data. A driver's `tenant_id` is filled the first time they sign in
(their workspace is auto-provisioned then). Bootstrap admins pinned in
GOOGLE_ADMIN_EMAILS are treated as immutable by the API so the owner can't lock
themselves out.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ROLE_ADMIN = "admin"
ROLE_DRIVER = "driver"


class AllowedUser(Base):
    __tablename__ = "allowed_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=ROLE_DRIVER, nullable=False)
    # Access toggle — flip off to revoke dashboard access without deleting the row
    # (the driver's tenant + data survive). Pinned admins are always active.
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # The driver's own tenant. NULL until their first sign-in auto-provisions it.
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    added_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
