"""Reviews API.

Public (no auth): list approved reviews for display, resolve an invite token, submit a
review (always created PENDING). Admin (require_admin): moderate (approve / hide / toggle
home / reply / delete), list candidates, and create review-request invites that the front
turns into email / SMS deep-link / copy actions.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_payload, require_admin, resolve_tenant_id
from app.db.base import get_db
from app.models import NotificationKind
from app.services import email, notifications, reviews
from app.services.reviews import ReviewError

router = APIRouter(prefix="/reviews", tags=["reviews"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ReviewPublicOut(BaseModel):
    author_name: str
    rating: int
    body: str
    verified: bool
    owner_reply: str | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ReviewSubmitIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=3, max_length=1500)
    author_name: str = Field(min_length=1, max_length=200)
    author_email: str | None = Field(default=None, max_length=254)
    token: str | None = None
    ride_id: int | None = None
    tenant_slug: str | None = Field(default=None, max_length=80)


class AdminReviewOut(BaseModel):
    id: int
    tenant_id: int
    tenant_name: str | None = None
    tenant_slug: str | None = None
    ride_id: int | None = None
    author_name: str
    author_email: str | None = None
    rating: int
    body: str
    status: str
    show_on_home: bool
    featured: bool
    verified: bool
    source: str
    owner_reply: str | None = None
    created_at: dt.datetime
    approved_at: dt.datetime | None = None

    model_config = {"from_attributes": True}


class ReviewPatch(BaseModel):
    status: str | None = None
    show_on_home: bool | None = None
    featured: bool | None = None
    owner_reply: str | None = Field(default=None, max_length=1000)


class InviteIn(BaseModel):
    ride_id: int | None = None
    client_id: int | None = None
    to_email: str | None = Field(default=None, max_length=254)
    to_phone: str | None = Field(default=None, max_length=40)
    author_name: str | None = Field(default=None, max_length=200)
    channels: list[str] = []  # include "email" to send via Resend now
    lang: str = "en"


# ─── Public ──────────────────────────────────────────────────────────────────


@router.get("/public", response_model=list[ReviewPublicOut])
async def list_public_reviews(
    surface: str = Query(default="home"),
    tenant_id: int | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewPublicOut]:
    tid = tenant_id or await resolve_tenant_id(db, None)
    rows = await reviews.list_public(db, tenant_id=tid, surface=surface, limit=limit)
    return [ReviewPublicOut.model_validate(r) for r in rows]


@router.get("/invite/{token}")
async def get_review_invite(token: str, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        inv = await reviews.get_invite(db, token=token)
    except ReviewError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.reason) from e
    return {"author_name": inv.author_name, "used": inv.used_at is not None}


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_review(
    body: ReviewSubmitIn, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    payload = current_payload(request)
    default_tid = await resolve_tenant_id(db, None)
    try:
        r = await reviews.submit_review(
            db,
            default_tenant_id=default_tid,
            rating=body.rating,
            body=body.body,
            author_name=body.author_name,
            author_email=body.author_email,
            token=body.token,
            ride_id=body.ride_id,
            tenant_slug=body.tenant_slug,
            payload=payload,
        )
    except ReviewError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if e.reason == "invalid_token"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=e.reason) from e
    try:
        await email.notify_owner_new_review(db, review=r)
    except Exception:  # noqa: BLE001 — notification must never break submit
        pass
    await notifications.emit(
        db,
        tenant_id=r.tenant_id,
        kind=NotificationKind.review_new,
        data={"review_id": r.id, "rating": int(r.rating), "author_name": r.author_name},
    )
    return {"ok": True, "status": r.status.value, "verified": r.verified}


# ─── Admin ───────────────────────────────────────────────────────────────────


@router.get("/admin", response_model=list[AdminReviewOut])
async def admin_list_reviews(
    status_filter: str | None = Query(default=None, alias="status"),
    tenant_id: int | None = Query(default=None),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminReviewOut]:
    # Platform-owner view: tenant_id None → reviews across all drivers.
    rows = await reviews.list_admin(db, tenant_id=tenant_id, status=status_filter)
    out: list[AdminReviewOut] = []
    for r, tname, tslug in rows:
        o = AdminReviewOut.model_validate(r)
        o.tenant_name = tname
        o.tenant_slug = tslug
        out.append(o)
    return out


@router.get("/admin/candidates")
async def admin_review_candidates(
    q: str | None = Query(default=None),
    tenant_id: int | None = Query(default=None),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await reviews.list_candidates(db, tenant_id=tenant_id, q=q)


@router.post("/admin/invites", status_code=status.HTTP_201_CREATED)
async def admin_create_invite(
    body: InviteIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tid = await resolve_tenant_id(db, payload)
    inv = await reviews.create_invite(
        db,
        tenant_id=tid,
        ride_id=body.ride_id,
        client_id=body.client_id,
        to_email=body.to_email,
        to_phone=body.to_phone,
        author_name=body.author_name,
    )
    link = reviews.invite_link(inv)
    message = reviews.invite_message(inv, body.lang)
    email_status: str | None = None
    if "email" in body.channels and inv.to_email:
        email_status = await email.send_review_request(
            to=inv.to_email, author_name=inv.author_name, link=link, lang=body.lang
        )
    return {
        "id": inv.id,
        "token": inv.token,
        "link": link,
        "message": message,
        "sms_href": reviews.sms_href(inv, body.lang),
        "email_status": email_status,
    }


@router.patch("/admin/{review_id}", response_model=AdminReviewOut)
async def admin_patch_review(
    review_id: int,
    body: ReviewPatch,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminReviewOut:
    try:
        r = await reviews.patch_review(
            db,
            review_id=review_id,
            status=body.status,
            show_on_home=body.show_on_home,
            featured=body.featured,
            owner_reply=body.owner_reply,
        )
    except ReviewError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if e.reason == "not_found"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=e.reason) from e
    return AdminReviewOut.model_validate(r)


@router.delete("/admin/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_review(
    review_id: int,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await reviews.delete_review(db, review_id=review_id)
    except ReviewError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.reason) from e
