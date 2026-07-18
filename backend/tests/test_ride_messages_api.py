"""Per-ride passenger<->driver messaging API.

Covers authorization (a passenger only sees their own ride; staff act as the
driver; cross-tenant is invisible), the chat window (booked..completed+48h),
read tracking, rate limiting, and the notification/push fan-out — all against
the isolated blackvolt_test DB, never prod.
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"
os.environ["VAPID_PUBLIC_KEY"] = "test-public"
os.environ["VAPID_PRIVATE_KEY"] = "test-private"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client, Notification, NotificationKind, Ride, RideStatus  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import push, ratelimit  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_tenant_client(name="rider") -> tuple[int, int]:
    """Create a tenant + one passenger client. Returns (client_id, tenant_id)."""
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"{name}-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name=f"{name.title()} Rider",
                    phone="+13035550188",
                    email=f"{name}-{os.urandom(4).hex()}@pgtest.local",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                    lang="en",
                )
                db.add(client)
                await db.commit()
                await db.refresh(client)
                return client.id, tenant.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_client_in(tenant_id: int) -> int:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                client = Client(
                    tenant_id=tenant_id,
                    name="Other Rider",
                    phone="+13035550111",
                    email=f"other-{os.urandom(4).hex()}@pgtest.local",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                    lang="en",
                )
                db.add(client)
                await db.commit()
                await db.refresh(client)
                return client.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _make_ride(
    tenant_id: int,
    client_id: int | None,
    *,
    status=RideStatus.CONFIRMED,
    updated_at=None,
) -> int:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                kwargs = dict(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    status=status,
                    pickup_text="6000 S Fraser St, Aurora",
                    dropoff_text="DEN",
                    # Far out so these seed rides never fall into the shared
                    # session DB's pickup-reminder window and pollute test_push.
                    scheduled_at=datetime.now(UTC) + timedelta(days=30),
                    lang="en",
                )
                if updated_at is not None:
                    kwargs["updated_at"] = updated_at
                ride = Ride(**kwargs)
                db.add(ride)
                await db.commit()
                await db.refresh(ride)
                return ride.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _staff_client(tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME, authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tenant_id)
    )
    return c


def _passenger_client(client_id: int, tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME,
        authsvc.make_token(
            role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id, client_id=client_id, email="p@e.com"
        ),
    )
    return c


def _notif_count(tenant_id: int, kind: NotificationKind) -> int:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return (
                    await db.execute(
                        select(func.count())
                        .select_from(Notification)
                        .where(Notification.tenant_id == tenant_id, Notification.kind == kind)
                    )
                ).scalar_one()
        finally:
            await eng.dispose()

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    ratelimit.reset()
    yield
    ratelimit.reset()


# ── happy path ────────────────────────────────────────────────────────────────
def test_passenger_sends_and_driver_receives():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    p = _passenger_client(cid, tid)

    r = p.post(f"/api/v1/rides/{ride}/messages", json={"body": "Running 5 min late"})
    assert r.status_code == 201, r.text
    assert r.json()["sender"] == "client"
    assert r.json()["body"] == "Running 5 min late"

    # A staff bell notification was recorded for the tenant.
    assert _notif_count(tid, NotificationKind.ride_message) == 1

    # The driver reads the thread and sees the message.
    s = _staff_client(tid)
    g = s.get(f"/api/v1/rides/{ride}/messages")
    assert g.status_code == 200
    body = g.json()
    assert [m["body"] for m in body["messages"]] == ["Running 5 min late"]
    assert body["chat_open"] is True


def test_driver_reply_visible_to_passenger():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    s = _staff_client(tid)
    r = s.post(f"/api/v1/rides/{ride}/messages", json={"body": "On my way"})
    assert r.status_code == 201
    assert r.json()["sender"] == "driver"

    p = _passenger_client(cid, tid)
    g = p.get(f"/api/v1/rides/{ride}/messages")
    assert [m["sender"] for m in g.json()["messages"]] == ["driver"]


# ── authorization ───────────────────────────────────────────────────────────
def test_cross_client_forbidden():
    cid, tid = _seed_tenant_client()
    other_cid = _seed_client_in(tid)
    ride = _make_ride(tid, cid)  # belongs to cid
    intruder = _passenger_client(other_cid, tid)

    assert intruder.get(f"/api/v1/rides/{ride}/messages").status_code == 403
    assert (
        intruder.post(f"/api/v1/rides/{ride}/messages", json={"body": "hi"}).status_code == 403
    )


def test_cross_tenant_not_found_for_staff():
    cid_a, tid_a = _seed_tenant_client("a")
    ride_a = _make_ride(tid_a, cid_a)
    _, tid_b = _seed_tenant_client("b")
    staff_b = _staff_client(tid_b)

    assert staff_b.get(f"/api/v1/rides/{ride_a}/messages").status_code == 404
    assert (
        staff_b.post(f"/api/v1/rides/{ride_a}/messages", json={"body": "hi"}).status_code == 404
    )


def test_requires_auth():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    anon = TestClient(app)
    assert anon.get(f"/api/v1/rides/{ride}/messages").status_code == 401
    assert anon.post(f"/api/v1/rides/{ride}/messages", json={"body": "hi"}).status_code == 401


# ── chat window ─────────────────────────────────────────────────────────────
def test_post_blocked_before_booking_and_after_cancel():
    cid, tid = _seed_tenant_client()
    p = _passenger_client(cid, tid)
    for st in (RideStatus.QUOTED, RideStatus.CANCELLED):
        ride = _make_ride(tid, cid, status=st)
        r = p.post(f"/api/v1/rides/{ride}/messages", json={"body": "hi"})
        assert r.status_code == 409, (st, r.text)
        assert r.json()["detail"] == "chat_closed"
        # History stays readable even when closed.
        assert p.get(f"/api/v1/rides/{ride}/messages").status_code == 200


def test_completed_within_grace_open_beyond_closed():
    cid, tid = _seed_tenant_client()
    p = _passenger_client(cid, tid)

    fresh = _make_ride(
        tid, cid, status=RideStatus.COMPLETED, updated_at=datetime.now(UTC) - timedelta(hours=1)
    )
    assert p.post(f"/api/v1/rides/{fresh}/messages", json={"body": "thanks!"}).status_code == 201

    stale = _make_ride(
        tid, cid, status=RideStatus.COMPLETED, updated_at=datetime.now(UTC) - timedelta(hours=49)
    )
    r = p.post(f"/api/v1/rides/{stale}/messages", json={"body": "too late"})
    assert r.status_code == 409
    assert p.get(f"/api/v1/rides/{stale}/messages").json()["chat_open"] is False


# ── read tracking ───────────────────────────────────────────────────────────
def test_reads_are_one_sided():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    p = _passenger_client(cid, tid)
    s = _staff_client(tid)

    s.post(f"/api/v1/rides/{ride}/messages", json={"body": "d1"})
    s.post(f"/api/v1/rides/{ride}/messages", json={"body": "d2"})
    p.post(f"/api/v1/rides/{ride}/messages", json={"body": "c1"})

    # Passenger opens: clears their unread (the 2 driver msgs) only.
    p.get(f"/api/v1/rides/{ride}/messages")
    # Passenger's list unread is now 0; the driver still has the passenger's 1 unread.
    assert _list_unread(p, ride) == 0
    assert _list_unread(s, ride) == 1

    # Driver opens: clears their unread too.
    s.get(f"/api/v1/rides/{ride}/messages")
    assert _list_unread(s, ride) == 0


def _list_unread(client: TestClient, ride_id: int) -> int:
    rows = client.get("/api/v1/rides").json()["rides"]
    for r in rows:
        if r["id"] == ride_id:
            return r["unread_messages"]
    raise AssertionError(f"ride {ride_id} not in list")


def test_rides_list_exposes_unread_and_chat_open():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    s = _staff_client(tid)
    p = _passenger_client(cid, tid)

    rows = p.get("/api/v1/rides").json()["rides"]
    row = next(r for r in rows if r["id"] == ride)
    assert row["unread_messages"] == 0
    assert row["chat_open"] is True

    s.post(f"/api/v1/rides/{ride}/messages", json={"body": "hello"})
    assert _list_unread(p, ride) == 1


# ── validation & rate limit ─────────────────────────────────────────────────
def test_empty_body_rejected():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    p = _passenger_client(cid, tid)
    assert p.post(f"/api/v1/rides/{ride}/messages", json={"body": "   "}).status_code == 422
    assert p.post(f"/api/v1/rides/{ride}/messages", json={"body": ""}).status_code == 422


def test_rate_limit_kicks_in():
    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    p = _passenger_client(cid, tid)
    codes = [
        p.post(f"/api/v1/rides/{ride}/messages", json={"body": f"m{i}"}).status_code
        for i in range(11)
    ]
    assert codes[:10] == [201] * 10
    assert codes[10] == 429


# ── fan-out routing ─────────────────────────────────────────────────────────
def test_client_send_notifies_staff_not_client(monkeypatch):
    staff_calls, client_calls = [], []
    monkeypatch.setattr(push, "notify_staff", lambda *a, **k: staff_calls.append((a, k)))
    monkeypatch.setattr(push, "notify_client", lambda *a, **k: client_calls.append((a, k)))

    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    p = _passenger_client(cid, tid)
    assert p.post(f"/api/v1/rides/{ride}/messages", json={"body": "hi"}).status_code == 201

    assert len(staff_calls) == 1
    assert staff_calls[0][1].get("kind") == "ride_message"
    assert client_calls == []


def test_driver_send_pushes_client_not_staff(monkeypatch):
    staff_calls, client_calls = [], []
    monkeypatch.setattr(push, "notify_staff", lambda *a, **k: staff_calls.append((a, k)))
    monkeypatch.setattr(push, "notify_client", lambda *a, **k: client_calls.append((a, k)))

    cid, tid = _seed_tenant_client()
    ride = _make_ride(tid, cid)
    s = _staff_client(tid)
    assert s.post(f"/api/v1/rides/{ride}/messages", json={"body": "omw"}).status_code == 201

    assert len(client_calls) == 1
    assert client_calls[0][1].get("event") == "ride_message"
    # A driver->client message must not ring the driver's own bell.
    assert staff_calls == []
