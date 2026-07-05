"""Joules chat API — passenger endpoints: auth gating, happy path, history,
validation, rate limiting, get-or-create + reopen. The LLM is monkeypatched so
no provider is ever contacted.
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

# ─── seed helpers ────────────────────────────────────────────────────────────


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_passenger() -> tuple[int, int]:
    async def go() -> tuple[int, int]:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"chatt-{os.urandom(4).hex()}")
                client = Client(
                    tenant_id=tenant.id,
                    name="Chat Rider",
                    phone="+13035550111",
                    email=f"chat-{os.urandom(4).hex()}@pgtest.local",
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
    token = authsvc.make_token(
        role=authsvc.ROLE_PASSENGER,
        tenant_id=tenant_id,
        email="chat@example.com",
        client_id=client_id,
    )
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    return c


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    async def fake_chat(**kwargs):
        return "Denver metro to DEN is a flat rate, quoted upfront."

    monkeypatch.setattr(joules.llm, "providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(joules.llm, "chat_complete", fake_chat)


# ─── tests ───────────────────────────────────────────────────────────────────


def test_anonymous_is_rejected():
    c = TestClient(app)
    assert c.get("/api/v1/chat").status_code in (401, 403)
    assert c.post("/api/v1/chat/messages", json={"message": "hi"}).status_code in (401, 403)


def test_staff_token_cannot_use_passenger_endpoints():
    _, tid = _seed_passenger()
    token = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid)
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    assert c.post("/api/v1/chat/messages", json={"message": "hi"}).status_code == 403


def test_happy_path_stores_both_turns_and_returns_reply():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    r = c.post("/api/v1/chat/messages", json={"message": "How much to the airport?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("Denver metro")
    assert body["escalated"] is False
    assert body["conversation_id"] > 0

    hist = c.get("/api/v1/chat").json()
    assert hist["conversation_id"] == body["conversation_id"]
    assert hist["status"] == "open"
    roles = [m["role"] for m in hist["messages"]]
    assert roles == ["user", "assistant"]
    assert hist["messages"][0]["body"] == "How much to the airport?"


def test_get_history_empty_when_no_conversation():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    body = c.get("/api/v1/chat").json()
    assert body == {"conversation_id": None, "status": None, "messages": []}


def test_empty_and_oversized_messages_are_422():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    assert c.post("/api/v1/chat/messages", json={"message": "   "}).status_code == 422
    big = "x" * (joules.MAX_MESSAGE_CHARS + 1)
    assert c.post("/api/v1/chat/messages", json={"message": big}).status_code == 422


def test_rate_limited_after_burst():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    codes = [
        c.post("/api/v1/chat/messages", json={"message": f"q{i}"}).status_code
        for i in range(6)
    ]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


def test_conversation_is_singleton_and_reopens_when_closed():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    id1 = c.post("/api/v1/chat/messages", json={"message": "first"}).json()["conversation_id"]
    id2 = c.post("/api/v1/chat/messages", json={"message": "second"}).json()["conversation_id"]
    assert id1 == id2

    # Owner closes it, then a new passenger message must reopen the SAME conversation.
    owner = TestClient(app)
    owner.cookies.set(
        authsvc.COOKIE_NAME, authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=tid)
    )
    assert owner.post(f"/api/v1/chat/threads/{id1}/close").status_code == 200
    id3 = c.post("/api/v1/chat/messages", json={"message": "again"}).json()["conversation_id"]
    assert id3 == id1
    assert c.get("/api/v1/chat").json()["status"] == "open"
