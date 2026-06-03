"""Booking API: quote, rides CRUD, rate-config, place autocomplete.

Tenant-scoped throughout. `/quote`, `/rate-config` (GET) and `/places/autocomplete`
are open (they back a public price calculator); writes and the rides list require
a session (passengers see only their own rides; staff see all)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_payload, require_auth, require_staff, resolve_tenant_id
from app.db.base import get_db
from app.models import PaymentMethod, Ride, RideStatus
from app.services import auth, booking, dashboard, maps

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


class RidePatch(BaseModel):
    status: RideStatus | None = None
    payment_method: PaymentMethod | None = None
    paid: bool | None = None


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
        "payment_method": (
            r.payment_method.value
            if isinstance(r.payment_method, PaymentMethod)
            else r.payment_method
        ),
        "paid": r.paid,
        "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        "google_event_id": r.google_event_id,
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
    names = await dashboard.client_names(
        db, tenant_id=tenant_id, ids=[r.client_id for r in rides]
    )
    out = []
    for r in rides:
        d = _ride_out(r)
        nm, ph = names.get(r.client_id, (None, None)) if r.client_id else (None, None)
        d["client_name"] = nm or r.passenger_name
        d["client_phone"] = ph or r.passenger_phone
        out.append(d)
    return {"rides": out}


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
    out = _ride_out(ride)
    out.update(await dashboard.ride_detail_extra(db, tenant_id=tenant_id, ride=ride))
    return out


@router.patch("/rides/{ride_id}")
async def patch_ride(
    ride_id: int,
    body: RidePatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Driver updates a ride: status and/or payment method + paid flag.
    Setting paid=true stamps paid_at; the driver can record cash/Venmo/Zelle."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if body.status is not None:
        # Cancelled/no-show rides leave the calendar.
        if body.status in (RideStatus.CANCELLED, RideStatus.NO_SHOW) and ride.google_event_id:
            from app.services import calendar

            calendar.delete_event(ride.google_event_id)
            ride.google_event_id = None
        ride.status = body.status
    if body.payment_method is not None:
        ride.payment_method = body.payment_method
    if body.paid is not None:
        ride.paid = body.paid
        if body.paid and ride.paid_at is None:
            ride.paid_at = datetime.now(UTC)
        if not body.paid:
            ride.paid_at = None
    await db.commit()
    await db.refresh(ride)
    return _ride_out(ride)
