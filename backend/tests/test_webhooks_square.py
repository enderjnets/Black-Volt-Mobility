"""Square subscription webhook: signature verification + event→status sync.

DB-backed (service layer) plus HTTP signature tests. Each case uses a unique
square_subscription_id/email so it stays isolated from accumulated rows."""
import base64
import hashlib
import hmac
import json
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["PAYMENTS_SIMULATED"] = "true"

import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Subscription, SubscriptionStatus, Tenant  # noqa: E402
from app.services import webhooks_square  # noqa: E402

_KEY = "whsig_test_key"
_URL = "https://driver.blackvoltmobility.com/api/v1/webhooks/square"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def _seed(db, *, status=SubscriptionStatus.PENDING, simulated=False) -> Subscription:
    tid = (await db.execute(select(Tenant.id).limit(1))).scalars().first()
    sub = Subscription(
        tenant_id=tid,
        email=f"wh-{uuid.uuid4().hex[:10]}@example.com",
        plan_key="operator",
        status=status,
        square_subscription_id=f"WHSUB-{uuid.uuid4().hex}",
        square_customer_id="WHCUST-1",
        simulated=simulated,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


def _sub_event(etype: str, sub_id: str, *, status=None, charged_through=None) -> dict:
    subscription = {"id": sub_id}
    if status is not None:
        subscription["status"] = status
    if charged_through is not None:
        subscription["charged_through_date"] = charged_through
    return {"type": etype, "data": {"object": {"subscription": subscription}}}


def _invoice_event(etype: str, sub_id: str) -> dict:
    return {"type": etype, "data": {"object": {"invoice": {"subscription_id": sub_id}}}}


# ── signature ────────────────────────────────────────────────────────────────


def _sign(body: bytes, key: str = _KEY, url: str = _URL) -> str:
    return base64.b64encode(
        hmac.new(key.encode(), url.encode() + body, hashlib.sha256).digest()
    ).decode()


def test_verify_signature_requires_key_and_url(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_SIGNATURE_KEY", "", raising=False)
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_URL", "", raising=False)
    assert webhooks_square.verify_signature(body=b"{}", signature=_sign(b"{}")) is False


def test_verify_signature_valid_and_invalid(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_SIGNATURE_KEY", _KEY, raising=False)
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_URL", _URL, raising=False)
    body = b'{"type":"subscription.updated"}'
    assert webhooks_square.verify_signature(body=body, signature=_sign(body)) is True
    assert webhooks_square.verify_signature(body=body, signature="deadbeef") is False
    assert webhooks_square.verify_signature(body=body, signature="") is False


# ── apply_event ──────────────────────────────────────────────────────────────


async def test_subscription_updated_active_sets_active_and_period(db):
    sub = await _seed(db, status=SubscriptionStatus.PENDING)
    ev = _sub_event(
        "subscription.updated", sub.square_subscription_id,
        status="ACTIVE", charged_through="2026-07-11",
    )
    await webhooks_square.apply_event(db, event=ev)
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.current_period_end is not None
    assert sub.current_period_end.year == 2026 and sub.current_period_end.month == 7


async def test_subscription_updated_canceled(db):
    for sq_status in ("CANCELED", "DEACTIVATED"):
        s2 = await _seed(db, status=SubscriptionStatus.ACTIVE)
        ev = _sub_event("subscription.updated", s2.square_subscription_id, status=sq_status)
        await webhooks_square.apply_event(db, event=ev)
        await db.refresh(s2)
        assert s2.status == SubscriptionStatus.CANCELED


async def test_invoice_payment_made_sets_active(db):
    sub = await _seed(db, status=SubscriptionStatus.PENDING)
    await webhooks_square.apply_event(
        db, event=_invoice_event("invoice.payment_made", sub.square_subscription_id)
    )
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE


async def test_invoice_failed_sets_past_due(db):
    sub = await _seed(db, status=SubscriptionStatus.ACTIVE)
    await webhooks_square.apply_event(
        db, event=_invoice_event("invoice.scheduled_charge_failed", sub.square_subscription_id)
    )
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.PAST_DUE


async def test_unknown_subscription_is_noop(db):
    res = await webhooks_square.apply_event(
        db, event=_sub_event("subscription.updated", "WHSUB-does-not-exist", status="ACTIVE")
    )
    assert res == "ignored"


async def test_simulated_row_is_not_touched(db):
    sub = await _seed(db, status=SubscriptionStatus.PENDING, simulated=True)
    res = await webhooks_square.apply_event(
        db, event=_sub_event("subscription.updated", sub.square_subscription_id, status="ACTIVE")
    )
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.PENDING
    assert res == "ignored"


async def test_redelivery_is_idempotent(db):
    sub = await _seed(db, status=SubscriptionStatus.PENDING)
    ev = _invoice_event("invoice.payment_made", sub.square_subscription_id)
    await webhooks_square.apply_event(db, event=ev)
    await webhooks_square.apply_event(db, event=ev)  # redelivery
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE


# ── HTTP endpoint (signature gate) ───────────────────────────────────────────


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_endpoint_rejects_when_not_configured():
    c = _client()
    body = json.dumps(_sub_event("subscription.updated", "x", status="ACTIVE")).encode()
    r = c.post(
        "/api/v1/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256": _sign(body), "Content-Type": "application/json"},
    )
    assert r.status_code == 403, r.text


def test_endpoint_accepts_valid_signature(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_SIGNATURE_KEY", _KEY, raising=False)
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_URL", _URL, raising=False)
    c = _client()
    body = json.dumps(_sub_event("subscription.updated", "WHSUB-none", status="ACTIVE")).encode()
    r = c.post(
        "/api/v1/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256": _sign(body), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_endpoint_rejects_bad_signature(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_SIGNATURE_KEY", _KEY, raising=False)
    monkeypatch.setattr(s, "SQUARE_WEBHOOK_URL", _URL, raising=False)
    c = _client()
    body = json.dumps(_sub_event("subscription.updated", "x", status="ACTIVE")).encode()
    r = c.post(
        "/api/v1/webhooks/square",
        content=body,
        headers={"x-square-hmacsha256": "wrong", "Content-Type": "application/json"},
    )
    assert r.status_code == 403, r.text
