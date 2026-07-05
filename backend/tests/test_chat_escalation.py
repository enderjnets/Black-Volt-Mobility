"""Joules escalation: the [ESCALATE] marker flips the conversation to escalated,
strips the marker from the stored/returned text, and fires the owner email
exactly once — and a total LLM failure escalates via the fallback. The email
send is monkeypatched; a raising send must never break the reply.
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
from app.models import AllowedUser, Client  # noqa: E402
from app.services import auth as authsvc  # noqa: E402
from app.services import email, joules, ratelimit  # noqa: E402
from app.services.tenancy import create_tenant_for  # noqa: E402


def _session_factory():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _seed_passenger() -> tuple[int, int]:
    async def go() -> tuple[int, int]:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"esct-{os.urandom(4).hex()}")
                # The owner (escalation-email recipient) for this tenant.
                db.add(
                    AllowedUser(
                        email=f"owner-{os.urandom(4).hex()}@pgtest.local",
                        role="driver",
                        active=True,
                        tenant_id=tenant.id,
                        name="Tenant Owner",
                    )
                )
                client = Client(
                    tenant_id=tenant.id,
                    name="Esc Rider",
                    phone="+13035550122",
                    email=f"esc-{os.urandom(4).hex()}@pgtest.local",
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
        role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id, client_id=client_id, email="e@e.com"
    )
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    return c


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    ratelimit.reset()
    yield
    ratelimit.reset()


def _mock_reply(monkeypatch, text: str):
    async def fake_chat(**kwargs):
        return text

    monkeypatch.setattr(joules.llm, "providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(joules.llm, "chat_complete", fake_chat)


def _capture_email(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def fake_send(*, to, subject, body_text, body_html=None):
        sent.append({"to": to, "subject": subject, "body": body_text})
        return {"id": "test", "simulated": True}

    monkeypatch.setattr(email, "send_email", fake_send)
    return sent


def test_marker_escalates_strips_and_emails_owner(monkeypatch):
    _mock_reply(monkeypatch, "[ESCALATE] No problem — Ender will reach out shortly.")
    sent = _capture_email(monkeypatch)
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)

    r = c.post("/api/v1/chat/messages", json={"message": "I want to talk to a human"}).json()
    assert r["escalated"] is True
    assert "[ESCALATE]" not in r["reply"]
    assert r["reply"].startswith("No problem")

    assert c.get("/api/v1/chat").json()["status"] == "escalated"
    assert len(sent) == 1
    # the client's contact is in the escalation email
    assert "Esc Rider" in sent[0]["subject"] or "Esc Rider" in sent[0]["body"]


def test_second_escalation_does_not_re_email(monkeypatch):
    _mock_reply(monkeypatch, "[ESCALATE] Ender will reach out.")
    sent = _capture_email(monkeypatch)
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)

    c.post("/api/v1/chat/messages", json={"message": "human please"})
    c.post("/api/v1/chat/messages", json={"message": "still want a human"})
    assert len(sent) == 1  # only the transition open→escalated emails


def test_email_failure_does_not_break_reply(monkeypatch):
    _mock_reply(monkeypatch, "[ESCALATE] Ender will reach out.")

    async def boom(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(email, "send_email", boom)
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)

    r = c.post("/api/v1/chat/messages", json={"message": "human"})
    assert r.status_code == 200
    assert r.json()["escalated"] is True


def test_total_llm_failure_falls_back_and_escalates(monkeypatch):
    async def fail(**kwargs):
        raise joules.llm.LLMError("chat:Boom")

    monkeypatch.setattr(joules.llm, "providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(joules.llm, "chat_complete", fail)
    sent = _capture_email(monkeypatch)
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)

    r = c.post("/api/v1/chat/messages", json={"message": "hello"}).json()
    assert r["escalated"] is True
    assert "Ender" in r["reply"]
    assert len(sent) == 1


def test_no_providers_configured_falls_back(monkeypatch):
    monkeypatch.setattr(joules.llm, "providers", lambda: [])
    _capture_email(monkeypatch)
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    r = c.post("/api/v1/chat/messages", json={"message": "hi"}).json()
    assert r["escalated"] is True
    assert "Ender" in r["reply"]
