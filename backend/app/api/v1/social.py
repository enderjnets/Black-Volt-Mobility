"""Social-media module API (Phase "Social"). Admin-only, tenant-scoped.

The whole module is gated to super-admins (`require_admin`) — only the owner /
admins manage Black Volt's social presence; regular drivers never see it. The one
exception is the render callback, which carries no session and is HMAC-verified.

Owner-approval workflow:
  POST /social/posts/generate     → AI brief → persisted draft
  GET  /social/posts              → content calendar / approval queue
  POST /social/posts              → create a draft by hand
  PATCH/DELETE /social/posts/{id} → edit / remove
  POST /social/posts/{id}/render  → request the (simulated) video render
  POST /social/posts/{id}/approve → owner gate → approved | scheduled
  POST /social/posts/{id}/reject  → back to draft
  POST /social/posts/{id}/publish → publish now (simulated in Stage 1)
  GET  /social/inbox              → comments / DMs needing a reply
  POST /social/inbox/{id}/draft   → (re)generate the AI reply draft
  POST /social/inbox/{id}/reply   → approve + send (optional owner edit)
  POST /social/inbox/{id}/dismiss → ignore
  GET  /social/accounts           → connected platforms
  GET  /social/analytics          → engagement KPIs
  POST /social/webhooks/render    → signed BitTrader render callback (Stage 2)
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, resolve_tenant_id
from app.config import get_settings
from app.db.base import get_db
from app.services import social, social_buffer

router = APIRouter(tags=["social"])


class GenerateBody(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    angle: str | None = Field(default=None, max_length=200)
    lang: str = Field(default="en", max_length=5)
    targets: list[str] | None = Field(default=None, max_length=3)
    # Rel paths of previously-uploaded reference images (POST /social/uploads).
    # Validated server-side to this tenant's own social/refs dir.
    reference_paths: list[str] | None = Field(default=None, max_length=4)


class CreatePostBody(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    script: str | None = Field(default=None, max_length=5000)
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: str | None = Field(default=None, max_length=500)
    lang: str = Field(default="en", max_length=5)
    targets: list[str] | None = Field(default=None, max_length=3)


class UpdatePostBody(BaseModel):
    script: str | None = Field(default=None, max_length=5000)
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: str | None = Field(default=None, max_length=500)
    targets: list[str] | None = Field(default=None, max_length=3)
    scheduled_at: datetime | None = None


class ApproveBody(BaseModel):
    scheduled_at: datetime | None = None


class ReplyBody(BaseModel):
    text: str | None = Field(default=None, max_length=2200)


# ── posts ─────────────────────────────────────────────────────────────────────
@router.post("/social/posts/generate", status_code=status.HTTP_201_CREATED)
async def generate_post(
    body: GenerateBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.generate_and_create(
        db, tenant_id=tenant_id, topic=body.topic, angle=body.angle,
        lang=body.lang, targets=body.targets, reference_paths=body.reference_paths,
    )


# ── reference-image uploads + generate-from-image ─────────────────────────────
async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, enforcing the shared media size cap. Raises 400/413."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_file")
    if len(raw) > get_settings().MEDIA_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large"
        )
    return raw


@router.post("/social/uploads", status_code=status.HTTP_201_CREATED)
async def upload_reference_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    raw = await _read_upload(file)
    saved = social.save_reference_image(tenant_id, raw=raw)
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_image_type"
        )
    rel_path, _ctype = saved
    return {"path": rel_path, "public_url": social._public_media_url(rel_path)}


@router.post("/social/posts/generate-from-image", status_code=status.HTTP_201_CREATED)
async def generate_from_image(
    file: UploadFile = File(...),
    lang: str = Form("en"),
    topic: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    raw = await _read_upload(file)
    out = await social.generate_from_image(
        db, tenant_id=tenant_id, raw=raw,
        lang=(lang or "en")[:5], topic=(topic or None),
    )
    if out is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_image_type"
        )
    return out


@router.get("/social/posts")
async def list_posts(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.list_posts(db, tenant_id=tenant_id, status=status_filter, limit=limit)


@router.post("/social/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    body: CreatePostBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.create_post(
        db, tenant_id=tenant_id,
        content=body.model_dump(include={"topic", "script", "caption", "hashtags"}),
        lang=body.lang, targets=body.targets,
    )


@router.patch("/social/posts/{post_id}")
async def update_post(
    post_id: int,
    body: UpdatePostBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    out = await social.update_post(
        db, tenant_id=tenant_id, post_id=post_id, fields=body.model_dump(exclude_unset=True)
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post_not_found")
    return out


@router.delete("/social/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    if not await social.delete_post(db, tenant_id=tenant_id, post_id=post_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post_not_found")
    return None


def _require(out: dict | None) -> dict:
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post_not_found")
    if isinstance(out, dict) and out.get("error"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=out["error"])
    return out


@router.post("/social/posts/{post_id}/render")
async def render_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return _require(await social.request_render(db, tenant_id=tenant_id, post_id=post_id))


@router.post("/social/posts/{post_id}/approve")
async def approve_post(
    post_id: int,
    body: ApproveBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return _require(
        await social.approve_post(
            db, tenant_id=tenant_id, post_id=post_id, scheduled_at=body.scheduled_at
        )
    )


@router.post("/social/posts/{post_id}/reject")
async def reject_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return _require(await social.reject_post(db, tenant_id=tenant_id, post_id=post_id))


@router.post("/social/posts/{post_id}/publish")
async def publish_post(
    post_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return _require(await social.publish_post(db, tenant_id=tenant_id, post_id=post_id))


# ── inbox ─────────────────────────────────────────────────────────────────────
@router.get("/social/inbox")
async def list_inbox(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.list_inbox(db, tenant_id=tenant_id, status=status_filter)


@router.post("/social/inbox/{interaction_id}/draft")
async def draft_reply(
    interaction_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    out = await social.draft_reply(db, tenant_id=tenant_id, interaction_id=interaction_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction_not_found")
    return out


@router.post("/social/inbox/{interaction_id}/reply")
async def send_reply(
    interaction_id: int,
    body: ReplyBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    out = await social.send_reply(
        db, tenant_id=tenant_id, interaction_id=interaction_id, text=body.text
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction_not_found")
    return out


@router.post("/social/inbox/{interaction_id}/dismiss")
async def dismiss_interaction(
    interaction_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    out = await social.dismiss_interaction(
        db, tenant_id=tenant_id, interaction_id=interaction_id
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="interaction_not_found")
    return out


# ── accounts + analytics ──────────────────────────────────────────────────────
@router.get("/social/accounts")
async def list_accounts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.list_accounts(db, tenant_id=tenant_id)


@router.post("/social/accounts/sync")
async def sync_accounts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    if not social_buffer.is_live():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="buffer_not_configured"
        )
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        return await social.sync_buffer_channels(db, tenant_id=tenant_id)
    except social_buffer.BufferError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="buffer_unavailable"
        ) from None


@router.get("/social/analytics")
async def get_analytics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_admin),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await social.analytics(db, tenant_id=tenant_id)


# ── render callback (signed; no auth cookie — verified by HMAC) ───────────────
@router.post("/social/webhooks/render")
async def render_callback(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("x-bv-render-signature", "")
    if not social.verify_render_callback(body=body, signature=signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_signature")
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_json"
        ) from None
    result = await social.apply_render_callback(db, payload=payload)
    return {"ok": True, "result": result}


# ── render progress (signed; no auth cookie — verified by HMAC) ───────────────
@router.post("/social/webhooks/render/progress")
async def render_progress(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("x-bv-render-signature", "")
    if not social.verify_render_callback(body=body, signature=signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_signature")
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_json"
        ) from None
    result = await social.apply_render_progress(db, payload=payload)
    return {"ok": True, "result": result}
