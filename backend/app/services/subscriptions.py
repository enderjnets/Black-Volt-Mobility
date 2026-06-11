"""Subscription orchestration: validate the plan, resolve the driver's identity
(allowed_users), drive the Square adapter, and persist atomically. Tenant-scoped.

Flow order is a security invariant: all Square calls happen BEFORE any local
write, and tenant + allowed_user + subscription land in ONE transaction — a
declined card leaves zero rows behind. The driver's identity is the lowercased
email: an existing allowed_user keeps their tenant (the subscription unlocks the
workspace they actually log into); a brand-new subscriber gets a tenant AND an
active allowed_users row so they can sign in with Google immediately."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AllowedUser, Subscription, SubscriptionStatus
from app.models.allowed_user import ROLE_DRIVER
from app.services import subscriptions_square as adapter
from app.services.tenancy import create_tenant_for


class InvalidPlanError(adapter.SubscriptionError):
    public_code = "invalid_plan"


class AccountDisabledError(adapter.SubscriptionError):
    public_code = "account_disabled"


class SubscriptionsUnavailableError(adapter.SubscriptionError):
    public_code = "subscriptions_unavailable"


# Square statuses we trust to mean "money confirmed". Anything else (PENDING,
# unknown, missing) persists as PENDING — present but NOT entitled.
_STATUS_MAP = {"ACTIVE": SubscriptionStatus.ACTIVE, "PENDING": SubscriptionStatus.PENDING}


async def _current_for(db: AsyncSession, *, email: str, plan_key: str) -> Subscription | None:
    """The OPEN (non-canceled) subscription for email+plan, if any. Open — not
    just active — so a pending/past_due row also blocks a duplicate charge."""
    return (
        await db.execute(
            select(Subscription).where(
                Subscription.email == email,
                Subscription.plan_key == plan_key,
                Subscription.status != SubscriptionStatus.CANCELED,
            )
        )
    ).scalars().first()


async def subscribe(
    db: AsyncSession, *, plan_key: str, email: str, source_id: str
) -> Subscription:
    """Subscribe a driver to a plan. Idempotent on (email, plan_key) while open."""
    # Normalize here too — direct callers (tests, future webhooks) must hit the
    # same canonical identity as the API boundary.
    email = (email or "").strip().lower()
    settings = get_settings()
    # Anti-pattern #5 guard: NEVER serve simulated subscriptions in production —
    # they would mint free ACTIVE entitlements for anyone who POSTs.
    if settings.is_production and not settings.payments_live:
        raise SubscriptionsUnavailableError("production requires payments_live")

    plan_variation_id = settings.subscription_plan(plan_key)
    # None → unknown key. Empty string → known key whose variation id env is
    # unset: fine while simulated, but live it must fail BEFORE vaulting a card.
    if plan_variation_id is None or (settings.payments_live and not plan_variation_id):
        raise InvalidPlanError(f"plan not available: {plan_key}")

    existing = await _current_for(db, email=email, plan_key=plan_key)
    if existing is not None:
        return existing

    allowed = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if allowed is not None and not allowed.active:
        # Deactivated by the owner — refuse BEFORE charging the card.
        raise AccountDisabledError(f"allowed_user inactive: {email}")

    # ── Square first: a payment failure must leave NO local rows behind. ──
    customer = await adapter.create_customer(email=email, idempotency_seed=source_id)
    card = await adapter.create_card(customer_id=customer.square_customer_id, source_id=source_id)
    result = await adapter.create_subscription(
        plan_variation_id=plan_variation_id,
        customer_id=customer.square_customer_id,
        card_id=card.square_card_id,
        location_id=settings.SQUARE_LOCATION_ID,
        idempotency_seed=source_id,
    )

    # ── One atomic transaction: tenant + allowed_user + subscription. ──
    tenant_id = allowed.tenant_id if allowed is not None else None
    if tenant_id is None:
        # Name from the email's local part only — the full email must not leak
        # into the public tenant slug.
        tenant = await create_tenant_for(db, name=email.split("@", 1)[0], commit=False)
        tenant_id = tenant.id
        if allowed is None:
            allowed = AllowedUser(
                email=email, role=ROLE_DRIVER, active=True,
                tenant_id=tenant_id, added_by="subscription",
            )
            db.add(allowed)
        else:
            allowed.tenant_id = tenant_id

    sub = Subscription(
        tenant_id=tenant_id,
        email=email,
        plan_key=plan_key,
        status=_STATUS_MAP.get((result.status or "").upper(), SubscriptionStatus.PENDING),
        square_subscription_id=result.square_subscription_id,
        square_customer_id=customer.square_customer_id,
        current_period_end=result.current_period_end,
        simulated=result.simulated,
    )
    db.add(sub)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a concurrent race on uq_subscriptions_email_plan_open: undo our
        # local rows, cancel OUR duplicate Square subscription (best-effort),
        # and return the winner's.
        await db.rollback()
        await adapter.cancel_subscription(subscription_id=result.square_subscription_id)
        winner = await _current_for(db, email=email, plan_key=plan_key)
        if winner is not None:
            return winner
        raise adapter.SubscriptionError(
            f"subscription insert conflict without a winner row: {email}",
            public_code="subscription_conflict",
        ) from None
    await db.refresh(sub)
    return sub


async def tenant_is_paid(db: AsyncSession, *, tenant_id: int) -> bool:
    """Entitlement marker: the tenant has an ACTIVE subscription. In production
    simulated rows never count — only real Square money grants entitlement."""
    conditions = [
        Subscription.tenant_id == tenant_id,
        Subscription.status == SubscriptionStatus.ACTIVE,
    ]
    if get_settings().is_production:
        conditions.append(Subscription.simulated.is_(False))
    row = (await db.execute(select(Subscription.id).where(*conditions))).first()
    return row is not None
