"""'Where to wait' — the owner's Uber history, one-tap shift log, static priors and
computed scores. Everything the driver produces is tenant-scoped; `hex_priors` and
`den_flight_baseline` are geography/airport facts shared by all tenants.

Spec: docs/superpowers/specs/2026-09-17-black-demand-heatmap-design.md
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class UberProduct(str, enum.Enum):
    BLACK_SUV = "black_suv"
    BLACK = "black"
    COMFORT = "comfort"
    X = "x"
    XL = "xl"
    OTHER = "other"


class EarnerState(str, enum.Enum):
    OPEN = "open"          # online, waiting for a request → the exposure we measure
    ENROUTE = "enroute"    # accepted, driving to the pickup
    ONTRIP = "ontrip"
    OFFLINE = "offline"


class SegmentSource(str, enum.Enum):
    EXPORT = "export"
    LIVE = "live"
    GPS = "gps"


def _tenant_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class UberTrip(Base):
    """One trip from the Uber driver data export (`driver_lifetime_trips`)."""

    __tablename__ = "uber_trips"
    __table_args__ = (UniqueConstraint("tenant_id", "dedup_key", name="uq_uber_trips_dedup"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    # The export has no trip UUID: sha256 of request_at|begin_at|fare_total|distance_mi.
    dedup_key: Mapped[str] = mapped_column(String(64))
    product: Mapped[UberProduct] = mapped_column(pg_enum(UberProduct, name="uber_product"))
    product_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    begin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dropoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Filled by the GPS import (Task 15) or the 2022 export format; null otherwise.
    begin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    begin_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_airport: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    fare_total: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    surge_multiplier: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    distance_mi: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DriverStateSegment(Base):
    """A stretch of time in one earner state, with where it began and ended."""

    __tablename__ = "driver_state_segments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedup_key", name="uq_driver_state_segments_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    dedup_key: Mapped[str] = mapped_column(String(80))
    state: Mapped[EarnerState] = mapped_column(pg_enum(EarnerState, name="earner_state"))
    begin_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Null while the live segment is still open; pings only move last_ping_at.
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    begin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    begin_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    h3_r8: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    zone_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[SegmentSource] = mapped_column(pg_enum(SegmentSource, name="segment_source"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OfferEvent(Base):
    """A ride offer the driver saw (live one-tap log only)."""

    __tablename__ = "offer_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_event_id", name="uq_offer_events_client_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    client_event_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    h3_r8: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    product: Mapped[UberProduct] = mapped_column(pg_enum(UberProduct, name="uber_product"))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    fare: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    dest_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DispatchWindow(Base):
    """Per-window offer counts from the export ("Dispatches Offered and Accepted")."""

    __tablename__ = "dispatch_windows"
    __table_args__ = (UniqueConstraint("tenant_id", "dedup_key", name="uq_dispatch_windows_dedup"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    dedup_key: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minutes_online: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    minutes_active: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    dispatches: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejections: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expireds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_trips: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class DemandImport(Base):
    """One upload of the Uber export ZIP and what it contained."""

    __tablename__ = "demand_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    summary: Mapped[dict] = mapped_column(JSON)


class HexPrior(Base):
    """Static per-cell geography: affluence, luxury hotels, generators, DEN distance."""

    __tablename__ = "hex_priors"

    h3_r8: Mapped[str] = mapped_column(String(16), primary_key=True)
    affluence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    hotels: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    generators: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    den_distance_mi: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    zone_key: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DenFlightBaseline(Base):
    """Typical DEN departures/arrivals per (month, dow, hour), from BTS On-Time."""

    __tablename__ = "den_flight_baseline"
    __table_args__ = (UniqueConstraint("month", "dow", "hour", name="uq_den_flight_baseline"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer)   # 1-12
    dow: Mapped[int] = mapped_column(Integer)     # 0=Monday … 6=Sunday
    hour: Mapped[int] = mapped_column(Integer)    # 0-23 local
    departures: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # avg per day
    arrivals: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    source_period: Mapped[str | None] = mapped_column(String(40), nullable=True)


class WeekScore(Base):
    """Latest 7×24 planner grid per tenant and zone."""

    __tablename__ = "week_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    zone_key: Mapped[str] = mapped_column(String(40), index=True)
    dow: Mapped[int] = mapped_column(Integer)
    hour: Mapped[int] = mapped_column(Integer)
    mean: Mapped[float] = mapped_column(Float)      # offers per minute
    lo: Mapped[float] = mapped_column(Float)
    hi: Mapped[float] = mapped_column(Float)
    own_share: Mapped[float] = mapped_column(Float)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class HexScore(Base):
    """Per-cell scores per 15-minute slot (filled in Phase 2; table created now)."""

    __tablename__ = "hex_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    h3_r8: Mapped[str] = mapped_column(String(16))
    mean: Mapped[float] = mapped_column(Float)
    lo: Mapped[float] = mapped_column(Float)
    hi: Mapped[float] = mapped_column(Float)
    own_share: Mapped[float] = mapped_column(Float)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
