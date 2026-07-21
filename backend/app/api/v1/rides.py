"""Booking API: quote, rides CRUD, rate-config, place autocomplete.

Tenant-scoped throughout. `/quote`, `/rate-config` (GET) and `/places/autocomplete`
are open (they back a public price calculator); writes and the rides list require
a session (passengers see only their own rides; staff see all)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_payload, require_auth, require_staff, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.models import (
    ClientNotificationKind,
    NotificationKind,
    PaymentMethod,
    Ride,
    RideMessageSender,
    RideStatus,
)
from app.services import (
    auth,
    booking,
    dashboard,
    email,
    event_pricing,
    maps,
    notifications,
    payments,
    payments_square,
    profile,
    push,
    smart,
    subscriptions,
    zones,
)
from app.services import (
    legal as legal_svc,
)
from app.services import (
    ride_messages as ride_messages_svc,
)
from app.services.discounts import DiscountError

# Vision providers accept these; anything else is rejected before the model call.
# The frontend normalizes images to PNG/JPEG first, so HEIC/HEIF rarely reach here
# — accepted as a safety net (and a clearer error than a silent drop otherwise).
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per image (MiniMax-M3 limit)

router = APIRouter(tags=["booking"])


# ─── Schemas ────────────────────────────────────────────────────────────────
def _normalize_lang(v):
    """Coerce any language input (incl. AI "Spanish"/"español") to EN|ES so a
    long/loose value never 422s the request. None stays None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    return "ES" if s.startswith(("es", "sp")) else "EN"


class QuoteRequest(BaseModel):
    pickup: str = Field(min_length=1, max_length=400)
    dropoff: str = Field(min_length=1, max_length=400)
    stops: list[str] | None = None
    pax: int | None = Field(default=None, ge=1, le=12)
    scheduled_at: datetime | None = None
    is_loyalty: bool = False
    is_peak: bool | None = None
    discount_code: str | None = None
    round_trip: bool = False
    return_at: datetime | None = None


class RideCreate(QuoteRequest):
    client_id: int | None = None
    passenger_name: str | None = Field(default=None, max_length=200)
    passenger_phone: str | None = Field(default=None, max_length=40)
    flight_number: str | None = Field(default=None, max_length=40)
    lang: str | None = None
    notes: str | None = None
    vehicle: str | None = Field(default=None, max_length=120)
    fare_override: float | None = Field(default=None, ge=0)
    # Optional per-ride preference overrides; validated/defaulted by the schema.
    ride_preferences: profile.RidePreferences | None = None
    confirm: bool = False  # passenger booking → CONFIRMED, else QUOTED
    # Rider accepted the event reservation terms (deposit + 48h refund). Turns an event round
    # trip into a deposit reservation (1/3 now, balance day-of). Ignored for non-event trips.
    terms_accepted: bool = False

    _norm_lang = field_validator("lang", mode="before")(_normalize_lang)


class RideEdit(BaseModel):
    """Editable ride fields (Smart update / change of plans)."""
    pickup: str | None = Field(default=None, min_length=1, max_length=400)
    dropoff: str | None = Field(default=None, min_length=1, max_length=400)
    stops: list[str] | None = None
    scheduled_at: datetime | None = None
    pax: int | None = Field(default=None, ge=1, le=12)
    flight_number: str | None = Field(default=None, max_length=40)
    notes: str | None = None
    lang: str | None = None
    fare_override: float | None = Field(default=None, ge=0)

    _norm_lang = field_validator("lang", mode="before")(_normalize_lang)


class RidePatch(RideEdit):
    status: RideStatus | None = None
    payment_method: PaymentMethod | None = None
    paid: bool | None = None
    # Gratuity recorded manually post-ride. tip=0 is an explicit "clear" (0 != None,
    # so it survives exclude_none). tip_method may differ from payment_method.
    tip: float | None = Field(default=None, ge=0)
    tip_method: PaymentMethod | None = None


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
    # Per-tenant flat-rate zone price overrides {zone_key: price}. Keys must be known
    # zones; the client sends the full effective map on save.
    zone_prices: dict[str, float] | None = None

    @field_validator("zone_prices")
    @classmethod
    def _check_zone_prices(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        cleaned: dict[str, float] = {}
        for key, price in v.items():
            if key not in zones.DEFAULT_ZONE_PRICES:
                raise ValueError(f"unknown zone: {key}")
            if price is None:
                continue
            if price < 0:
                raise ValueError("zone price must be >= 0")
            # Store only deviations: the Rates editor round-trips the full effective map,
            # and persisting default-equal entries would pin every zone forever — future
            # zones.py recalibrations would silently stop reaching this tenant.
            if float(price) == zones.DEFAULT_ZONE_PRICES[key]:
                continue
            cleaned[key] = float(price)
        return cleaned


# Statuses a passenger may self-cancel from (before the driver is en route).
_CANCELLABLE_BY_RIDER = (RideStatus.QUOTED, RideStatus.CONFIRMED, RideStatus.ASSIGNED)
# A cancellation fee may be charged only when the rider cancels <24h before pickup.
_CANCELLATION_FEE_WINDOW = timedelta(hours=24)
# Event rides commit the driver's whole evening: full refund only 72h+ out, else 50%.
_EVENT_CANCELLATION_FEE_WINDOW = timedelta(hours=72)
_EVENT_CANCELLATION_FEE_PCT = 50
# Event DEPOSIT reservations: fully refundable up to 48h before the event, then the deposit is
# kept in full (the driver reserved the night). 100 = deposit non-refundable, 0 = full refund.
_DEPOSIT_REFUND_WINDOW = timedelta(hours=48)


def _is_event_ride(r: Ride) -> bool:
    return bool((r.price_breakdown or {}).get("event"))


def _event_start_at(r: Ride) -> datetime | None:
    """The event's start time stamped in the ride breakdown (for the 48h deposit window)."""
    ev = (r.price_breakdown or {}).get("event") or {}
    raw = ev.get("starts_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _cancellation_fee_eligible(r: Ride) -> bool:
    """True when a cancellation fee is on the table: the ride is cancelled and
    the rider cancelled less than 24h before the scheduled pickup."""
    if r.status != RideStatus.CANCELLED or r.cancelled_at is None or r.scheduled_at is None:
        return False
    return (r.scheduled_at - r.cancelled_at) < _CANCELLATION_FEE_WINDOW


def _ride_out(r: Ride, *, unread_messages: int = 0) -> dict:
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
        "deposit_cents": r.deposit_cents,
        "balance_due_cents": r.balance_due_cents,
        "return_ride_id": r.return_ride_id,
        "is_return": r.is_return,
        "pax": r.pax,
        "vehicle": r.vehicle,
        "flight_number": r.flight_number,
        "lang": r.lang,
        "notes": r.notes,
        "ride_preferences": r.ride_preferences,
        "payment_method": (
            r.payment_method.value
            if isinstance(r.payment_method, PaymentMethod)
            else r.payment_method
        ),
        "paid": r.paid,
        "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        "tip": r.tip,
        "tip_method": (
            r.tip_method.value if isinstance(r.tip_method, PaymentMethod) else r.tip_method
        ),
        "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
        "cancellation_fee_eligible": _cancellation_fee_eligible(r),
        "google_event_id": r.google_event_id,
        "overdue": booking.is_overdue(r),
        "chat_open": booking.chat_window_open(r),
        "unread_messages": unread_messages,
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
        # Effective per-zone flat prices (global defaults overlaid with tenant overrides)
        # plus the static zone descriptors the dashboard renders its editor from.
        "zone_prices": {**zones.DEFAULT_ZONE_PRICES, **(rc.zone_prices or {})},
        "zones": zones.ZONE_DESCRIPTORS,
    }


# ─── Quote (gated by the registration wall) ──────────────────────────────────
@router.post("/quote")
async def post_quote(body: QuoteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Price a candidate trip without persisting. Backs the booking calculator.

    Registration wall: when REQUIRE_AUTH_TO_QUOTE is on (and auth is enforced), an
    anonymous visitor must sign in first — this binds every lead to their referring
    driver before they see a price. Open mode (AUTH_ENABLED=false) is unaffected."""
    payload = current_payload(request)
    settings = get_settings()
    if settings.REQUIRE_AUTH_TO_QUOTE and settings.AUTH_ENABLED and payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        if body.round_trip:
            return await booking.build_round_trip_quote(
                db,
                tenant_id=tenant_id,
                pickup=body.pickup,
                dropoff=body.dropoff,
                pax=body.pax,
                scheduled_at=body.scheduled_at,
                return_at=body.return_at,
                is_loyalty=body.is_loyalty,
                is_peak=body.is_peak,
            )
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
            discount_code=body.discount_code,
        )
    except DiscountError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e


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


# ─── Smart reservation (screenshots → fields) ──────────────────────────────────
@router.post("/rides/extract")
async def extract_reservation(
    files: list[UploadFile] = File(...),
    merge: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Read 1..N screenshots of a client's message and return a LIST of
    reservations to pre-fill the form. Staff only. Screenshots are grouped by
    client (different clients → separate reservations); pass merge=true to force a
    single merged reservation. Best-effort: a vision failure returns [] (the
    driver then types it). No ride is persisted here."""
    tenant_id = await resolve_tenant_id(db, payload)
    if not await subscriptions.tenant_has_entitlements(db, tenant_id=tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="subscription_required"
        )
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_files")
    if len(files) > settings.SMART_MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"too_many_images_max_{settings.SMART_MAX_IMAGES}",
        )
    images: list[tuple[str, bytes]] = []
    for f in files:
        media_type = (f.content_type or "").split(";")[0].strip().lower()
        if media_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_image_type"
            )
        raw = await f.read()
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_image")
        if len(raw) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="image_too_large"
            )
        images.append((media_type, raw))
    reservations = await smart.extract_reservation(images, merge=merge)
    return {
        "reservations": reservations,
        "simulated": not settings.smart_live,
        "count": len(reservations),
    }


# ─── Rides ────────────────────────────────────────────────────────────────────
@router.post("/rides", status_code=status.HTTP_201_CREATED)
async def create_ride(
    body: RideCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Create a ride. Passengers book for themselves (client_id pinned from the
    session); the ride starts QUOTED (a draft) and is only confirmed once the
    rider completes the payment step — paying online (POST /payments) or
    committing to pay-on-completion (POST /rides/{id}/confirm). This keeps
    unpaid drafts off the driver's calendar. Staff create manual rides QUOTED
    unless confirm=true."""
    # Server-side enforcement of the legal-agreement gate (defense in depth on top
    # of the frontend modal): no ride may be created until the user has signed.
    await legal_svc.ensure_signed(db, payload)
    tenant_id = await resolve_tenant_id(db, payload)
    is_passenger = payload.get("role") == auth.ROLE_PASSENGER
    client_id = payload.get("cid") if is_passenger else body.client_id
    ride_status = RideStatus.CONFIRMED if body.confirm else RideStatus.QUOTED
    # Event rides must be prepaid by card: never let confirm=true create a CONFIRMED,
    # unpaid (cash) event ride — force it back to QUOTED so it goes through the card flow.
    if body.confirm and await event_pricing.find_event_for_ride(
        db, pickup=body.pickup, dropoff=body.dropoff, when=body.scheduled_at
    ) is not None:
        ride_status = RideStatus.QUOTED
    if body.round_trip:
        try:
            outbound, _ret = await booking.create_round_trip(
                db,
                tenant_id=tenant_id,
                pickup=body.pickup,
                dropoff=body.dropoff,
                scheduled_at=body.scheduled_at,
                return_at=body.return_at,
                client_id=client_id,
                passenger_name=body.passenger_name,
                passenger_phone=body.passenger_phone,
                pax=body.pax,
                flight_number=body.flight_number,
                lang=body.lang,
                notes=body.notes,
                vehicle=body.vehicle,
                status=ride_status,
                ride_preferences=(
                    body.ride_preferences.model_dump() if body.ride_preferences else None
                ),
                terms_accepted=body.terms_accepted,
            )
        except booking.EventUnavailableError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="event_unavailable"
            ) from e
        return _ride_out(outbound)
    try:
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
            ride_preferences=body.ride_preferences.model_dump() if body.ride_preferences else None,
            discount_code=body.discount_code,
        )
    except DiscountError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.reason
        ) from e
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
    is_passenger = payload.get("role") == auth.ROLE_PASSENGER
    # Staff dashboard view lazily closes paid rides whose pickup time has passed.
    if not is_passenger and await booking.reconcile_overdue_paid(db, tenant_id=tenant_id):
        await db.commit()
    rides = await booking.list_rides(db, tenant_id=tenant_id, status=status_filter, limit=limit)
    if is_passenger:
        cid = payload.get("cid")
        rides = [r for r in rides if r.client_id == cid]
    names = await dashboard.client_names(
        db, tenant_id=tenant_id, ids=[r.client_id for r in rides]
    )
    # Assigned-driver contact (name/phone/vehicle/rating) so a rider can call or
    # text their driver from /trips. Only attached when a driver is assigned.
    drivers = await dashboard.assigned_drivers(
        db, ids=[(r.assigned_tenant_id or r.tenant_id) for r in rides]
    )
    reader_side = RideMessageSender.client if is_passenger else RideMessageSender.driver
    unread = await ride_messages_svc.unread_counts(
        db, ride_ids=[r.id for r in rides], reader_side=reader_side
    )
    out = []
    for r in rides:
        d = _ride_out(r, unread_messages=unread.get(r.id, 0))
        nm, ph = names.get(r.client_id, (None, None)) if r.client_id else (None, None)
        d["client_name"] = nm or r.passenger_name
        d["client_phone"] = ph or r.passenger_phone
        # Driver shown to the rider: the discount-handoff tenant if set, else the
        # ride's owning tenant (the driver who will service a normal booking).
        # Only surface a driver that has a phone — that's a configured driver and
        # the contact the rider can act on (call/text); contactless tenants stay
        # "driver pending".
        did = r.assigned_tenant_id or r.tenant_id
        if did and drivers.get(did) and drivers[did].get("phone"):
            d["assigned_driver"] = drivers[did]
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
    # Keep detail consistent with the list sweep: a paid past ride auto-closes.
    if booking.complete_if_overdue_paid(ride):
        await db.commit()
        await db.refresh(ride)
    reader_side = (
        RideMessageSender.client
        if payload.get("role") == auth.ROLE_PASSENGER
        else RideMessageSender.driver
    )
    unread = await ride_messages_svc.unread_counts(
        db, ride_ids=[ride.id], reader_side=reader_side
    )
    out = _ride_out(ride, unread_messages=unread.get(ride.id, 0))
    out.update(await dashboard.ride_detail_extra(db, tenant_id=tenant_id, ride=ride))
    did = ride.assigned_tenant_id or ride.tenant_id
    if did:
        drivers = await dashboard.assigned_drivers(db, ids=[did])
        if drivers.get(did) and drivers[did].get("phone"):
            out["assigned_driver"] = drivers[did]
    return out


@router.post("/rides/{ride_id}/confirm")
async def confirm_ride(
    ride_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Confirm a QUOTED ride the rider chose to pay on completion (cash / pay
    the driver at drop-off). No online charge: the ride moves to CONFIRMED, is
    left as CASH + unpaid, and is synced to the driver's calendar. Idempotent —
    re-confirming an already-active ride is a no-op. Passengers may only confirm
    their own ride."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if payload.get("role") == auth.ROLE_PASSENGER and ride.client_id != payload.get("cid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    # A round-trip return leg is only ever confirmed/paid through its outbound.
    if ride.is_return:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirm_via_outbound")
    # Event rides must be prepaid by card (no pay-later / cash) to secure the commitment.
    if _is_event_ride(ride):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="card_required_for_event"
        )
    if ride.status in (RideStatus.REQUESTED, RideStatus.QUOTED):
        ride.status = RideStatus.CONFIRMED
        # Pay-on-completion: keep the default CASH method; stays unpaid until the
        # driver collects at drop-off and marks it paid.
        ride.payment_method = PaymentMethod.CASH
        await db.commit()
        await db.refresh(ride)
        await booking.sync_ride_to_calendar(db, ride)
        await email.send_driver_new_ride(db, ride=ride)
        await notifications.emit(
            db,
            tenant_id=getattr(ride, "assigned_tenant_id", None) or ride.tenant_id,
            kind=NotificationKind.ride_new,
            data={
                "ride_id": ride.id,
                "pickup": ride.pickup_text,
                "dropoff": ride.dropoff_text,
                "client_name": (ride.passenger_name or "").strip() or None,
            },
        )
    return _ride_out(ride)


@router.patch("/rides/{ride_id}")
async def patch_ride(
    ride_id: int,
    body: RidePatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Driver updates a ride: status, payment method/paid flag, and/or the ride
    details themselves (pickup/dropoff/time/pax/flight/notes — a change of plans).
    Editing the route or schedule re-quotes the fare and moves the calendar event.
    Setting paid=true stamps paid_at; the driver can record cash/Venmo/Zelle."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")

    changes = body.model_dump(exclude_none=True)
    has_edits = any(k in changes for k in booking.EDITABLE_FIELDS)
    if has_edits:
        try:
            await booking.apply_ride_update(db, ride=ride, changes=changes, persist=False)
        except booking.RoundTripLockedError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    if body.status is not None:
        # Cancelled/no-show rides leave the calendar (the correct per-tenant one).
        if body.status in (RideStatus.CANCELLED, RideStatus.NO_SHOW) and ride.google_event_id:
            await booking.remove_ride_from_calendar(db, ride)
        ride.status = body.status
    if body.payment_method is not None:
        ride.payment_method = body.payment_method
    if body.paid is not None:
        ride.paid = body.paid
        if body.paid and ride.paid_at is None:
            ride.paid_at = datetime.now(UTC)
        if not body.paid:
            ride.paid_at = None
    # Tip: a positive amount is recorded; 0 clears it (and drops the method).
    if body.tip is not None:
        ride.tip = body.tip if body.tip > 0 else None
        if ride.tip is None:
            ride.tip_method = None
    if body.tip_method is not None and ride.tip:
        ride.tip_method = body.tip_method
    # A paid ride whose pickup time has passed auto-closes as completed (an
    # explicit cancel/no-show still wins — those are never "overdue").
    booking.complete_if_overdue_paid(ride)
    await db.commit()
    await db.refresh(ride)
    # Re-sync the (possibly moved) calendar event after an edit to an active ride.
    if has_edits and ride.scheduled_at and ride.status not in booking._INACTIVE:
        await booking.sync_ride_to_calendar(db, ride)
        await db.refresh(ride)
    return _ride_out(ride)


@router.delete("/rides/{ride_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ride(
    ride_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Permanently delete a ride. Only cancelled/no-show rides can be removed —
    active or completed rides are part of the record and must be cancelled first.
    Tenant-scoped: a ride from another tenant returns 404, not 403."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if ride.status not in (RideStatus.CANCELLED, RideStatus.NO_SHOW):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="ride_not_deletable"
        )
    await booking.delete_ride(db, ride=ride)
    return None


@router.post("/rides/{ride_id}/preview-update")
async def preview_ride_update(
    ride_id: int,
    body: RideEdit,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Dry-run a change of plans: re-quote the proposed trip and report scheduling
    conflicts WITHOUT persisting. Backs the diff + conflict warning shown before
    the driver applies the change."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")

    ch = body.model_dump(exclude_none=True)
    cur_stops = [s["text"] for s in ride.stops] if ride.stops else None
    m_pickup = ch.get("pickup", ride.pickup_text)
    m_dropoff = ch.get("dropoff", ride.dropoff_text)
    m_stops = ch.get("stops", cur_stops)
    m_pax = ch.get("pax", ride.pax)
    m_sched = ch.get("scheduled_at", ride.scheduled_at)

    distance, duration, fare = ride.distance_miles, ride.duration_minutes, ride.fare_total
    if any(k in ch for k in ("pickup", "dropoff", "stops", "pax", "scheduled_at")):
        bd = await booking.build_quote(
            db, tenant_id=tenant_id, pickup=m_pickup, dropoff=m_dropoff,
            stops=m_stops, pax=m_pax, scheduled_at=m_sched,
        )
        distance, duration = bd["distance_miles"], bd["duration_minutes"]
        fare = bd["total"]
    if "fare_override" in ch:
        fare = ch["fare_override"]

    conflicts = []
    if m_sched is not None:
        conflicts = await booking.find_conflicts(
            db, tenant_id=tenant_id, scheduled_at=m_sched,
            duration_minutes=duration, exclude_ride_id=ride.id,
        )
    return {
        "current": {
            "pickup": ride.pickup_text, "dropoff": ride.dropoff_text,
            "scheduled_at": ride.scheduled_at.isoformat() if ride.scheduled_at else None,
            "pax": ride.pax, "flight_number": ride.flight_number,
            "fare_total": ride.fare_total, "distance_miles": ride.distance_miles,
            "duration_minutes": ride.duration_minutes,
        },
        "proposed": {
            "pickup": m_pickup, "dropoff": m_dropoff,
            "scheduled_at": m_sched.isoformat() if m_sched else None,
            "pax": m_pax, "flight_number": ch.get("flight_number", ride.flight_number),
            "notes": ch.get("notes", ride.notes), "lang": ch.get("lang", ride.lang),
            "fare_total": fare, "distance_miles": distance, "duration_minutes": duration,
        },
        "conflicts": conflicts,
    }


class RefundDecisionBody(BaseModel):
    # 0 = full refund; 20/30 = cancellation fee the driver keeps (rest refunded).
    fee_pct: int = Field(..., description="0, 20, or 30")

    @field_validator("fee_pct")
    @classmethod
    def _valid_pct(cls, v: int) -> int:
        if v not in (0, 20, 30):
            raise ValueError("fee_pct must be 0, 20, or 30")
        return v


@router.post("/rides/{ride_id}/cancel")
async def cancel_ride(
    ride_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Cancel a ride. Accessible to the rider (own ride) and to staff.

    Riders may cancel before the driver is en route. Refund handling:
    - >=24h before pickup (or no scheduled time): the rider is refunded in full
      automatically (the hold is voided or the charge refunded).
    - <24h before pickup: a cancellation fee may apply, so the payment is left
      pending the driver's refund decision (POST /rides/{id}/refund-decision).
    Cash / pay-on-completion rides simply cancel (nothing to refund)."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if payload.get("role") == auth.ROLE_PASSENGER and ride.client_id != payload.get("cid"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if ride.status == RideStatus.CANCELLED:
        return _ride_out(ride)  # idempotent
    if ride.status not in _CANCELLABLE_BY_RIDER:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_cancellable")

    now = datetime.now(UTC)
    ride.status = RideStatus.CANCELLED
    ride.cancelled_at = now
    if ride.google_event_id:
        await booking.remove_ride_from_calendar(db, ride)
    # Round trip: cancelling the outbound cancels the linked return leg too (the single
    # payment refund below already covers both legs' fares).
    if ride.return_ride_id:
        ret = await db.get(Ride, ride.return_ride_id)
        if ret is not None and ret.status != RideStatus.CANCELLED:
            ret.status = RideStatus.CANCELLED
            ret.cancelled_at = now
            if ret.google_event_id:
                await booking.remove_ride_from_calendar(db, ret)
    is_event = _is_event_ride(ride)
    is_deposit = ride.deposit_cents is not None
    refund_pending = False
    if is_deposit:
        # Event deposit reservation: fully refundable up to 48h before the event; inside 48h the
        # deposit is non-refundable (fee_pct=100 -> keep it). Keyed to the event start time.
        ev_start = _event_start_at(ride) or ride.scheduled_at
        non_refundable = ev_start is not None and (ev_start - now) < _DEPOSIT_REFUND_WINDOW
        await payments.settle_cancellation(
            db, tenant_id=tenant_id, ride=ride, fee_pct=100 if non_refundable else 0
        )
    else:
        window = _EVENT_CANCELLATION_FEE_WINDOW if is_event else _CANCELLATION_FEE_WINDOW
        fee_eligible = ride.scheduled_at is not None and (ride.scheduled_at - now) < window
        if not fee_eligible:
            # Outside the fee window -> make the rider whole right away.
            await payments.settle_cancellation(db, tenant_id=tenant_id, ride=ride, fee_pct=0)
        elif is_event:
            # Events have a fixed policy: within 72h -> automatic 50% refund (no driver choice).
            await payments.settle_cancellation(
                db, tenant_id=tenant_id, ride=ride, fee_pct=_EVENT_CANCELLATION_FEE_PCT
            )
        else:
            pay = await payments.active_payment_for_ride(
                db, tenant_id=ride.tenant_id, ride_id=ride.id
            )
            refund_pending = pay is not None
    await db.commit()
    await db.refresh(ride)
    await email.send_driver_ride_cancelled(db, ride=ride, refund_pending=refund_pending)
    await notifications.emit(
        db,
        tenant_id=getattr(ride, "assigned_tenant_id", None) or ride.tenant_id,
        kind=NotificationKind.ride_cancelled,
        data={
            "ride_id": ride.id,
            "pickup": ride.pickup_text,
            "dropoff": ride.dropoff_text,
            "client_name": (ride.passenger_name or "").strip() or None,
        },
    )
    # Passenger push: only when STAFF cancelled — if the rider cancelled their own
    # ride they already know. Best-effort, never raises.
    if payload.get("role") in auth.STAFF_ROLES and ride.client_id:
        push.notify_client(
            ride.tenant_id,
            ride.client_id,
            event="ride_cancelled",
            lang=ride.lang,
            place=ride.dropoff_text,
        )
    return _ride_out(ride)


@router.post("/rides/{ride_id}/refund-decision")
async def refund_decision(
    ride_id: int,
    body: RefundDecisionBody,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """Driver/staff decision on a cancelled ride's refund: full refund
    (fee_pct=0) or keep a 20%/30% cancellation fee. A fee is allowed only when
    the ride was cancelled <24h before pickup."""
    tenant_id = await resolve_tenant_id(db, payload)
    ride = await booking.get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ride_not_found")
    if ride.status != RideStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ride_not_cancelled")
    if body.fee_pct > 0 and not _cancellation_fee_eligible(ride):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="fee_not_eligible")
    try:
        await payments.settle_cancellation(db, tenant_id=tenant_id, ride=ride, fee_pct=body.fee_pct)
    except payments_square.PaymentError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await db.commit()
    await db.refresh(ride)
    # Passenger push about the refund outcome. Best-effort, never raises.
    if ride.client_id:
        full = body.fee_pct <= 0
        push.notify_client(
            ride.tenant_id,
            ride.client_id,
            event="refund_full" if full else "refund_partial",
            lang=ride.lang,
        )
        refund_kind = (
            ClientNotificationKind.refund_full if full else ClientNotificationKind.refund_partial
        )
        await notifications.emit_client(
            db,
            client_id=ride.client_id,
            tenant_id=ride.tenant_id,
            kind=refund_kind,
            data={"ride_id": ride.id},
        )
    out = _ride_out(ride)
    out.update(await dashboard.ride_detail_extra(db, tenant_id=tenant_id, ride=ride))
    return out
