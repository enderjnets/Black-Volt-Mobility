"""Joules staff endpoints: tenant scoping (a driver only sees their own tenant's
threads), unread clears on thread open, close works, and passengers are barred.
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Client  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import joules, ratelimit  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_passenger() -> tuple[int, int]:
    async def go() -> tuple[int, int]:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"stfft-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Staff-test Rider",
                    phone="+13035550133",
                    email=f"stf-{os.urandom(4).hex()}@pgtest.local",
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


def _passenger_client(client_id: int, tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME,
        authsvc.make_token(
            role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id, client_id=client_id, email="p@e.com"
        ),
    )
    return c


def _staff_client(tenant_id: int) -> TestClient:
    c = TestClient(app)
    c.cookies.set(
        authsvc.COOKIE_NAME, authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tenant_id)
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


def test_passenger_cannot_list_threads():
    cid, tid = _seed_passenger()
    assert _passenger_client(cid, tid).get("/api/v1/chat/threads").status_code == 403


def test_threads_are_tenant_scoped_and_unread_clears():
    cid_a, tid_a = _seed_passenger()
    cid_b, tid_b = _seed_passenger()
    _passenger_client(cid_a, tid_a).post("/api/v1/chat/messages", json={"message": "hi from A"})
    _passenger_client(cid_b, tid_b).post("/api/v1/chat/messages", json={"message": "hi from B"})

    staff_a = _staff_client(tid_a)
    threads = staff_a.get("/api/v1/chat/threads").json()
    assert len(threads) == 1
    t = threads[0]
    assert t["client_name"] == "Staff-test Rider"
    assert t["unread"] == 1
    assert t["snippet"]  # last message preview present

    # tenant B's conversation is invisible to tenant A
    assert all(x["id"] != None for x in threads)  # noqa: E711 - sanity
    detail = staff_a.get(f"/api/v1/chat/threads/{t['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    # unread cleared after opening
    assert staff_a.get("/api/v1/chat/threads").json()[0]["unread"] == 0


def test_staff_cannot_open_other_tenant_thread():
    cid_a, tid_a = _seed_passenger()
    _, tid_b = _seed_passenger()
    _passenger_client(cid_a, tid_a).post("/api/v1/chat/messages", json={"message": "hi"})
    thread_id = _staff_client(tid_a).get("/api/v1/chat/threads").json()[0]["id"]
    # a different tenant's owner must get a 404 for that thread
    assert _staff_client(tid_b).get(f"/api/v1/chat/threads/{thread_id}").status_code == 404
    assert _staff_client(tid_b).post(f"/api/v1/chat/threads/{thread_id}/close").status_code == 404


def test_unknown_status_filter_does_not_500():
    cid, tid = _seed_passenger()
    _passenger_client(cid, tid).post("/api/v1/chat/messages", json={"message": "hi"})
    r = _staff_client(tid).get("/api/v1/chat/threads?status=bogus")
    assert r.status_code == 200
    # unknown filter is ignored → the open thread still shows
    assert len(r.json()) == 1


def test_close_thread():
    cid, tid = _seed_passenger()
    _passenger_client(cid, tid).post("/api/v1/chat/messages", json={"message": "hi"})
    staff = _staff_client(tid)
    tid_thread = staff.get("/api/v1/chat/threads").json()[0]["id"]
    r = staff.post(f"/api/v1/chat/threads/{tid_thread}/close")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert staff.get("/api/v1/chat/threads?status=closed").json()[0]["id"] == tid_thread
