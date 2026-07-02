"""Featured events API.

Public (no auth): list published upcoming events and one event's landing detail.
Admin (require_admin, owner only): list scanner suggestions, approve/dismiss, run a
scan, list/edit events, and generate extra social posts. All admin operations are
scoped to the owner tenant (the public site is single-brand).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.config import get_settings
from app.db.base import get_db
from app.services import events, events_scan
from app.services.tenancy import media_url

router = APIRouter(prefix="/events", tags=["events"])


def _owner_tid() -> int:
    """Owner tenant that owns all events (matches the scanner's target tenant)."""
    return get_settings().OWNER_TENANT_ID or 1


# ─── Schemas ───────────────────────────────────────────────────────────────────


class PublicEventOut(BaseModel):
    slug: str
    title: str
    performer: str | None = None
    venue_name: str
    starts_at: dt.datetime
    hero_url: str | None = None


class SuggestionOut(BaseModel):
    id: int
    source: str
    title: str
    performer: str | None = None
    venue_name: str
    venue_key: str | None = None
    venue_address: str | None = None
    distance_mi: float | None = None
    starts_at: dt.datetime
    score: float | None = None
    image_url: str | None = None
    event_url: str | None = None
    status: str


class AdminEventOut(BaseModel):
    id: int
    slug: str
    title: str
    performer: str | None = None
    venue_key: str
    venue_name: str
    venue_address: str | None = None
    starts_at: dt.datetime
    hero_url: str | None = None
    about_text: str | None = None
    tips_text: str | None = None
    status: str
    event_url: str | None = None


class EventPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    about_text: str | None = Field(default=None, max_length=4000)
    tips_text: str | None = Field(default=None, max_length=4000)
    venue_address: str | None = Field(default=None, max_length=240)
    status: str | None = None


class GeneratePostIn(BaseModel):
    kind: str = "video"  # "video" | "image"


def _admin_event_out(d: dict) -> AdminEventOut:
    return AdminEventOut(
        id=d["id"], slug=d["slug"], title=d["title"], performer=d.get("performer"),
        venue_key=d["venue_key"], venue_name=d["venue_name"],
        venue_address=d.get("venue_address"), starts_at=d["starts_at"],
        hero_url=media_url(d.get("hero_path")), about_text=d.get("about_text"),
        tips_text=d.get("tips_text"), status=d["status"], event_url=d.get("event_url"),
    )


# ─── Public ────────────────────────────────────────────────────────────────────


@router.get("/public", response_model=list[PublicEventOut])
async def list_public(db: AsyncSession = Depends(get_db)) -> list[PublicEventOut]:
    rows = await events.list_public_events(db)
    return [
        PublicEventOut(
            slug=r["slug"], title=r["title"], performer=r.get("performer"),
            venue_name=r["venue_name"], starts_at=r["starts_at"],
            hero_url=media_url(r.get("hero_path")),
        )
        for r in rows
    ]


@router.get("/public/{slug}")
async def public_detail(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    data = await events.get_public_event(db, slug=slug)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    data = {**data, "hero_url": media_url(data.get("hero_path"))}
    data.pop("hero_path", None)
    return data


# ─── Admin ─────────────────────────────────────────────────────────────────────


@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    venue_key: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SuggestionOut]:
    rows = await events.list_suggestions(db, tenant_id=_owner_tid(), venue_key=venue_key)
    return [SuggestionOut(**r) for r in rows]


@router.post("/suggestions/{suggestion_id}/approve")
async def approve(
    suggestion_id: int,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await events.approve_suggestion(
        db, tenant_id=_owner_tid(), suggestion_id=suggestion_id
    )
    if out is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_not_suggested"
        )
    return {**out, "hero_url": media_url(out.get("hero_path"))}


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss(
    suggestion_id: int,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ok = await events.dismiss_suggestion(db, tenant_id=_owner_tid(), suggestion_id=suggestion_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return {"ok": True}


@router.post("/scan")
async def scan_now(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await events_scan.run_scan(db)


@router.get("/admin", response_model=list[AdminEventOut])
async def list_admin_events(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminEventOut]:
    rows = await events.list_events(db, tenant_id=_owner_tid())
    return [_admin_event_out(r) for r in rows]


@router.patch("/admin/{event_id}", response_model=AdminEventOut)
async def patch_event(
    event_id: int,
    body: EventPatch,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminEventOut:
    out = await events.update_event(
        db, tenant_id=_owner_tid(), event_id=event_id,
        patch=body.model_dump(exclude_unset=True),
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _admin_event_out(out)


@router.post("/admin/{event_id}/posts")
async def generate_post(
    event_id: int,
    body: GeneratePostIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await events.generate_event_post(
        db, tenant_id=_owner_tid(), event_id=event_id, kind=body.kind
    )
    if out.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return out
