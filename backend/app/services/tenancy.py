"""Tenant + client helpers. MVP seeds a single tenant (Black Volt)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, RateConfig, Tenant
from app.models.rate_config import DEFAULT_RATES

DEFAULT_TENANT_SLUG = "black-volt"
DEFAULT_TENANT = {
    "slug": DEFAULT_TENANT_SLUG,
    "name": "Black Volt Mobility",
    "tagline": "Silent Power. Premium Arrival.",
    "vehicle": "Kia EV9",
    "city": "Denver / Aurora, CO",
}


async def ensure_seed(db: AsyncSession) -> Tenant:
    """Idempotently ensure the Black Volt tenant exists. Returns it."""
    t = (
        await db.execute(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    ).scalar_one_or_none()
    if t is None:
        t = Tenant(**DEFAULT_TENANT)
        db.add(t)
        await db.commit()
        await db.refresh(t)
    rc = (
        await db.execute(select(RateConfig).where(RateConfig.tenant_id == t.id))
    ).scalar_one_or_none()
    if rc is None:
        db.add(RateConfig(tenant_id=t.id, **DEFAULT_RATES))
        await db.commit()
    return t


async def get_default_tenant(db: AsyncSession) -> Tenant:
    t = (
        await db.execute(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    ).scalar_one_or_none()
    if t is None:
        t = await ensure_seed(db)
    return t


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    return (
        await db.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one_or_none()


async def find_or_create_client(
    db: AsyncSession,
    *,
    tenant_id: int,
    google_sub: str,
    email: str | None,
    name: str | None,
) -> Client:
    """Find the passenger by google_sub (then email) within the tenant, else create."""
    row = (
        await db.execute(
            select(Client).where(
                Client.tenant_id == tenant_id, Client.google_sub == google_sub
            )
        )
    ).scalar_one_or_none()
    if row is None and email:
        row = (
            await db.execute(
                select(Client).where(Client.tenant_id == tenant_id, Client.email == email)
            )
        ).scalar_one_or_none()
        if row is not None and not row.google_sub:
            row.google_sub = google_sub
    if row is None:
        row = Client(tenant_id=tenant_id, google_sub=google_sub, email=email, name=name)
        db.add(row)
    else:
        if email and not row.email:
            row.email = email
        if name and not row.name:
            row.name = name
    await db.commit()
    await db.refresh(row)
    return row
