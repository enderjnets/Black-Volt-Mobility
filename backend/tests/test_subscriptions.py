"""Subscription orchestration (service layer), SIMULATED. DB-backed: each case
uses a unique email so it stays isolated from rows accumulated by earlier runs.

These tests drive the service directly (not the HTTP layer) so they can assert on
the persisted row count and the entitlement helper. Each test builds its own async
engine bound to the current event loop to avoid cross-loop reuse of the app's
cached engine."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["SQUARE_PLAN_OPERATOR_MONTHLY"] = "PLACEHOLDER_MONTHLY_VARIATION_ID"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Subscription  # noqa: E402
from app.services import subscriptions, subscriptions_square  # noqa: E402


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(get_settings().DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _email() -> str:
    return f"svc-{uuid.uuid4().hex[:10]}@example.com"


async def _count(db, email: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Subscription).where(Subscription.email == email)
        )
    ).scalar_one()


async def test_subscribe_simulated_creates_active_row(db):
    email = _email()
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert sub.status == subscriptions.STATUS_ACTIVE
    assert sub.simulated is True
    assert sub.square_subscription_id.startswith("SIMSUB-")
    assert sub.square_customer_id.startswith("SIMCUST-")
    assert sub.tenant_id is not None
    assert await _count(db, email) == 1


async def test_invalid_plan_raises(db):
    with pytest.raises(subscriptions_square.SubscriptionError):
        await subscriptions.subscribe(
            db, plan_key="bogus", email=_email(), source_id="cnon:card-nonce-ok"
        )


async def test_idempotent_no_duplicate(db):
    email = _email()
    a = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    b = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert a.id == b.id
    assert await _count(db, email) == 1


async def test_entitlement_tenant_is_paid(db):
    email = _email()
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert await subscriptions.tenant_is_paid(db, tenant_id=sub.tenant_id) is True


async def test_unsubscribed_tenant_not_paid(db):
    from app.services.tenancy import create_tenant_for

    tenant = await create_tenant_for(db, name=f"NoSub {uuid.uuid4().hex[:6]}")
    assert await subscriptions.tenant_is_paid(db, tenant_id=tenant.id) is False


async def test_email_is_normalized_and_idempotent_across_case(db):
    base = _email()
    mixed = base.replace("svc-", "SVC-").replace("@example.com", "@Example.COM")
    a = await subscriptions.subscribe(
        db, plan_key="operator", email=mixed, source_id="cnon:card-nonce-ok"
    )
    assert a.email == mixed.strip().lower()
    b = await subscriptions.subscribe(
        db, plan_key="operator", email=mixed.lower(), source_id="cnon:card-nonce-ok"
    )
    assert a.id == b.id
    assert await _count(db, mixed.lower()) == 1
