"""RateConfig = a tenant's configurable fare engine. One row per tenant. Edited
from the dashboard Rates screen; consumed by services/pricing.py. Per-tenant so
the SaaS path lets every driver price their own rides."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Black Volt's starting fares (configurable in the dashboard). Mirrors the
# dashboard Rates defaults: base 12, per-mile 2.4, per-min 0.55, DEN flat 74,
# minimum 28, surge x1.4.
DEFAULT_RATES = {
    "currency": "USD",
    "minimum": 28.0,
    "base": 12.0,
    "per_mile": 2.4,
    "per_minute": 0.55,
    "airport_flat": 74.0,
    "extra_stop_fee": 15.0,
    "group_surcharge": 20.0,
    "group_threshold": 4,
    "peak_enabled": True,
    "peak_multiplier": 1.4,
    "loyalty_discount_pct": 10.0,
}


class RateConfig(Base):
    __tablename__ = "rate_configs"
    # One config per tenant — enforced by a named unique constraint (migration
    # 0002) plus a plain lookup index on tenant_id.
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_rate_config_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Metered components: fare = MAX(floor, base + miles*per_mile + min*per_minute).
    minimum: Mapped[float] = mapped_column(Float, default=28.0)
    base: Mapped[float] = mapped_column(Float, default=12.0)
    per_mile: Mapped[float] = mapped_column(Float, default=2.4)
    per_minute: Mapped[float] = mapped_column(Float, default=0.55)
    # Airport rides use this as the fare floor instead of `minimum` (DEN flat).
    airport_flat: Mapped[float] = mapped_column(Float, default=74.0)

    # Additive surcharges.
    extra_stop_fee: Mapped[float] = mapped_column(Float, default=15.0)
    group_surcharge: Mapped[float] = mapped_column(Float, default=20.0)
    group_threshold: Mapped[int] = mapped_column(Integer, default=4)

    # Multiplicative peak surge (applied after surcharges).
    peak_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    peak_multiplier: Mapped[float] = mapped_column(Float, default=1.4)

    # Loyalty discount (percent off the final fare for returning clients).
    loyalty_discount_pct: Mapped[float] = mapped_column(Float, default=10.0)

    # Per-tenant flat-rate zone price overrides: {zone_key: flat_price}. NULL / missing
    # keys fall back to services.zones.DEFAULT_ZONE_PRICES. Zone geography itself is
    # global (defined in code); only the prices are editable per driver.
    zone_prices: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
