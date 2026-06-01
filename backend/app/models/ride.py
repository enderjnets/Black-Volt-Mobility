"""Ride = a booking. Tenant-scoped; may link to a Client (portal) or carry an
ad-hoc passenger (driver-entered manual ride). Route distance/duration come from
services/maps.py; the fare breakdown from services/pricing.py."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class RideStatus(str, enum.Enum):
    REQUESTED = "requested"   # passenger asked; not yet priced
    QUOTED = "quoted"         # priced, awaiting confirmation/payment
    CONFIRMED = "confirmed"   # booked
    ASSIGNED = "assigned"     # driver assigned (single-driver MVP: == confirmed)
    EN_ROUTE = "en_route"     # in progress
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# Statuses an in-progress/open ride can be in (used for list filters).
OPEN_STATUSES = (
    RideStatus.REQUESTED,
    RideStatus.QUOTED,
    RideStatus.CONFIRMED,
    RideStatus.ASSIGNED,
    RideStatus.EN_ROUTE,
)


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[RideStatus] = mapped_column(
        pg_enum(RideStatus, name="ride_status"),
        default=RideStatus.QUOTED,
        index=True,
    )

    # Route — text plus optional geocoded coordinates / place ids.
    pickup_text: Mapped[str] = mapped_column(String(400))
    pickup_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    pickup_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    pickup_place_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dropoff_text: Mapped[str] = mapped_column(String(400))
    dropoff_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_place_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Intermediate stops: [{"text": str, "lat": float|None, "lng": float|None}].
    stops: Mapped[list | None] = mapped_column(JSON, nullable=True)

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Computed route + fare (snapshotted at quote time).
    distance_miles: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    fare_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Full pricing breakdown (line items) as returned by services/pricing.py.
    price_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Trip details.
    pax: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    flight_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lang: Mapped[str | None] = mapped_column(String(2), nullable=True)  # EN | ES
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ad-hoc passenger (manual driver entry without a Client row).
    passenger_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    passenger_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Square payment reference (Phase 3).
    payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
