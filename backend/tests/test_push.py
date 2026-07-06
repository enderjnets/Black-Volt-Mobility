"""Web Push: subscribe/unsubscribe, tenant scoping, delivery + pruning, and the
passenger pickup-reminder job. No real network — pywebpush is monkeypatched.
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"
# Non-empty VAPID keys → push_enabled True (values are never validated here since
# pywebpush is mocked out).
os.environ["VAPID_PUBLIC_KEY"] = "test-public"
os.environ["VAPID_PRIVATE_KEY"] = "test-private"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client, PushSubscription, Ride, RideStatus  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import push  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_tenant_client() -> tuple[int, int]:
    """Create a tenant + one passenger client. Returns (client_id, tenant_id)."""
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"push-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Push Rider",
                    phone="+13035550188",
                    email=f"push-{os.urandom(4).hex()}@pgtest.local",
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


def _seed_sub(tenant_id: int, *, audience: str, client_id: int | None, endpoint: str) -> None:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                db.add(
                    PushSubscription(
                        tenant_id=tenant_id,
                        audience=audience,
                        client_id=client_id,
                        endpoint=endpoint,
                        p256dh="k",
                        auth="a",
                    )
                )
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _sub_count(endpoint: str) -> int:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                rows = (
                    await db.execute(
                        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
                    )
                ).scalars().all()
                return len(rows), (rows[0].audience if rows else None), (
                    rows[0].client_id if rows else None
                )
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


_SUB_BODY = {
    "endpoint": "https://push.example.com/ep-AAA",
    "keys": {"p256dh": "BPubKey", "auth": "authsecret"},
}


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakePushError(Exception):
    def __init__(self, status_code):
        super().__init__(f"fake {status_code}")
        self.response = _FakeResponse(status_code)


@pytest.fixture
def _mock_webpush(monkeypatch):
    """Replace pywebpush.webpush with a recorder. Returns the calls list; set
    ``raise_status`` on the closure to simulate an endpoint error."""
    calls = []
    state = {"raise_status": None}

    def fake(**kwargs):
        calls.append(kwargs)
        if state["raise_status"] is not None:
            raise _FakePushError(state["raise_status"])

    monkeypatch.setattr("pywebpush.webpush", fake)
    return calls, state


# ─── config / subscribe / unsubscribe ───────────────────────────────────────


def test_config_reports_enabled():
    r = TestClient(app).get("/api/v1/push/config")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["public_key"] == "test-public"


def test_staff_subscribe_creates_staff_row():
    _cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/staff-1"
    r = _staff_client(tid).post("/api/v1/push/subscribe", json={**_SUB_BODY, "endpoint": ep})
    assert r.status_code == 200
    assert r.json()["audience"] == "staff"
    count, audience, client_id = _sub_count(ep)
    assert (count, audience, client_id) == (1, "staff", None)


def test_passenger_subscribe_creates_client_row():
    cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/client-1"
    r = _passenger_client(cid, tid).post(
        "/api/v1/push/subscribe", json={**_SUB_BODY, "endpoint": ep}
    )
    assert r.status_code == 200
    assert r.json()["audience"] == "client"
    count, audience, client_id = _sub_count(ep)
    assert (count, audience, client_id) == (1, "client", cid)


def test_resubscribe_same_endpoint_upserts():
    _cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/dup"
    sc = _staff_client(tid)
    sc.post("/api/v1/push/subscribe", json={**_SUB_BODY, "endpoint": ep})
    sc.post(
        "/api/v1/push/subscribe",
        json={"endpoint": ep, "keys": {"p256dh": "NEW", "auth": "NEW"}},
    )
    count, _, _ = _sub_count(ep)
    assert count == 1  # no duplicate row


def test_unsubscribe_removes_row():
    _cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/gone"
    sc = _staff_client(tid)
    sc.post("/api/v1/push/subscribe", json={**_SUB_BODY, "endpoint": ep})
    r = sc.post("/api/v1/push/unsubscribe", json={"endpoint": ep})
    assert r.status_code == 200
    assert _sub_count(ep)[0] == 0


def test_subscribe_requires_auth():
    r = TestClient(app).post("/api/v1/push/subscribe", json=_SUB_BODY)
    assert r.status_code == 401


# ─── delivery via /push/test (mocked webpush) ───────────────────────────────


def test_test_push_delivers_to_own_tenant(_mock_webpush):
    calls, _ = _mock_webpush
    _cid, tid = _seed_tenant_client()
    _seed_sub(tid, audience="staff", client_id=None, endpoint="https://push.example.com/t-own")
    r = _staff_client(tid).post("/api/v1/push/test")
    assert r.status_code == 200
    assert r.json()["sent"] == 1
    assert len(calls) == 1


def test_test_push_is_tenant_scoped(_mock_webpush):
    calls, _ = _mock_webpush
    _cidA, tidA = _seed_tenant_client()
    _cidB, tidB = _seed_tenant_client()
    # A staff sub belongs to tenant A; tenant B's test must not reach it.
    _seed_sub(tidA, audience="staff", client_id=None, endpoint="https://push.example.com/t-A")
    r = _staff_client(tidB).post("/api/v1/push/test")
    assert r.status_code == 200
    assert r.json()["sent"] == 0
    assert calls == []


def test_dead_endpoint_is_pruned(_mock_webpush):
    _calls, state = _mock_webpush
    state["raise_status"] = 410  # Gone → subscription expired
    _cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/t-dead"
    _seed_sub(tid, audience="staff", client_id=None, endpoint=ep)
    r = _staff_client(tid).post("/api/v1/push/test")
    assert r.status_code == 200
    assert r.json()["sent"] == 0
    assert _sub_count(ep)[0] == 0  # pruned


def test_transient_error_keeps_subscription(_mock_webpush):
    _calls, state = _mock_webpush
    state["raise_status"] = 500  # transient server error → keep
    _cid, tid = _seed_tenant_client()
    ep = "https://push.example.com/t-transient"
    _seed_sub(tid, audience="staff", client_id=None, endpoint=ep)
    r = _staff_client(tid).post("/api/v1/push/test")
    assert r.status_code == 200
    assert r.json()["sent"] == 0  # not counted as delivered
    assert _sub_count(ep)[0] == 1  # but still there


# ─── pickup-reminder job ─────────────────────────────────────────────────────


def _make_ride(tenant_id: int, client_id: int | None, *, when, lang="en") -> int:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = Ride(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    status=RideStatus.CONFIRMED,
                    pickup_text="6000 S Fraser St, Aurora",
                    dropoff_text="DEN",
                    scheduled_at=when,
                    lang=lang,
                )
                db.add(ride)
                await db.commit()
                await db.refresh(ride)
                return ride.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _run_reminders(monkeypatch, result: tuple[int, int] = (1, 1)) -> tuple[int, list]:
    """Run send_due_pickup_reminders with deliver_to_client stubbed to return
    ``result`` (found, sent). Returns (count, list of client_ids it pushed to)."""
    pushed = []

    async def fake_deliver(client_id, payload):
        pushed.append(client_id)
        return result

    monkeypatch.setattr(push, "deliver_to_client", fake_deliver)

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return await push.send_due_pickup_reminders(db)
        finally:
            await eng.dispose()

    return asyncio.run(go()), pushed


def test_pickup_reminder_fires_once(monkeypatch):
    cid, tid = _seed_tenant_client()
    _make_ride(tid, cid, when=datetime.now(UTC) + timedelta(hours=1))
    n, pushed = _run_reminders(monkeypatch)
    assert n == 1
    assert pushed == [cid]
    # Second run is a no-op (dedup via pickup_reminder_sent_at).
    n2, pushed2 = _run_reminders(monkeypatch)
    assert n2 == 0
    assert pushed2 == []


def test_pickup_reminder_retries_on_transient_failure(monkeypatch):
    cid, tid = _seed_tenant_client()
    _make_ride(tid, cid, when=datetime.now(UTC) + timedelta(hours=1))
    # Live subscription but delivery failed transiently (found=1, sent=0) → NOT marked.
    n, pushed = _run_reminders(monkeypatch, result=(1, 0))
    assert n == 0
    assert pushed == [cid]
    # Next run still sees it and retries (attempts delivery again).
    n2, pushed2 = _run_reminders(monkeypatch, result=(1, 1))
    assert n2 == 1
    assert pushed2 == [cid]


def test_pickup_reminder_marks_when_no_subscription(monkeypatch):
    cid, tid = _seed_tenant_client()
    _make_ride(tid, cid, when=datetime.now(UTC) + timedelta(hours=1))
    # No device subscribed (found=0) → mark reminded so we don't retry forever.
    n, pushed = _run_reminders(monkeypatch, result=(0, 0))
    assert n == 1
    n2, _ = _run_reminders(monkeypatch, result=(0, 0))
    assert n2 == 0  # already marked, no repeat


def test_pickup_reminder_skips_far_and_unlinked(monkeypatch):
    cid, tid = _seed_tenant_client()
    _make_ride(tid, cid, when=datetime.now(UTC) + timedelta(hours=10))  # too far out
    _make_ride(tid, None, when=datetime.now(UTC) + timedelta(hours=1))  # no client
    n, pushed = _run_reminders(monkeypatch)
    assert n == 0
    assert pushed == []


# ─── no-op safety ────────────────────────────────────────────────────────────


def test_notify_helpers_are_noops_without_target():
    # Missing tenant/client → returns silently, never raises, never schedules.
    push.notify_staff(None, kind="ride_new")
    push.notify_client(1, None, event="ride_cancelled", lang="en")
    push.notify_client(None, 1, event="ride_cancelled", lang="en")
