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


async def test_db_enforces_one_open_subscription_per_email_plan(db):
    """The schema (not just app code) owns the no-duplicate invariant: inserting
    a second non-canceled row for the same email+plan violates the partial
    unique index."""
    from sqlalchemy.exc import IntegrityError

    from app.models import SubscriptionStatus

    email = _email()
    db.add(Subscription(tenant_id=1, email=email, plan_key="operator",
                        status=SubscriptionStatus.ACTIVE, simulated=True))
    await db.commit()
    db.add(Subscription(tenant_id=1, email=email, plan_key="operator",
                        status=SubscriptionStatus.PENDING, simulated=True))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_live_mode_rejects_unconfigured_plan(db, monkeypatch):
    """A known plan_key whose variation id env is unset must fail fast in live
    mode (before any Square call / card vaulting), not send '' to Square."""
    s = get_settings()
    monkeypatch.setattr(s, "PAYMENTS_SIMULATED", False)
    monkeypatch.setattr(s, "SQUARE_ACCESS_TOKEN", "fake-token")
    monkeypatch.setattr(s, "SQUARE_LOCATION_ID", "fake-loc")
    assert s.payments_live is True
    with pytest.raises(subscriptions.InvalidPlanError):
        await subscriptions.subscribe(
            db, plan_key="operator_annual", email=_email(), source_id="cnon:x"
        )


async def test_production_with_simulated_payments_is_unavailable(db, monkeypatch):
    """Anti-pattern guard: in production with payments simulated, the public
    endpoint must refuse instead of minting free ACTIVE subscriptions."""
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    with pytest.raises(subscriptions.SubscriptionsUnavailableError):
        await subscriptions.subscribe(
            db, plan_key="operator", email=_email(), source_id="cnon:x"
        )


def test_idempotency_keys_are_deterministic_per_intent():
    """Retrying the SAME checkout (same nonce) must reuse the same Square
    idempotency keys so Square collapses duplicates; a NEW checkout (new nonce)
    gets fresh keys. A random-per-attempt key would double-bill on a lost
    response."""
    k1 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-A")
    k2 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-A")
    k3 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-B")
    assert k1 == k2
    assert k1 != k3
    uuid.UUID(k1)  # valid uuid string


def test_parse_square_date():
    from datetime import UTC, datetime

    assert subscriptions_square._parse_square_date("2026-07-11") == datetime(
        2026, 7, 11, tzinfo=UTC
    )
    assert subscriptions_square._parse_square_date(None) is None
    assert subscriptions_square._parse_square_date("garbage") is None


async def test_cancel_subscription_simulated_is_noop():
    await subscriptions_square.cancel_subscription(subscription_id="SIMSUB-x")  # no raise
