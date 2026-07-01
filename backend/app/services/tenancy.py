"""Tenant + client helpers. Seeds the Black Volt tenant and provisions a fresh
tenant per driver on their first sign-in (multi-driver SaaS path)."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, RateConfig, Ride, RideStatus, Tenant
from app.models.rate_config import DEFAULT_RATES

DEFAULT_TENANT_SLUG = "ender-ocando"
# Deprecated slugs that must keep resolving after a rename (printed QR codes,
# already-shared links, referral cookies). Maps an old slug → the current slug.
SLUG_ALIASES = {"black-volt": DEFAULT_TENANT_SLUG}
# Slugs that identify the default/MVP tenant — the canonical one plus any alias —
# so a not-yet-migrated row (old slug) is found instead of seeding a duplicate.
_DEFAULT_LOOKUP_SLUGS = (DEFAULT_TENANT_SLUG, *SLUG_ALIASES.keys())
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
        await db.execute(
            select(Tenant)
            .where(Tenant.slug.in_(_DEFAULT_LOOKUP_SLUGS))
            # Prefer the canonical slug so coexisting old+new rows resolve
            # deterministically instead of raising MultipleResultsFound.
            .order_by(case((Tenant.slug == DEFAULT_TENANT_SLUG, 0), else_=1))
            .limit(1)
        )
    ).scalars().first()
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
        await db.execute(
            select(Tenant)
            .where(Tenant.slug.in_(_DEFAULT_LOOKUP_SLUGS))
            # Prefer the canonical slug so coexisting old+new rows resolve
            # deterministically instead of raising MultipleResultsFound.
            .order_by(case((Tenant.slug == DEFAULT_TENANT_SLUG, 0), else_=1))
            .limit(1)
        )
    ).scalars().first()
    if t is None:
        t = await ensure_seed(db)
    return t


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "driver"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Slugify `base` and de-duplicate against existing tenant slugs (-2, -3…).
    Reserved alias keys are treated as taken so a new tenant can't claim a slug
    that resolves elsewhere via SLUG_ALIASES."""
    base = _slugify(base)
    slug, n = base, 2
    while (
        slug in SLUG_ALIASES
        or (
            await db.execute(select(Tenant.id).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        is not None
    ):
        slug, n = f"{base}-{n}", n + 1
    return slug


async def create_tenant_for(
    db: AsyncSession, *, name: str, slug: str | None = None, commit: bool = True
) -> Tenant:
    """Provision a brand-new driver tenant (their own workspace) + default rates.
    The slug is derived from the name (or `slug`) and de-duplicated. Called when
    an allow-listed driver signs in for the first time. With commit=False the
    rows are only flushed — the caller owns the transaction (atomic flows like
    subscribe must not persist a tenant before the payment succeeds)."""
    nm = (name or "").strip() or "Driver"
    uslug = await _unique_slug(db, slug or nm)
    t = Tenant(slug=uslug, name=nm)
    db.add(t)
    await db.flush()  # populate t.id for the RateConfig FK
    db.add(RateConfig(tenant_id=t.id, **DEFAULT_RATES))
    if commit:
        await db.commit()
        await db.refresh(t)
    return t


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    # Resolve the literal slug first; only fall back to an alias target when no
    # real tenant owns that slug, so a future tenant can't be shadowed by an alias.
    t = (
        await db.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one_or_none()
    if t is None and slug in SLUG_ALIASES:
        t = (
            await db.execute(select(Tenant).where(Tenant.slug == SLUG_ALIASES[slug]))
        ).scalar_one_or_none()
    return t


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
    "phone",
    "brand_color",
    "rating",
    "since_year",
    "review_reminders_enabled",
    "review_reminder_hours",
    "social_daily_media",
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
        "phone": t.phone,
        "brand_color": t.brand_color,
        "rating": t.rating,
        "since_year": t.since_year,
        "review_reminders_enabled": t.review_reminders_enabled,
        "review_reminder_hours": t.review_reminder_hours,
        "social_daily_media": t.social_daily_media,
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


async def public_profile(
    db: AsyncSession, *, slug: str, include_contact: bool = False
) -> dict | None:
    """Public-safe profile for /d/{slug}: brand + computed stats. No secrets.

    The driver's direct phone is included only when ``include_contact`` is True
    (i.e. the viewer is a registered/signed-in client) — never for anonymous
    visitors, honoring the registration wall.
    """
    t = await get_tenant_by_slug(db, slug)
    if t is None:
        return None
    profile = {
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
    if include_contact:
        profile["phone"] = t.phone
    return profile


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


async def find_client_by_google_sub(db: AsyncSession, google_sub: str) -> Client | None:
    """Find a passenger by their Google identity ACROSS ALL tenants — the one
    deliberate cross-tenant lookup (identity resolution, like the global allow-list
    in resolve_user_access). It backs the *permanent, first-touch* designated-driver
    rule: a Google account belongs to whichever driver first registered it, so we
    return the OLDEST matching row and never spawn a duplicate under another tenant.
    Returns None when this account has never signed in anywhere."""
    if not google_sub:
        return None
    return (
        await db.execute(
            select(Client)
            .where(Client.google_sub == google_sub)
            .order_by(Client.created_at.asc(), Client.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_referral_tenant(db: AsyncSession, slug: str | None) -> Tenant:
    """Resolve the tenant a referral link (`?ref=`/`/d/{slug}`) points at, for
    attributing a brand-new passenger. The slug must name a real tenant that
    passes the entitlement gate (`tenant_has_entitlements`); anything else
    (missing, unknown, or — once `ENTITLEMENTS_ENFORCED` is on — an unpaid slug)
    falls back to the default Black Volt tenant so attribution can never be
    steered at a bogus workspace. With enforcement off (MVP default) any real
    tenant slug attributes — the gate tightens automatically when paid plans go
    live, with no code change here."""
    if slug:
        from app.services import subscriptions  # local: avoid tenancy↔subscriptions cycle

        t = await get_tenant_by_slug(db, slug)
        if t is not None and await subscriptions.tenant_has_entitlements(db, tenant_id=t.id):
            return t
    return await get_default_tenant(db)


async def find_or_create_client(
    db: AsyncSession,
    *,
    tenant_id: int,
    google_sub: str,
    email: str | None,
    name: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
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
        row = Client(
            tenant_id=tenant_id, google_sub=google_sub, email=email,
            name=name, first_name=first_name, last_name=last_name,
        )
        db.add(row)
    else:
        if email and not row.email:
            row.email = email
        if name and not row.name:
            row.name = name
        if first_name and not row.first_name:
            row.first_name = first_name
        if last_name and not row.last_name:
            row.last_name = last_name
    await db.commit()
    await db.refresh(row)
    return row
