"""Booking API: quote, rides CRUD, rate-config, place autocomplete.

Tenant-scoped throughout. `/quote`, `/rate-config` (GET) and `/places/autocomplete`
are open (they back a public price calculator); writes and the rides list require
a session (passengers see only their own rides; staff see all)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_payload, require_auth, require_staff, resolve_tenant_id
from app.db.base import get_db
from app.models import Ride, RideStatus
from app.services import auth, booking, maps

router = APIRouter(tags=["booking"])


# ─── Schemas ────────────────────────────────────────────────────────────────
class QuoteRequest(BaseModel):
    pickup: str = Field(min_length=1, max_length=400)
    dropoff: str = Field(min_length=1, max_length=400)
    stops: list[str] | None = None
    pax: int | None = Field(default=None, ge=1, le=12)
    scheduled_at: datetime | None = None
    is_loyalty: bool = False
    is_peak: bool | None = None


class RideCreate(QuoteRequest):
    client_id: int | None = None
    passenger_name: str | None = Field(default=None, max_length=200)
    passenger_phone: str | None = Field(default=None, max_length=40)
    flight_number: str | None = Field(default=None, max_length=20)
    lang: str | None = Field(default=None, max_length=2)
    notes: str | None = None
    vehicle: str | None = Field(default=None, max_length=120)
    fare_override: float | None = Field(default=None, ge=0)
    confirm: bool = False  # passenger booking → CONFIRMED, else QUOTED


class StatusPatch(BaseModel):
    status: RideStatus


class RateConfigBody(BaseModel):
    currency: str | None = Field(default=None, max_length=3)
    minimum: float | None = Field(default=None, ge=0)
    base: float | None = Field(default=None, ge=0)
    per_mile: float | None = Field(default=None, ge=0)
    per_minute: float | None = Field(default=None, ge=0)
    airport_flat: float | None = Field(default=None, ge=0)
    extra_stop_fee: float | None = Field(default=None, ge=0)
    group_surcharge: float | None = Field(default=None, ge=0)
    group_threshold: int | None = Field(default=None, ge=1, le=12)
    peak_enabled: bool | None = None
    peak_multiplier: float | None = Field(default=None, ge=1.0, le=5.0)
    loyalty_discount_pct: float | None = Field(default=None, ge=0, le=90)


def _ride_out(r: Ride) -> dict:
    return {
        "id": r.id,
        "status": r.status.value if isinstance(r.status, RideStatus) else r.status,
        "client_id": r.client_id,
        "passenger_name": r.passenger_name,
        "passenger_phone": r.passenger_phone,
        "pickup": r.pickup_text,
        "dropoff": r.dropoff_text,
        "stops": r.stops,
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
        "distance_miles": r.distance_miles,
        "duration_minutes": r.duration_minutes,
        "fare_total": r.fare_total,
        "currency": r.currency,
        "price_breakdown": r.price_breakdown,
        "pax": r.pax,
        "vehicle": r.vehicle,
        "flight_number": r.flight_number,
        "lang": r.lang,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _rate_out(rc) -> dict:
    return {
        "currency": rc.currency,
        "minimum": rc.minimum,
        "base": rc.base,
        "per_mile": rc.per_mile,
        "per_minute": rc.per_minute,
        "airport_flat": rc.airport_flat,
        "extra_stop_fee": rc.extra_stop_fee,
        "group_surcharge": rc.group_surcharge,
        "group_threshold": rc.group_threshold,
        "peak_enabled": rc.peak_enabled,
        "peak_multiplier": rc.peak_multiplier,
        "loyalty_discount_pct": rc.loyalty_discount_pct,
    }


# ─── Quote (open) ─────────────────────────────────────────────────────────────
@router.post("/quote")
async def post_quote(body: QuoteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Price a candidate trip without persisting. Backs the booking calculator."""
    tenant_id = await resolve_tenant_id(db, current_payload(request))
    return await booking.build_quote(
        db,
        tenant_id=tenant_id,
        pickup=body.pickup,
        dropoff=body.dropoff,
        stops=body.stops,
        pax=body.pax,
        scheduled_at=body.scheduled_at,
        is_loyalty=body.is_loyalty,
        is_peak=body.is_peak,
    )


@router.get("/places/autocomplete")
async def places_autocomplete(q: str = Query(min_length=1, max_length=200)):
    """Address suggestions for pickup/dropoff inputs."""
    out = await maps.autocomplete(q)
    return {"suggestions": [{"description": s.description, "place_id": s.place_id} for s in out]}


# ─── Rate config ──────────────────────────────────────────────────────────────
@router.get("/rate-config")
async def get_rate_config(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = await resolve_tenant_id(db, current_payload(request))
    rc = await booking.get_or_create_rate_config(db, tenant_id=tenant_id)
    return _rate_out(rc)


@router.put("/rate-config")
async def put_rate_config(
    body: RateConfigBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    rc = await booking.update_rate_config(
        db, tenant_id=tenant_id, changes=body.model_dump(exclude_none=True)
    )
    return _rate_out(rc)


# ─── Rides ────────────────────────────────────────────────────────────────────
@router.post("/rides", status_code=status.HTTP_201_CREATED)
async def create_ride(
    body: RideCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Create a ride. Passengers book for themselves (client_id pinned from the
    session, status CONFIRMED); staff create manual rides (status QUOTED unless
    confirm=true)."""
    tenant_id = await resolve_tenant_id(db, payload)
    is_passenger = payload.get("role") == auth.ROLE_PASSENGER
    client_id = payload.get("cid") if is_passenger else body.client_id
    ride_status = RideStatus.CONFIRMED if (is_passenger or body.confirm) else RideStatus.QUOTED
    ride = await booking.create_ride(
        db,
        tenant_id=tenant_id,
        pickup=body.pickup,
        dropoff=body.dropoff,
        stops=body.stops,
        client_id=client_id,
        passenger_name=body.passenger_name,
        passenger_phone=body.passenger_phone,
        pax=body.pax,
        scheduled_at=body.scheduled_at,
        flight_number=body.flight_number,
        lang=body.lang,
        notes=body.notes,
        vehicle=body.vehicle,
        is_loyalty=body.is_loyalty,
        is_peak=body.is_peak,
        status=ride_status,
        fare_override=body.fare_override,
    )
    return _ride_out(ride)


@router.get("/rides")
async def list_rides(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
    status_filter: RideStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Staff: all tenant rides. Passenger: only their own."""
    tenant_id = await resolve_tenant_id(db, payload)
    rides = await booking.list_rides(db, tenant_id=tenant_id, status=status_filter, limit=limit)
    if payload.get("role") == auth.ROLE_PASSENGER:
        cid = payload.get("cid")
        rides = [r for r in rides if r.client_id == cid]
    return {"rides": [_ride_out(r) for r in rides]}


@router.get("/rides/{ride_id}")
async def get_ride(
    ride_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if payload.get("role") == auth.ROLE_PASSENGER and ride.client_id != payload.get("cid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _ride_out(ride)


@router.patch("/rides/{ride_id}")
async def patch_ride_status(
    ride_id: int,
    body: StatusPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.set_ride_status(
        db, tenant_id=tenant_id, ride_id=ride_id, status=body.status
    )
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    return _ride_out(ride)
