"""Booking payment-gating + pay-on-completion + assigned-driver contact.

Covers the fix where a web booking used to be CONFIRMED and pushed to the
driver's calendar *before* payment, plus the new "pay the driver at drop-off"
path and the assigned-driver contact exposed on /trips. Auth env mirrors the
other API tests; payments + maps run simulated (no external calls)."""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client, Ride  # noqa: E402
from app.models.ride import RideStatus  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import booking  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


# --- seed helpers -----------------------------------------------------------
def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_passenger(phone: str = "+13035550100") -> tuple[int, int]:
    """Create a tenant + client; return (client_id, tenant_id)."""

    async def go() -> tuple[int, int]:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"paxt-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Test Rider",
                    phone=phone,
                    email=f"pax-{os.urandom(4).hex()}@pgtest.local",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                )
                db.add(client)
                await db.commit()
                await db.refresh(client)
                return client.id, tenant.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_client_in_tenant(tenant_id: int) -> int:
    """A second client inside an existing tenant (for same-tenant ownership)."""

    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                client = Client(
                    tenant_id=tenant_id,
                    name="Other Rider",
                    email=f"pax-{os.urandom(4).hex()}@pgtest.local",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                )
                db.add(client)
                await db.commit()
                await db.refresh(client)
                return client.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_driver_tenant(phone: str, vehicle: str, rating: float) -> int:
    """A driver is a top-level tenant carrying contact fields."""

    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                t = await create_tenant_for(db, name=f"drv-{os.urandom(4).hex()}")
                t.phone = phone
                t.vehicle = vehicle
                t.rating = rating
                await db.commit()
                return t.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_ride(
    *,
    tenant_id: int,
    client_id: int,
    status: RideStatus = RideStatus.QUOTED,
    scheduled_at=None,
    assigned_tenant_id: int | None = None,
    fare_total: float = 74.0,
) -> int:
    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = Ride(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    status=status,
                    pickup_text="Downtown Denver",
                    dropoff_text="Denver Intl (DEN)",
                    fare_total=fare_total,
                    duration_minutes=22.0,
                    scheduled_at=scheduled_at,
                    assigned_tenant_id=assigned_tenant_id,
                    passenger_name="Test Rider",
                    passenger_phone="+13035550100",
                )
                db.add(ride)
                await db.commit()
                await db.refresh(ride)
                return ride.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _ride_row(db_session_status: RideStatus) -> Ride:
    """Build a transient (un-persisted) Ride for direct unit tests."""
    return Ride(
        tenant_id=1,
        status=db_session_status,
        pickup_text="A",
        dropoff_text="B",
        scheduled_at=_future(),
        duration_minutes=20.0,
        fare_total=50.0,
    )


def _future():
    # A fixed future instant (no Date.now() needed): 2030-01-01 15:00 UTC.
    from datetime import UTC, datetime

    return datetime(2030, 1, 1, 15, 0, tzinfo=UTC)


def _passenger_client(client_id: int, tenant_id: int) -> TestClient:
    token = authsvc.make_token(
        role=authsvc.ROLE_PASSENGER,
        tenant_id=tenant_id,
        email="pax@example.com",
        client_id=client_id,
    )
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    for _p in c.get("/api/v1/agreements/pending").json().get("pending", []):
        c.post(
            f"/api/v1/agreements/{_p['doc_type']}/accept",
            json={"version": _p["version"], "lang": "en", "signed_name": "Test Signer"},
        )
    return c


# --- calendar guard (the core bug) ------------------------------------------
def test_sync_skips_quoted_ride(monkeypatch):
    """A QUOTED draft must never reach calendar routing — the status guard
    returns before _calendar_route is consulted."""
    calls = []

    async def _recorder(db, ride):
        calls.append(ride.status)
        return None  # unconnected — would skip anyway

    monkeypatch.setattr(booking, "_calendar_route", _recorder)

    asyncio.run(booking.sync_ride_to_calendar(None, _ride_row(RideStatus.QUOTED)))
    assert calls == []  # guard short-circuited; routing never attempted

    asyncio.run(booking.sync_ride_to_calendar(None, _ride_row(RideStatus.CONFIRMED)))
    assert calls == [RideStatus.CONFIRMED]  # confirmed rides do route


# --- create starts QUOTED (no premature calendar) ---------------------------
def test_passenger_create_ride_is_quoted():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Downtown Denver",
            "dropoff": "Denver Intl (DEN)",
            "pax": 2,
            "scheduled_at": "2030-01-01T15:00:00Z",
            "confirm": False,
        },
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "quoted"
    assert body.get("google_event_id") is None


def test_passenger_create_ride_confirm_true_is_confirmed():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Downtown Denver",
            "dropoff": "Denver Intl (DEN)",
            "pax": 1,
            "scheduled_at": "2030-01-01T15:00:00Z",
            "confirm": True,
        },
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["status"] == "confirmed"


# --- pay-on-completion confirm endpoint -------------------------------------
def test_confirm_quoted_ride_pay_later():
    cid, tid = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid, client_id=cid, scheduled_at=_future())
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/confirm")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["payment_method"] == "cash"
    assert body["paid"] is False


def test_confirm_is_idempotent():
    cid, tid = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid, client_id=cid, scheduled_at=_future())
    c = _passenger_client(cid, tid)
    assert c.post(f"/api/v1/rides/{ride_id}/confirm").status_code == 200
    again = c.post(f"/api/v1/rides/{ride_id}/confirm")
    assert again.status_code == 200
    assert again.json()["status"] == "confirmed"


def test_confirm_other_tenant_ride_404():
    cid_a, tid_a = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid_a, client_id=cid_a, scheduled_at=_future())
    cid_b, tid_b = _seed_passenger()  # different tenant
    other = _passenger_client(cid_b, tid_b)
    r = other.post(f"/api/v1/rides/{ride_id}/confirm")
    assert r.status_code == 404, r.text


def test_confirm_same_tenant_other_client_403():
    cid_a, tid = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid, client_id=cid_a, scheduled_at=_future())
    cid_b = _seed_client_in_tenant(tid)  # same tenant, different rider
    other = _passenger_client(cid_b, tid)
    r = other.post(f"/api/v1/rides/{ride_id}/confirm")
    assert r.status_code == 403, r.text


def test_confirm_syncs_calendar(monkeypatch):
    cid, tid = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid, client_id=cid, scheduled_at=_future())
    synced = []

    async def _rec(db, ride):
        synced.append(ride.status)

    monkeypatch.setattr(booking, "sync_ride_to_calendar", _rec)
    c = _passenger_client(cid, tid)
    assert c.post(f"/api/v1/rides/{ride_id}/confirm").status_code == 200
    assert synced == [RideStatus.CONFIRMED]


# --- pay-now (Square authorize) confirms + syncs calendar -------------------
def test_authorize_confirms_and_syncs_calendar(monkeypatch):
    cid, tid = _seed_passenger()
    ride_id = _seed_ride(tenant_id=tid, client_id=cid, scheduled_at=_future())
    synced = []

    async def _rec(db, ride):
        synced.append(ride.status)

    monkeypatch.setattr(booking, "sync_ride_to_calendar", _rec)
    c = _passenger_client(cid, tid)
    r = c.post(
        "/api/v1/payments",
        json={"ride_id": ride_id, "source_id": "cnon:card-nonce-ok"},
    )
    assert r.status_code in (200, 201), r.text
    # ride now confirmed
    detail = c.get(f"/api/v1/rides/{ride_id}").json()
    assert detail["status"] == "confirmed"
    assert synced and synced[-1] == RideStatus.CONFIRMED


# --- assigned-driver contact on /trips --------------------------------------
def test_list_rides_includes_assigned_driver():
    cid, tid = _seed_passenger()
    drv = _seed_driver_tenant(phone="+13035559999", vehicle="Black Kia EV9", rating=4.98)
    _seed_ride(
        tenant_id=tid,
        client_id=cid,
        status=RideStatus.CONFIRMED,
        scheduled_at=_future(),
        assigned_tenant_id=drv,
    )
    c = _passenger_client(cid, tid)
    rows = c.get("/api/v1/rides").json()["rides"]
    assert rows, "passenger should see their ride"
    ad = rows[0].get("assigned_driver")
    assert ad is not None
    assert ad["phone"] == "+13035559999"
    assert ad["vehicle"] == "Black Kia EV9"
    assert ad["rating"] == 4.98


def test_list_rides_without_driver_has_no_contact():
    cid, tid = _seed_passenger()
    _seed_ride(tenant_id=tid, client_id=cid, status=RideStatus.QUOTED)
    c = _passenger_client(cid, tid)
    rows = c.get("/api/v1/rides").json()["rides"]
    assert rows
    assert "assigned_driver" not in rows[0]
