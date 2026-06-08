"""Tenant + client helpers. MVP seeds a single tenant (Black Volt)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, RateConfig, Ride, RideStatus, Tenant
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


async def get_tenant(db: AsyncSession, tenant_id: int) -> Tenant | None:
    return (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()


# Brand/profile fields the owner may edit from Settings. slug/created_at are
# immutable; uploads (logo/photo) go through dedicated endpoints, not here.
TENANT_EDITABLE_FIELDS = (
    "name",
    "tagline",
    "bio",
    "instagram",
    "website",
    "vehicle",
    "city",
    "brand_color",
    "rating",
    "since_year",
)


def media_url(path: str | None) -> str | None:
    """Public URL for a stored media path (served by the /media mount), or None."""
    if not path:
        return None
    return f"/media/{path.lstrip('/')}"


async def _completed_rides(db: AsyncSession, tenant_id: int) -> int:
    return int(
        (
            await db.execute(
                select(func.count(Ride.id)).where(
                    Ride.tenant_id == tenant_id, Ride.status == RideStatus.COMPLETED
                )
            )
        ).scalar_one()
    )


def _years_active(since_year: int | None) -> int | None:
    if not since_year:
        return None
    return max(0, datetime.now(UTC).year - int(since_year))


async def tenant_settings(db: AsyncSession, *, tenant_id: int) -> dict | None:
    """Full editable settings for the dashboard + read-only integration status."""
    t = await get_tenant(db, tenant_id)
    if t is None:
        return None
    s = get_settings()
    return {
        "slug": t.slug,
        "name": t.name,
        "tagline": t.tagline,
        "bio": t.bio,
        "instagram": t.instagram,
        "website": t.website,
        "vehicle": t.vehicle,
        "city": t.city,
        "brand_color": t.brand_color,
        "rating": t.rating,
        "since_year": t.since_year,
        "logo_url": media_url(t.logo_path),
        "photo_url": media_url(t.photo_path),
        # Read-only status of integrations (configured env-level for the MVP).
        "payments": {
            "connected": bool(s.SQUARE_ACCESS_TOKEN and s.SQUARE_LOCATION_ID),
            "live": s.payments_live,
            "env": s.SQUARE_ENV,
        },
        "notifications": {
            # Phase 7 wires real sending; the channels are not active yet.
            "available": False,
            "sms": False,
            "calls": False,
        },
    }


async def update_tenant(db: AsyncSession, *, tenant_id: int, changes: dict) -> Tenant | None:
    """Update the owner-editable brand/profile fields. Unknown keys ignored."""
    t = await get_tenant(db, tenant_id)
    if t is None:
        return None
    for k, v in changes.items():
        if k in TENANT_EDITABLE_FIELDS:
            setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return t


async def set_tenant_asset(
    db: AsyncSession, *, tenant_id: int, kind: str, path: str | None
) -> Tenant | None:
    """Point the tenant's logo or photo at a stored media path (or clear it)."""
    if kind not in ("logo", "photo"):
        raise ValueError("kind must be 'logo' or 'photo'")
    t = await get_tenant(db, tenant_id)
    if t is None:
        return None
    setattr(t, f"{kind}_path", path)
    await db.commit()
    await db.refresh(t)
    return t


async def public_profile(db: AsyncSession, *, slug: str) -> dict | None:
    """Public-safe profile for /d/{slug}: brand + computed stats. No secrets."""
    t = await get_tenant_by_slug(db, slug)
    if t is None:
        return None
    return {
        "slug": t.slug,
        "name": t.name,
        "tagline": t.tagline,
        "bio": t.bio,
        "instagram": t.instagram,
        "website": t.website,
        "vehicle": t.vehicle,
        "city": t.city,
        "brand_color": t.brand_color,
        "logo_url": media_url(t.logo_path),
        "photo_url": media_url(t.photo_path),
        "rating": t.rating,
        "rides_total": await _completed_rides(db, t.id),
        "years_active": _years_active(t.since_year),
    }


def _digits(phone: str | None) -> str:
    """Digits-only form of a phone for tolerant matching (+1 303-555 == 1303555)."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _lang2(lang: str | None) -> str | None:
    """Map a free language value to the stored 2-letter code, or None."""
    val = (lang or "").strip().lower()
    if val in ("es", "spanish", "español", "espanol"):
        return "ES"
    if val in ("en", "english", "inglés", "ingles"):
        return "EN"
    return None


async def find_or_create_client_by_contact(
    db: AsyncSession,
    *,
    tenant_id: int,
    name: str | None,
    phone: str | None,
    lang: str | None = None,
) -> Client | None:
    """Get-or-create a driver-entered passenger (manual/smart ride) as a real
    Client so they show up in the CRM and accrue rides. Matches an existing client
    by phone (digits-only) first, else by exact name (case-insensitive) when no
    phone is given. Fills missing fields without overwriting. Returns None when
    there's nothing to identify a person. Flushes so the caller sees `id`."""
    name = (name or "").strip() or None
    phone = (phone or "").strip() or None
    lang = _lang2(lang)
    if not name and not phone:
        return None

    row = None
    digits = _digits(phone)
    if digits:
        candidates = (
            await db.execute(
                select(Client).where(
                    Client.tenant_id == tenant_id, Client.phone.isnot(None)
                )
            )
        ).scalars().all()
        row = next((c for c in candidates if _digits(c.phone) == digits), None)
    if row is None and name and not phone:
        row = (
            await db.execute(
                select(Client).where(
                    Client.tenant_id == tenant_id,
                    func.lower(Client.name) == name.lower(),
                )
            )
        ).scalars().first()

    if row is None:
        row = Client(tenant_id=tenant_id, name=name, phone=phone, lang=lang)
        db.add(row)
    else:
        if name and not row.name:
            row.name = name
        if phone and not row.phone:
            row.phone = phone
        if lang and not row.lang:
            row.lang = lang
    await db.flush()
    return row


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
