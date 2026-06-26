"""Payment = a Square payment tied to a ride. Tenant-scoped. Tracks the
authorize → capture → refund lifecycle and the Square payment id."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class PaymentStatus(str, enum.Enum):
    AUTHORIZED = "authorized"   # funds held, not captured (autocomplete=false)
    CAPTURED = "captured"       # completed/charged
    CANCELED = "canceled"       # authorization voided
    REFUNDED = "refunded"       # captured then refunded
    FAILED = "failed"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    ride_id: Mapped[int | None] = mapped_column(
        ForeignKey("rides.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.AUTHORIZED,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer)  # smallest unit (cents)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    square_payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    square_refund_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Cents actually refunded (None = never refunded). Equals `amount` on a full
    # refund; less than `amount` on a partial refund (e.g. a cancellation fee kept
    # by the driver, where kept = amount - refunded_amount).
    refunded_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    simulated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
