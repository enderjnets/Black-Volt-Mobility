"""Booking service: rate-config access, quoting (maps + pricing), and ride
persistence. All queries are tenant-scoped."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, RateConfig, Ride, RideStatus
from app.models.rate_config import DEFAULT_RATES
from app.services import discounts, maps, pricing
from app.services import profile as profile_svc

logger = logging.getLogger("blackvolt.booking")

# Cancelled/no-show rides never count toward money or activity.
CANCELLED_STATUSES = (RideStatus.CANCELLED, RideStatus.NO_SHOW)


def earned_ride_filter():
    """SQL predicate for a ride that actually earned money: it's completed OR
    settled, and never cancelled/no-show. Shared by the dashboard KPIs and the
    My Stats funnel so "revenue" means the same thing everywhere — a completed
    cash ride counts even if the paid flag was never toggled, and a cancelled
    ride never inflates the numbers."""
    return and_(
        Ride.status.not_in(CANCELLED_STATUSES),
        or_(Ride.paid.is_(True), Ride.status == RideStatus.COMPLETED),
    )


async def get_or_create_rate_config(db: AsyncSession, *, tenant_id: int) -> RateConfig:
    rc = (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if rc is None:
        rc = RateConfig(tenant_id=tenant_id, **DEFAULT_RATES)
        db.add(rc)
        await db.commit()
        await db.refresh(rc)
    return rc


# Fields a client/dashboard may edit on the rate engine.
RATE_FIELDS = (
    "currency",
    "minimum",
    "base",
    "per_mile",
    "per_minute",
    "airport_flat",
    "extra_stop_fee",
    "group_surcharge",
    "group_threshold",
    "peak_enabled",
    "peak_multiplier",
    "loyalty_discount_pct",
)


async def update_rate_config(db: AsyncSession, *, tenant_id: int, changes: dict) -> RateConfig:
    rc = await get_or_create_rate_config(db, tenant_id=tenant_id)
    for k, v in changes.items():
        if k in RATE_FIELDS and v is not None:
            setattr(rc, k, v)
    await db.commit()
    await db.refresh(rc)
    return rc


async def build_quote(
    db: AsyncSession,
    *,
    tenant_id: int,
    pickup: str,
    dropoff: str,
    stops: list[str] | None = None,
    pax: int | None = None,
    scheduled_at: datetime | None = None,
    is_loyalty: bool = False,
    is_peak: bool | None = None,
    discount_code: str | None = None,
) -> dict:
    """Compute a fare for a candidate trip without persisting it. Returns the
    route facts + the pricing breakdown."""
    rc = await get_or_create_rate_config(db, tenant_id=tenant_id)
    rr = await maps.route(pickup, dropoff, stops)
    is_airport = pricing.looks_like_airport(pickup, dropoff)
    facts = pricing.RouteFacts(
        distance_miles=rr.distance_miles,
        duration_minutes=rr.duration_minutes,
        is_airport=is_airport,
        pax=pax,
        extra_stops=len(stops) if stops else 0,
        scheduled_at=scheduled_at,
        is_peak=is_peak,
        is_loyalty=is_loyalty,
    )
    if discount_code:
        code_row = await discounts.validate_code(db, discount_code)
        facts.discount_pct = code_row.discount_pct
        # Re-resolve RateConfig using the code owner's tenant for correct base rates.
        rc = await get_or_create_rate_config(db, tenant_id=code_row.tenant_id)
    breakdown = pricing.quote(rc, facts)
    breakdown["route_simulated"] = rr.simulated
    return breakdown


async def create_ride(
    db: AsyncSession,
    *,
    tenant_id: int,
    pickup: str,
    dropoff: str,
    stops: list[str] | None = None,
    client_id: int | None = None,
    passenger_name: str | None = None,
    passenger_phone: str | None = None,
    pax: int | None = None,
    scheduled_at: datetime | None = None,
    flight_number: str | None = None,
    lang: str | None = None,
    notes: str | None = None,
    vehicle: str | None = None,
    is_loyalty: bool = False,
    is_peak: bool | None = None,
    status: RideStatus = RideStatus.QUOTED,
    fare_override: float | None = None,
    ride_preferences: dict | None = None,
    discount_code: str | None = None,
) -> Ride:
    """Quote (maps + pricing) then persist the ride. `fare_override` lets the
    driver pin a negotiated fare while still snapshotting the computed route.

    When `discount_code` is given the ride stays in the booker's tenant
    (`tenant_id`), `assigned_tenant_id` is set to the code-owning tenant so
    that driver can see and service it, `client_id` is preserved as-is
    (passenger contact is snapshotted on the ride). The fare is computed using
    the code owner's RateConfig (not the booker's), and `used_count` is
    incremented only when payment succeeds — not at ride creation."""
    # Validate the discount code first so we have the owning-tenant info and
    # the discount_pct before the quote is computed.
    code_row = None
    if discount_code:
        code_row = await discounts.validate_code(db, discount_code)

    breakdown = await build_quote(
        db,
        tenant_id=tenant_id,
        pickup=pickup,
        dropoff=dropoff,
        stops=stops,
        pax=pax,
        scheduled_at=scheduled_at,
        is_loyalty=is_loyalty,
        is_peak=is_peak,
        discount_code=discount_code,
    )

    # Persist a driver-entered passenger as a real Client (CRM + autocomplete);
    # the ad-hoc name/phone stay on the ride as a snapshot for history.
    # When a discount code hands the ride to a different tenant, skip client
    # creation — the client belongs to the originating tenant, not the driver.
    if code_row is None and client_id is None and (passenger_name or passenger_phone):
        from app.services.tenancy import find_or_create_client_by_contact

        c = await find_or_create_client_by_contact(
            db, tenant_id=tenant_id, name=passenger_name, phone=passenger_phone, lang=lang
        )
        if c is not None:
            client_id = c.id

    # Per-ride preference snapshot: explicit overrides win; otherwise inherit the
    # client's standing preferences so the driver sees them for this ride.
    prefs_snapshot: dict | None = None
    if ride_preferences is not None:
        prefs_snapshot = profile_svc.normalize_ride_preferences(None, ride_preferences)
    elif client_id is not None:
        # Tenant-scoped lookup: never snapshot another tenant's client preferences.
        existing = (
            await db.execute(
                select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if existing is not None and existing.ride_preferences:
            prefs_snapshot = profile_svc.normalize_ride_preferences(existing.ride_preferences)

    # Discount amount is the absolute value of the "discount_code" line in the
    # breakdown (0.0 when no code was applied).
    discount_amount = 0.0
    if code_row is not None:
        for line in breakdown.get("lines", []):
            if line.get("label") == "discount_code":
                discount_amount = abs(line["amount"])
                break

    # When a discount code is present: ride stays in the booker's tenant and
    # retains the original client_id so payment and history continue to work.
    # assigned_tenant_id marks the code-owning driver who will service the ride.
    assigned_tenant_id = code_row.tenant_id if code_row is not None else None

    # Passenger contact snapshot: if the ride is handed off and no explicit
    # passenger_name was supplied but a client_id is available, copy the client's
    # contact info so the receiving driver can reach the passenger.
    if assigned_tenant_id is not None and client_id is not None:
        snap = (
            await db.execute(
                select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if snap is not None:
            if not passenger_name:
                passenger_name = snap.name
            if not passenger_phone:
                passenger_phone = snap.phone

    ride = Ride(
        tenant_id=tenant_id,
        client_id=client_id,
        status=status,
        ride_preferences=prefs_snapshot,
        pickup_text=pickup,
        dropoff_text=dropoff,
        stops=[{"text": s} for s in stops] if stops else None,
        scheduled_at=scheduled_at,
        distance_miles=breakdown["distance_miles"],
        duration_minutes=breakdown["duration_minutes"],
        fare_total=fare_override if fare_override is not None else breakdown["total"],
        currency=breakdown["currency"],
        price_breakdown=breakdown,
        pax=pax,
        vehicle=vehicle,
        flight_number=flight_number,
        lang=lang,
        notes=notes,
        passenger_name=passenger_name,
        passenger_phone=passenger_phone,
        assigned_tenant_id=assigned_tenant_id,
        discount_code_id=code_row.id if code_row is not None else None,
        discount_amount=discount_amount,
    )
    db.add(ride)
    await db.commit()
    await db.refresh(ride)
    await sync_ride_to_calendar(db, ride)
    return ride


# Terminal/inactive statuses: no overdue, excluded from active-ride queries.
_INACTIVE = (RideStatus.CANCELLED, RideStatus.NO_SHOW, RideStatus.COMPLETED)

# Statuses a ride must hold to appear on a driver's calendar. A QUOTED/REQUESTED
# ride is only a draft awaiting the rider's payment decision — it must NOT be
# pushed to the calendar until it is actually confirmed (paid online or
# committed to pay-on-completion). This is the guard that keeps unpaid drafts
# off the driver's schedule.
_CALENDAR_VISIBLE = (RideStatus.CONFIRMED, RideStatus.ASSIGNED, RideStatus.EN_ROUTE)


def is_overdue(ride: Ride, now: datetime | None = None) -> bool:
    """A scheduled, still-active ride whose pickup time has already passed —
    it needs the driver to confirm the pickup happened (or auto-closes if paid)."""
    if ride.scheduled_at is None or ride.status in _INACTIVE:
        return False
    sched = ride.scheduled_at
    if sched.tzinfo is None:  # a naive client value (PATCH without offset) is UTC
        sched = sched.replace(tzinfo=UTC)
    return sched < (now or datetime.now(UTC))


def complete_if_overdue_paid(ride: Ride, now: datetime | None = None) -> bool:
    """Auto-close a ride once it is both paid and past its pickup time (e.g. a
    Square capture or a recorded cash payment on a ride whose time has passed).
    Returns True if it transitioned the ride to COMPLETED."""
    if ride.paid and is_overdue(ride, now):
        ride.status = RideStatus.COMPLETED
        return True
    return False


async def reconcile_overdue_paid(
    db: AsyncSession, *, tenant_id: int, now: datetime | None = None
) -> int:
    """Bulk-complete every paid, still-active ride whose pickup time has passed
    (settled in advance or by Square) — a lazy, idempotent sweep run when the
    dashboard lists rides, so paid past rides don't linger as 'upcoming'. Does
    not commit; the caller decides. Returns the number of rides closed."""
    cutoff = now or datetime.now(UTC)
    result = await db.execute(
        update(Ride)
        .where(
            Ride.tenant_id == tenant_id,
            Ride.paid.is_(True),
            Ride.scheduled_at.is_not(None),
            Ride.scheduled_at < cutoff,
            Ride.status.not_in(_INACTIVE),
        )
        .values(status=RideStatus.COMPLETED)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def house_to_house_window(
    scheduled_at: datetime, *, lead_min: float, trip_min: float, trail_min: float
) -> tuple[datetime, datetime]:
    """Calendar block for a pickup (pickup-protocol house→house rule): leave the
    dispatch base `lead_min` (deadhead) before the pickup and return home
    `trip_min + trail_min` after it (passenger trip + return drive + turnaround
    buffer). The real pickup time stays in the event title/description."""
    start = scheduled_at - timedelta(minutes=lead_min)
    end = scheduled_at + timedelta(minutes=trip_min + trail_min)
    return start, end


async def _deadhead_window(ride: Ride) -> tuple[float, float]:
    """Deadhead (base→pickup) and trail (dropoff→base + buffer) minutes for the
    house→house block. Returns (0, 0) when no dispatch base is configured, so the
    event falls back to the passenger trip only. Best-effort: a maps failure
    fails soft to a simulated route inside maps.route."""
    settings = get_settings()
    home = settings.DISPATCH_ADDRESS.strip()
    if not home:
        return 0.0, 0.0
    lead = (await maps.route(home, ride.pickup_text)).duration_minutes
    ret = (await maps.route(ride.dropoff_text, home)).duration_minutes
    return lead, ret + settings.CALENDAR_BLOCK_BUFFER_MIN


async def _tenant_is_admin(db: AsyncSession, tenant_id: int) -> bool:
    """True when a tenant's rides belong on the shared Black Volt calendar: the
    default tenant, or a tenant owned by an active admin.

    Deterministic by design — this decides which calendar a ride routes to, so it
    must NOT depend on row ordering. A tenant is "admin/shared" iff ANY active
    admin AllowedUser owns it; otherwise it routes to the member's own calendar."""
    from app.models import AllowedUser
    from app.models.allowed_user import ROLE_ADMIN
    from app.services.tenancy import get_default_tenant

    default = await get_default_tenant(db)
    if tenant_id == default.id:
        return True
    admin_owner = (
        await db.execute(
            select(AllowedUser.id).where(
                AllowedUser.tenant_id == tenant_id,
                AllowedUser.role == ROLE_ADMIN,
                AllowedUser.active.is_(True),
            )
        )
    ).first()
    return admin_owner is not None


async def _calendar_route(db: AsyncSession, ride: Ride):
    """Resolve which Google Calendar a ride's event belongs to, keyed by tenant.

    Returns ``(service, calendar_id, attendees)`` or ``None`` to skip sync:
      • Admin / default tenant → the shared Black Volt calendar (unchanged):
        ``service=None`` (upsert uses the global service) + GOOGLE_CALENDAR_ID +
        the configured invitees (only when OAuth can actually invite).
      • A member who has connected their own calendar → their own service +
        calendar id, no global invitees (the event lives on their calendar).
      • A non-admin member who has NOT connected → ``None`` (do not sync; never
        pollute the admin calendar).
    """
    settings = get_settings()

    if await _tenant_is_admin(db, ride.tenant_id):
        attendees = settings.calendar_invitees if settings.calendar_can_invite else None
        return (None, settings.GOOGLE_CALENDAR_ID, attendees)

    from app.models import CalendarCredential
    from app.services import calendar, crypto

    cred = (
        await db.execute(
            select(CalendarCredential).where(CalendarCredential.tenant_id == ride.tenant_id)
        )
    ).scalar_one_or_none()
    if cred is None:
        return None  # member hasn't connected their calendar → skip
    if settings.CALENDAR_SIMULATED:
        # Dev/tests: never call Google; let upsert simulate (service=None).
        return (None, cred.calendar_id, None)
    try:
        token = crypto.decrypt(cred.refresh_token_enc)
        svc = calendar.service_from_refresh_token(token)
    except Exception as e:  # noqa: BLE001 — bad/rotated token → skip, don't crash
        logger.warning("calendar creds unusable for tenant %s: %s", ride.tenant_id, e)
        return None
    return (svc, cred.calendar_id, None)


async def remove_ride_from_calendar(db: AsyncSession, ride: Ride) -> None:
    """Delete a ride's event from its correct (per-tenant) calendar and clear the
    stored id. Best-effort — never raises. The caller commits."""
    if not ride.google_event_id:
        return
    try:
        from app.services import calendar

        route = await _calendar_route(db, ride)
        if route is not None:
            svc, cal, _ = route
            calendar.delete_event(ride.google_event_id, service=svc, calendar_id=cal)
    except Exception as e:  # noqa: BLE001 — calendar must not block ride deletion
        logger.warning("calendar delete failed for ride %s: %s", ride.id, e)
    finally:
        ride.google_event_id = None


async def sync_ride_to_calendar(db: AsyncSession, ride: Ride) -> None:
    """Push a scheduled, active ride to the correct Google Calendar (create or
    update) and store the event id. The target calendar is resolved per tenant
    (admin → shared Black Volt calendar; a member → their own connected calendar;
    an unconnected member → skipped). The event spans the house→house block per
    the pickup protocol and reminds 30/60 min before. Best-effort — never raises
    (calendar must not block bookings)."""
    if ride.scheduled_at is None or ride.status not in _CALENDAR_VISIBLE:
        return
    try:
        from app.models import Client
        from app.services import calendar

        route = await _calendar_route(db, ride)
        if route is None:
            return  # unconnected member — do not sync
        svc, cal, attendees = route

        settings = get_settings()
        name = ride.passenger_name
        if ride.client_id:
            c = (
                await db.execute(select(Client).where(Client.id == ride.client_id))
            ).scalar_one_or_none()
            if c and c.name:
                name = c.name

        lead, trail = await _deadhead_window(ride)
        start, end = house_to_house_window(
            ride.scheduled_at,
            lead_min=lead,
            trip_min=ride.duration_minutes or 60,
            trail_min=trail,
        )
        ev = calendar.build_ride_event(
            client_name=name,
            pickup=ride.pickup_text,
            dropoff=ride.dropoff_text,
            fare=ride.fare_total,
            flight=ride.flight_number,
            phone=ride.passenger_phone,
            notes=ride.notes,
            pickup_time=ride.scheduled_at,
            tz=settings.CALENDAR_TIMEZONE,
        )
        event_id = calendar.upsert_event(
            summary=ev["summary"],
            description=ev["description"],
            location=ev["location"],
            start=start,
            end=end,
            tz=settings.CALENDAR_TIMEZONE,
            # Attendees only on the shared calendar (and only when OAuth can
            # invite — a service account 403s on attendees). A member's own
            # calendar carries no global invitees.
            attendees=attendees,
            event_id=ride.google_event_id,
            service=svc,
            calendar_id=cal,
        )
        if event_id and event_id != ride.google_event_id:
            ride.google_event_id = event_id
            await db.commit()
    except Exception as e:  # noqa: BLE001 — best-effort, never block the booking
        # Surface the failure (bad invitee, invalid timezone, maps/creds error)
        # so a systematically-broken calendar is detectable, then roll back.
        logger.warning("calendar sync failed for ride %s: %s", ride.id, e)
        await db.rollback()


# Fields a driver may edit on an existing ride (Smart update / change of plans).
# Route-affecting fields trigger a re-quote; `stops` is passed as list[str].
EDITABLE_FIELDS = (
    "pickup",
    "dropoff",
    "stops",
    "scheduled_at",
    "pax",
    "flight_number",
    "notes",
    "lang",
    "fare_override",
)
_ROUTE_FIELDS = ("pickup", "dropoff", "stops", "pax", "scheduled_at")


async def find_conflicts(
    db: AsyncSession,
    *,
    tenant_id: int,
    scheduled_at: datetime,
    duration_minutes: float | None,
    exclude_ride_id: int | None = None,
    buffer_min: int | None = None,
) -> list[dict]:
    """Active, scheduled rides whose time window (± a travel/turnaround buffer)
    overlaps the proposed [scheduled_at, +duration]. Used to warn before applying
    a change of plans. Excludes the ride being edited and inactive rides."""
    from datetime import timedelta

    from app.config import get_settings
    from app.models import Client

    mins = buffer_min if buffer_min is not None else get_settings().RIDE_BUFFER_MIN
    buf = timedelta(minutes=mins)
    p_start = scheduled_at
    p_end = scheduled_at + timedelta(minutes=duration_minutes or 60)

    q = select(Ride).where(
        Ride.tenant_id == tenant_id,
        Ride.scheduled_at.is_not(None),
        Ride.status.not_in(_INACTIVE),
    )
    if exclude_ride_id is not None:
        q = q.where(Ride.id != exclude_ride_id)
    rides = list((await db.execute(q)).scalars().all())

    hits = []
    for r in rides:
        e_start = r.scheduled_at
        e_end = e_start + timedelta(minutes=r.duration_minutes or 60)
        # Conflict unless one ride fully ends (+buffer) before the other starts.
        if p_end + buf <= e_start or e_end + buf <= p_start:
            continue
        hits.append(r)

    names: dict[int, str] = {}
    cids = [r.client_id for r in hits if r.client_id]
    if cids:
        rows = (await db.execute(select(Client).where(Client.id.in_(cids)))).scalars().all()
        names = {c.id: c.name for c in rows if c.name}
    return [
        {
            "id": r.id,
            "name": names.get(r.client_id) or r.passenger_name or "Guest",
            "scheduled_at": r.scheduled_at.isoformat(),
            "pickup": r.pickup_text,
            "dropoff": r.dropoff_text,
        }
        for r in hits
    ]


async def apply_ride_update(
    db: AsyncSession, *, ride: Ride, changes: dict, persist: bool = True
) -> Ride:
    """Apply editable changes to a ride. Route-affecting edits re-quote (maps +
    pricing) and refresh distance/duration/fare/breakdown unless a fare_override
    is given. With persist=True the change is committed and the calendar event is
    re-synced (moved); with persist=False the ride is mutated in-memory only (for
    a dry-run preview)."""
    clean = {k: v for k, v in changes.items() if k in EDITABLE_FIELDS and v is not None}
    fare_override = clean.pop("fare_override", None)

    if "pickup" in clean:
        ride.pickup_text = clean["pickup"]
    if "dropoff" in clean:
        ride.dropoff_text = clean["dropoff"]
    if "stops" in clean:
        ride.stops = [{"text": s} for s in clean["stops"]] if clean["stops"] else None
    if "scheduled_at" in clean:
        ride.scheduled_at = clean["scheduled_at"]
    if "pax" in clean:
        ride.pax = clean["pax"]
    if "flight_number" in clean:
        ride.flight_number = clean["flight_number"]
    if "notes" in clean:
        ride.notes = clean["notes"]
    if "lang" in clean:
        ride.lang = clean["lang"]

    if any(f in clean for f in _ROUTE_FIELDS):
        stops = [s["text"] for s in ride.stops] if ride.stops else None
        breakdown = await build_quote(
            db,
            tenant_id=ride.tenant_id,
            pickup=ride.pickup_text,
            dropoff=ride.dropoff_text,
            stops=stops,
            pax=ride.pax,
            scheduled_at=ride.scheduled_at,
        )
        ride.distance_miles = breakdown["distance_miles"]
        ride.duration_minutes = breakdown["duration_minutes"]
        ride.currency = breakdown["currency"]
        ride.price_breakdown = breakdown
        if fare_override is None:
            ride.fare_total = breakdown["total"]
    if fare_override is not None:
        ride.fare_total = fare_override

    if persist:
        await db.commit()
        await db.refresh(ride)
        await sync_ride_to_calendar(db, ride)
    return ride


async def list_rides(
    db: AsyncSession, *, tenant_id: int, status: RideStatus | None = None, limit: int = 100
) -> list[Ride]:
    q = select(Ride).where(or_(Ride.tenant_id == tenant_id, Ride.assigned_tenant_id == tenant_id))
    if status is not None:
        q = q.where(Ride.status == status)
    q = q.order_by(
        Ride.scheduled_at.is_(None), Ride.scheduled_at.asc(), Ride.id.desc()
    ).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_ride(db: AsyncSession, *, tenant_id: int, ride_id: int) -> Ride | None:
    return (
        await db.execute(
            select(Ride).where(
                or_(Ride.tenant_id == tenant_id, Ride.assigned_tenant_id == tenant_id),
                Ride.id == ride_id,
            )
        )
    ).scalar_one_or_none()


async def set_ride_status(
    db: AsyncSession, *, tenant_id: int, ride_id: int, status: RideStatus
) -> Ride | None:
    ride = await get_ride(db, tenant_id=tenant_id, ride_id=ride_id)
    if ride is None:
        return None
    ride.status = status
    await db.commit()
    await db.refresh(ride)
    return ride


async def delete_ride(db: AsyncSession, *, ride: Ride) -> None:
    """Permanently remove a ride. The caller must enforce that it's in a deletable
    (cancelled/no-show) state. Any calendar event is removed, and payment rows are
    detached (ride_id → NULL) rather than deleted, preserving the financial audit
    trail even though the ride record goes away."""
    await remove_ride_from_calendar(db, ride)
    from app.models import Payment

    await db.execute(
        update(Payment).where(Payment.ride_id == ride.id).values(ride_id=None)
    )
    await db.delete(ride)
    await db.commit()
