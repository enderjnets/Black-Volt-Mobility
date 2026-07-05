"""Dashboard notification bell: emit + list/unread, mark read/all, tenant scoping,
per-tenant retention prune, and the chat hooks (deduped message + escalation).
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client, Notification, NotificationKind  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import joules, notifications, ratelimit  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _new_tenant() -> int:
    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"notif-{os.urandom(4).hex()}")
                return tenant.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_passenger() -> tuple[int, int]:
    async def go() -> tuple[int, int]:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"notif-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Notify Rider",
                    phone="+13035550199",
                    email=f"nr-{os.urandom(4).hex()}@pgtest.local",
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


def _emit(tenant_id, kind, data=None) -> None:
    async def go() -> None:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                await notifications.emit(db, tenant_id=tenant_id, kind=kind, data=data or {})
        finally:
            await eng.dispose()

    asyncio.run(go())


def _count(tenant_id: int) -> int:
    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                return (
                    await db.execute(
                        select(func.count())
                        .select_from(Notification)
                        .where(Notification.tenant_id == tenant_id)
                    )
                ).scalar_one()
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _staff(tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME, authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tenant_id)
    )
    return c


def _passenger(client_id: int, tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME,
        authsvc.make_token(
            role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id, client_id=client_id, email="p@e.com"
        ),
    )
    return c


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    async def fake_chat(**kwargs):
        return "A flat rate, quoted upfront."

    monkeypatch.setattr(joules.llm, "providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(joules.llm, "chat_complete", fake_chat)


def test_emit_and_list_newest_first():
    tid = _new_tenant()
    _emit(tid, NotificationKind.ride_new, {"pickup": "Aurora", "dropoff": "DEN"})
    _emit(tid, NotificationKind.review_new, {"rating": 5, "author_name": "Ada"})
    res = _staff(tid).get("/api/v1/notifications").json()
    assert res["unread"] == 2
    assert [i["kind"] for i in res["items"]] == ["review_new", "ride_new"]  # newest first
    assert res["items"][1]["data"]["pickup"] == "Aurora"


def test_emit_noop_without_tenant():
    tid = _new_tenant()
    _emit(None, NotificationKind.ride_new, {})
    assert _staff(tid).get("/api/v1/notifications").json()["unread"] == 0


def test_mark_read_and_read_all():
    tid = _new_tenant()
    _emit(tid, NotificationKind.ride_new, {})
    _emit(tid, NotificationKind.ride_cancelled, {})
    staff = _staff(tid)
    first = staff.get("/api/v1/notifications").json()["items"][0]["id"]
    assert staff.post(f"/api/v1/notifications/{first}/read").status_code == 200
    assert staff.get("/api/v1/notifications").json()["unread"] == 1
    assert staff.post("/api/v1/notifications/read-all").status_code == 200
    assert staff.get("/api/v1/notifications").json()["unread"] == 0


def test_tenant_isolation():
    tid_a = _new_tenant()
    tid_b = _new_tenant()
    _emit(tid_a, NotificationKind.ride_new, {})
    a_id = _staff(tid_a).get("/api/v1/notifications").json()["items"][0]["id"]
    # tenant B sees nothing and cannot mark A's notification read
    assert _staff(tid_b).get("/api/v1/notifications").json()["items"] == []
    assert _staff(tid_b).post(f"/api/v1/notifications/{a_id}/read").status_code == 404


def test_passenger_cannot_list():
    cid, tid = _seed_passenger()
    assert _passenger(cid, tid).get("/api/v1/notifications").status_code == 403


def test_unauthenticated_is_401():
    assert TestClient(app).get("/api/v1/notifications").status_code == 401


def test_retention_prunes_to_cap():
    tid = _new_tenant()
    for _ in range(notifications.KEEP_PER_TENANT + 6):
        _emit(tid, NotificationKind.chat_message, {})
    assert _count(tid) == notifications.KEEP_PER_TENANT
    # the list endpoint still caps its own page
    assert len(_staff(tid).get("/api/v1/notifications").json()["items"]) == 30


def test_chat_message_notification_is_deduped_per_unread_batch():
    cid, tid = _seed_passenger()
    pax = _passenger(cid, tid)
    pax.post("/api/v1/chat/messages", json={"message": "hi one"})
    pax.post("/api/v1/chat/messages", json={"message": "hi two"})
    staff = _staff(tid)
    items = staff.get("/api/v1/notifications").json()["items"]
    assert [i["kind"] for i in items] == ["chat_message"]  # one, not two

    # staff opens the thread (clears unread); the next message re-notifies
    thread_id = staff.get("/api/v1/chat/threads").json()[0]["id"]
    staff.get(f"/api/v1/chat/threads/{thread_id}")
    pax.post("/api/v1/chat/messages", json={"message": "hi three"})
    kinds = [i["kind"] for i in staff.get("/api/v1/notifications").json()["items"]]
    assert kinds == ["chat_message", "chat_message"]


def test_chat_escalation_notifies_and_does_not_double_notify(monkeypatch):
    async def escalate_chat(**kwargs):
        return "[ESCALATE] A human will reach out shortly."

    monkeypatch.setattr(joules.llm, "chat_complete", escalate_chat)
    cid, tid = _seed_passenger()
    _passenger(cid, tid).post("/api/v1/chat/messages", json={"message": "I want a person"})
    items = _staff(tid).get("/api/v1/notifications").json()["items"]
    assert [i["kind"] for i in items] == ["chat_escalated"]  # escalated, no chat_message
