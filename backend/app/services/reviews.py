"""Customer reviews: public submit/list + admin moderation + review-request invites.

Reviews are always created PENDING and only surface publicly once an admin approves
them (and toggles `show_on_home` for the home page). A review is VERIFIED when it comes
from an admin invite token or a signed-in passenger reviewing their own completed ride.
Everything is scoped by `tenant_id`; the public list never exposes PII or cross-tenant data.
"""
from __future__ import annotations

import datetime as dt
import secrets
import urllib.parse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, Review, ReviewInvite, ReviewStatus, Ride, RideStatus, Tenant


class ReviewError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _clean(s: str | None, limit: int) -> str:
    return (s or "").strip()[:limit]


def public_site_origin() -> str:
    """Apex public site (strip the app. dashboard host) for building review links."""
    base = (get_settings().PUBLIC_DASHBOARD_URL or "https://blackvoltmobility.com").strip()
    base = base.replace("://app.", "://")
    if base.endswith("/dashboard"):
        base = base[: -len("/dashboard")]
    return base.rstrip("/")


# ─── public submit / list ────────────────────────────────────────────────────


async def submit_review(
    db: AsyncSession,
    *,
    default_tenant_id: int,
    rating: int,
    body: str,
    author_name: str,
    author_email: str | None = None,
    token: str | None = None,
    ride_id: int | None = None,
    tenant_slug: str | None = None,
    payload: dict | None = None,
) -> Review:
    rating = int(rating)
    if rating < 1 or rating > 5:
        raise ReviewError("bad_rating")
    body = _clean(body, 1500)
    if len(body) < 3:
        raise ReviewError("body_too_short")
    author_name = _clean(author_name, 200) or "Anonymous"
    author_email = _clean(author_email, 254) or None

    tenant_id = default_tenant_id
    bound_ride_id: int | None = None
    client_id: int | None = None
    invite: ReviewInvite | None = None
    verified = False
    source = "public"

    if token:
        invite = (
            await db.execute(select(ReviewInvite).where(ReviewInvite.token == token))
        ).scalar_one_or_none()
        if invite is None:
            raise ReviewError("invalid_token")
        tenant_id = invite.tenant_id
        bound_ride_id = invite.ride_id
        client_id = invite.client_id
        verified = True
        source = "invite"
        if author_name == "Anonymous" and invite.author_name:
            author_name = invite.author_name
        invite.used_at = _now()
    elif ride_id and payload and payload.get("cid"):
        # signed-in passenger reviewing their own ride
        ride = (await db.execute(select(Ride).where(Ride.id == ride_id))).scalar_one_or_none()
        if ride is not None and ride.client_id == payload.get("cid"):
            tenant_id = ride.tenant_id
            bound_ride_id = ride.id
            client_id = ride.client_id
            verified = True
            source = "trips"

    if source == "public" and tenant_slug:
        slug = _clean(tenant_slug, 80).lower()
        if slug:
            t = (
                await db.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
            if t is not None:
                tenant_id = t.id  # review left on this driver's public profile
                source = "profile"

    review = Review(
        tenant_id=tenant_id,
        ride_id=bound_ride_id,
        client_id=client_id,
        invite_id=invite.id if invite else None,
        author_name=author_name,
        author_email=author_email,
        rating=rating,
        body=body,
        status=ReviewStatus.PENDING,
        verified=verified,
        source=source,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def list_public(
    db: AsyncSession, *, tenant_id: int, surface: str = "home", limit: int = 12
) -> list[Review]:
    stmt = select(Review).where(
        Review.tenant_id == tenant_id, Review.status == ReviewStatus.APPROVED
    )
    if surface == "home":
        stmt = stmt.where(Review.show_on_home.is_(True))
    stmt = stmt.order_by(
        Review.featured.desc(), Review.approved_at.desc(), Review.created_at.desc()
    ).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def get_invite(db: AsyncSession, *, token: str) -> ReviewInvite:
    inv = (
        await db.execute(select(ReviewInvite).where(ReviewInvite.token == token))
    ).scalar_one_or_none()
    if inv is None:
        raise ReviewError("not_found")
    return inv


# ─── admin moderation ────────────────────────────────────────────────────────


async def list_admin(
    db: AsyncSession, *, tenant_id: int | None = None, status: str | None = None
) -> list[tuple[Review, str, str]]:
    """Admin moderation list. tenant_id None → all tenants (platform-owner view).

    Returns (review, tenant_name, tenant_slug) so the panel can label which driver
    each review belongs to. Only the platform owner reaches the admin routes, so a
    cross-tenant view does not leak between drivers; revisit if per-tenant admins land.
    """
    stmt = select(Review, Tenant.name, Tenant.slug).join(Tenant, Review.tenant_id == Tenant.id)
    if tenant_id is not None:
        stmt = stmt.where(Review.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Review.status == ReviewStatus(status))
    stmt = stmt.order_by(Review.created_at.desc())
    rows = (await db.execute(stmt)).all()
    return [(row[0], row[1], row[2]) for row in rows]


async def patch_review(
    db: AsyncSession,
    *,
    review_id: int,
    tenant_id: int | None = None,
    status: str | None = None,
    show_on_home: bool | None = None,
    featured: bool | None = None,
    owner_reply: str | None = None,
) -> Review:
    stmt = select(Review).where(Review.id == review_id)
    if tenant_id is not None:
        stmt = stmt.where(Review.tenant_id == tenant_id)
    r = (await db.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise ReviewError("not_found")
    if status is not None:
        new = ReviewStatus(status)
        r.status = new
        if new == ReviewStatus.APPROVED and r.approved_at is None:
            r.approved_at = _now()
    if show_on_home is not None:
        r.show_on_home = bool(show_on_home)
    if featured is not None:
        r.featured = bool(featured)
    if owner_reply is not None:
        r.owner_reply = _clean(owner_reply, 1000) or None
    await db.commit()
    await db.refresh(r)
    return r


async def delete_review(db: AsyncSession, *, review_id: int, tenant_id: int | None = None) -> None:
    stmt = select(Review).where(Review.id == review_id)
    if tenant_id is not None:
        stmt = stmt.where(Review.tenant_id == tenant_id)
    r = (await db.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise ReviewError("not_found")
    await db.delete(r)
    await db.commit()


# ─── review-request invites ──────────────────────────────────────────────────


async def list_candidates(
    db: AsyncSession, *, tenant_id: int | None = None, q: str | None = None, limit: int = 25
) -> list[dict]:
    """Recent completed rides + the rider's contact, for the picker. tenant_id None → all."""
    stmt = select(Ride).where(Ride.status == RideStatus.COMPLETED)
    if tenant_id is not None:
        stmt = stmt.where(Ride.tenant_id == tenant_id)
    rides = list(
        (await db.execute(stmt.order_by(Ride.id.desc()).limit(limit))).scalars().all()
    )
    client_ids = [r.client_id for r in rides if r.client_id]
    clients: dict[int, Client] = {}
    if client_ids:
        crows = (
            await db.execute(select(Client).where(Client.id.in_(client_ids)))
        ).scalars().all()
        clients = {c.id: c for c in crows}
    tenant_ids = {r.tenant_id for r in rides}
    tenants: dict[int, Tenant] = {}
    if tenant_ids:
        trows = (
            await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))
        ).scalars().all()
        tenants = {t.id: t for t in trows}

    out: list[dict] = []
    for r in rides:
        c = clients.get(r.client_id) if r.client_id else None
        name = (c.name if c and c.name else None) or r.passenger_name or "Passenger"
        email = c.email if c else None
        phone = (c.phone if c and c.phone else None) or r.passenger_phone
        tnt = tenants.get(r.tenant_id)
        out.append(
            {
                "ride_id": r.id,
                "client_id": r.client_id,
                "name": name,
                "email": email,
                "phone": phone,
                "route": f"{r.pickup_text} → {r.dropoff_text}",
                "when": r.scheduled_at,
                "tenant_id": r.tenant_id,
                "tenant_name": tnt.name if tnt else None,
            }
        )
    if q:
        ql = q.lower()
        out = [
            o
            for o in out
            if ql in (o["name"] or "").lower()
            or ql in (o["email"] or "").lower()
            or ql in (o["route"] or "").lower()
        ]
    return out


async def create_invite(
    db: AsyncSession,
    *,
    tenant_id: int,
    ride_id: int | None = None,
    client_id: int | None = None,
    to_email: str | None = None,
    to_phone: str | None = None,
    author_name: str | None = None,
) -> ReviewInvite:
    if ride_id:
        ride = (await db.execute(select(Ride).where(Ride.id == ride_id))).scalar_one_or_none()
        if ride is not None:
            tenant_id = ride.tenant_id  # invite belongs to the driver who served the ride
            if client_id is None:
                client_id = ride.client_id
    inv = ReviewInvite(
        tenant_id=tenant_id,
        ride_id=ride_id,
        client_id=client_id,
        token=secrets.token_urlsafe(24),
        author_name=_clean(author_name, 200) or None,
        to_email=_clean(to_email, 254) or None,
        to_phone=_clean(to_phone, 40) or None,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return inv


def invite_link(inv: ReviewInvite) -> str:
    return f"{public_site_origin()}/review/{inv.token}"


def invite_message(inv: ReviewInvite, lang: str = "en") -> str:
    link = invite_link(inv)
    who = (inv.author_name or "").strip()
    if lang == "es":
        hi = f"Hola {who}," if who else "Hola,"
        return (
            f"{hi} gracias por viajar con Black Volt Mobility. "
            f"¿Nos dejas una reseña rápida? {link}"
        )
    hi = f"Hi {who}," if who else "Hi,"
    return (
        f"{hi} thanks for riding with Black Volt Mobility. "
        f"Would you leave a quick review? {link}"
    )


def sms_href(inv: ReviewInvite, lang: str = "en") -> str:
    """Cross-platform `sms:` deep link (opens the admin's Messages app, prefilled)."""
    body = urllib.parse.quote(invite_message(inv, lang))
    phone = (inv.to_phone or "").strip()
    return f"sms:{phone}?&body={body}" if phone else f"sms:?&body={body}"


# ─── automatic post-ride reminder (scheduler) ────────────────────────────────


async def send_due_reminders(db: AsyncSession) -> int:
    """Email a review request to riders whose ride completed ~N hours ago.

    Per-tenant enable + hours; a global kill-switch lives in settings. Dedup via any
    existing ReviewInvite/Review for the ride (so manual requests, repeats, and already-
    reviewed rides are skipped). Uses `updated_at` as the completion proxy (rides have no
    completed_at) within a bounded lookback window, so enabling never blasts old rides.
    Email only — the SMS path is a manual deep link from the owner's phone. Returns count.
    """
    s = get_settings()
    if not s.REVIEW_REMINDERS_ENABLED:
        return 0
    from app.services import email  # lazy import to avoid a cycle

    now = _now()
    sent = 0
    tenants = (
        await db.execute(select(Tenant).where(Tenant.review_reminders_enabled.is_(True)))
    ).scalars().all()
    for tnt in tenants:
        hours = tnt.review_reminder_hours or s.REVIEW_REMINDER_HOURS_DEFAULT
        due_before = now - dt.timedelta(hours=hours)
        window_start = due_before - dt.timedelta(hours=s.REVIEW_REMINDER_LOOKBACK_HOURS)
        rides = (
            await db.execute(
                select(Ride)
                .where(
                    Ride.tenant_id == tnt.id,
                    Ride.status == RideStatus.COMPLETED,
                    Ride.client_id.is_not(None),
                    Ride.updated_at <= due_before,
                    Ride.updated_at >= window_start,
                )
                .order_by(Ride.id.desc())
                .limit(50)
            )
        ).scalars().all()
        for ride in rides:
            invited = (
                await db.execute(
                    select(ReviewInvite.id).where(ReviewInvite.ride_id == ride.id).limit(1)
                )
            ).first()
            if invited:
                continue
            reviewed = (
                await db.execute(select(Review.id).where(Review.ride_id == ride.id).limit(1))
            ).first()
            if reviewed:
                continue
            client = await db.get(Client, ride.client_id)
            if client is None or not client.email:
                continue
            name = (client.name or client.first_name or "").strip() or None
            inv = await create_invite(
                db,
                tenant_id=tnt.id,
                ride_id=ride.id,
                client_id=ride.client_id,
                to_email=client.email,
                author_name=name,
            )
            lang = "es" if str(getattr(ride, "lang", "") or "").lower().startswith("es") else "en"
            try:
                await email.send_review_request(
                    to=client.email, author_name=name, link=invite_link(inv), lang=lang
                )
            except Exception:  # noqa: BLE001 — one bad send must not stop the batch
                pass
            sent += 1
    return sent
