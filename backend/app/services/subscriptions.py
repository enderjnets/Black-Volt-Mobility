"""Subscription orchestration: validate the plan, provision the driver's tenant,
drive the Square adapter, and persist the Subscription row. Tenant-scoped.

A brand-new driver subscribes from the landing before they have a session, so the
flow is keyed on their email: a repeat subscribe for the same email+plan returns
the existing active row (idempotent) instead of double-charging. An active row
marks the tenant as paid (`tenant_is_paid`)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Subscription, SubscriptionStatus
from app.services import subscriptions_square as adapter
from app.services.tenancy import create_tenant_for

STATUS_ACTIVE = SubscriptionStatus.ACTIVE


class InvalidPlanError(adapter.SubscriptionError):
    public_code = "invalid_plan"


async def _active_for(db: AsyncSession, *, email: str, plan_key: str) -> Subscription | None:
    return (
        await db.execute(
            select(Subscription).where(
                Subscription.email == email,
                Subscription.plan_key == plan_key,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
    ).scalars().first()


async def subscribe(
    db: AsyncSession, *, plan_key: str, email: str, source_id: str
) -> Subscription:
    """Subscribe a driver to a plan. Idempotent on (email, plan_key) while active.
    Raises adapter.SubscriptionError('invalid_plan') for an unknown plan_key."""
    settings = get_settings()
    plan_variation_id = settings.subscription_plan(plan_key)
    if plan_variation_id is None:
        raise InvalidPlanError(f"unknown plan_key: {plan_key}")

    existing = await _active_for(db, email=email, plan_key=plan_key)
    if existing is not None:
        return existing

    # New driver → provision their own isolated workspace (tenant + default rates).
    tenant = await create_tenant_for(db, name=email)

    customer = await adapter.create_customer(email=email)
    card = await adapter.create_card(customer_id=customer.square_customer_id, source_id=source_id)
    result = await adapter.create_subscription(
        plan_variation_id=plan_variation_id,
        customer_id=customer.square_customer_id,
        card_id=card.square_card_id,
        location_id=settings.SQUARE_LOCATION_ID,
    )

    sub = Subscription(
        tenant_id=tenant.id,
        email=email,
        plan_key=plan_key,
        status=SubscriptionStatus.ACTIVE,
        square_subscription_id=result.square_subscription_id,
        square_customer_id=customer.square_customer_id,
        current_period_end=result.current_period_end,
        simulated=result.simulated,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def tenant_is_paid(db: AsyncSession, *, tenant_id: int) -> bool:
    """Entitlement: the tenant has at least one active subscription → paid plan
    (unlocks AI features + public profile)."""
    row = (
        await db.execute(
            select(Subscription.id).where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
    ).first()
    return row is not None
