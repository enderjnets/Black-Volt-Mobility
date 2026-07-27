"""Volt Blog Autopilot API.

Public (no auth): list/detail of published articles (SSR), plus an embeddable JS/JSON
feed keyed by the tenant's embed token (for external sites / SaaS). Admin (require_admin,
owner tenant): Brand DNA config, keywords, posts (generate/edit/publish), and SEO analytics.
"""
from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.config import get_settings
from app.db.base import get_db, get_session_factory
from app.models import BlogConfig
from app.services import blog as blog_service
from app.services import blog_keywords, blog_writer, gsc
from app.services.tenancy import owner_tenant_id

router = APIRouter(prefix="/blog", tags=["blog"])
logger = logging.getLogger("blackvolt.blog.api")

# Writing a bilingual article is two long model calls — comfortably past the 100s ceiling
# every reverse proxy in front of this app enforces, so the request that starts it used to
# come back as a 500 while the article was quietly written anyway. The owner saw a failure
# every single time he pressed the button. Now the request only starts the job.
_writing: set[int] = set()
_write_tasks: set[asyncio.Task] = set()


async def _generate_in_background(tenant_id: int, keyword_id: int | None, keyword: str | None):
    Session = get_session_factory()
    try:
        async with Session() as db:
            await blog_writer.generate_article(
                db, tenant_id=tenant_id, keyword_id=keyword_id, keyword_text=keyword
            )
    except Exception:
        logger.exception("blog background generation failed tenant=%s", tenant_id)
    finally:
        _writing.discard(tenant_id)


# ─── Schemas ───────────────────────────────────────────────────────────────────


class KeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    lang: str = "en"


class KeywordStatusIn(BaseModel):
    status: str


class GenerateIn(BaseModel):
    keyword_id: int | None = None
    keyword: str | None = Field(default=None, max_length=200)


class PostPatch(BaseModel):
    title_en: str | None = Field(default=None, max_length=200)
    title_es: str | None = Field(default=None, max_length=200)
    excerpt_en: str | None = Field(default=None, max_length=400)
    excerpt_es: str | None = Field(default=None, max_length=400)
    body_md_en: str | None = None
    body_md_es: str | None = None
    hero_alt: str | None = Field(default=None, max_length=300)


class PostStatusIn(BaseModel):
    status: str


class ConfigPatch(BaseModel):
    voice: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, max_length=2000)
    key_themes: list[str] | None = None
    avoid_topics: list[str] | None = None
    image_style: str | None = Field(default=None, max_length=2000)
    cadence_per_week: int | None = Field(default=None, ge=0, le=14)
    autopublish: bool | None = None
    paused: bool | None = None
    languages: list[str] | None = None


# ─── Public ────────────────────────────────────────────────────────────────────


@router.get("/public")
async def list_public(
    lang: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    tid = await owner_tenant_id(db)
    return await blog_service.list_public_posts(db, tenant_id=tid, lang=lang)


@router.get("/public/{slug}")
async def public_detail(
    slug: str,
    lang: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tid = await owner_tenant_id(db)
    data = await blog_service.get_public_post(db, tenant_id=tid, slug=slug, lang=lang)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return data


async def _tenant_for_token(db: AsyncSession, token: str) -> int | None:
    cfg = (
        await db.execute(select(BlogConfig).where(BlogConfig.embed_token == token))
    ).scalar_one_or_none()
    return cfg.tenant_id if cfg else None


@router.get("/embed/{token}/posts.json")
async def embed_posts(
    token: str,
    lang: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """JSON feed for external embeds (keyed by the tenant's embed token)."""
    tid = await _tenant_for_token(db, token)
    if tid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    posts = await blog_service.list_public_posts(db, tenant_id=tid, lang=lang, limit=50)
    return {"posts": posts}


# ─── Admin ─────────────────────────────────────────────────────────────────────


@router.get("/admin/config")
async def get_config(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await blog_service.get_config(db, tenant_id=await owner_tenant_id(db))


@router.put("/admin/config")
async def put_config(
    body: ConfigPatch,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await blog_service.update_config(
        db, tenant_id=await owner_tenant_id(db),
        patch=body.model_dump(exclude_unset=True),
    )


@router.post("/admin/config/autofill")
async def autofill_config(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auto-generate the Brand DNA with the LLM (grounded in the business)."""
    return await blog_service.autofill_config(db, tenant_id=await owner_tenant_id(db))


@router.get("/admin/keywords")
async def list_keywords(
    kw_status: str | None = Query(default=None, alias="status"),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await blog_service.list_keywords(
        db, tenant_id=await owner_tenant_id(db), status=kw_status
    )


@router.post("/admin/keywords")
async def add_keyword(
    body: KeywordIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await blog_service.add_keyword(
        db, tenant_id=await owner_tenant_id(db), keyword=body.keyword, lang=body.lang
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid")
    return out


@router.post("/admin/keywords/{keyword_id}/status")
async def set_keyword_status(
    keyword_id: int,
    body: KeywordStatusIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await blog_service.set_keyword_status(
        db, tenant_id=await owner_tenant_id(db), keyword_id=keyword_id, status=body.status
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return out


@router.post("/admin/discover")
async def discover(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await blog_keywords.run_daily(db, tenant_id=await owner_tenant_id(db))


@router.get("/admin/posts")
async def list_posts(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await blog_service.list_posts(db, tenant_id=await owner_tenant_id(db))


@router.post("/admin/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate(
    body: GenerateIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start writing an article. Returns at once; the finished post appears in /admin/posts."""
    tenant_id = await owner_tenant_id(db)
    if body.keyword_id is None and not (body.keyword or "").strip():
        # "Write the next one" with an empty queue: say so now rather than after two minutes.
        if await blog_service.next_planned_keyword(db, tenant_id=tenant_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="need_keyword")
    if tenant_id in _writing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_writing")
    _writing.add(tenant_id)
    task = asyncio.create_task(_generate_in_background(tenant_id, body.keyword_id, body.keyword))
    # Hold a reference: a bare create_task can be garbage-collected mid-flight.
    _write_tasks.add(task)
    task.add_done_callback(_write_tasks.discard)
    return {"status": "generating"}


@router.patch("/admin/posts/{post_id}")
async def patch_post(
    post_id: int,
    body: PostPatch,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await blog_service.update_post(
        db, tenant_id=await owner_tenant_id(db), post_id=post_id,
        patch=body.model_dump(exclude_unset=True),
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return out


@router.post("/admin/posts/{post_id}/publish")
async def publish_post(
    post_id: int,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await blog_service.publish_now(
        db, tenant_id=await owner_tenant_id(db), post_id=post_id
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_bad_state")
    return out


@router.post("/admin/posts/{post_id}/status")
async def set_post_status(
    post_id: int,
    body: PostStatusIn,
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    out = await blog_service.set_post_status(
        db, tenant_id=await owner_tenant_id(db), post_id=post_id, status=body.status
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found_or_invalid")
    return out


def _gsc_redirect_uri() -> str:
    return f"{get_settings().PUBLIC_BASE_URL.rstrip('/')}/api/v1/blog/admin/gsc/callback"


@router.get("/admin/gsc/authorize")
async def gsc_authorize(
    site_url: str = Query(min_length=1, max_length=240),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the Google consent URL to connect Search Console for `site_url`
    (e.g. sc-domain:blackvoltmobility.com or https://blackvoltmobility.com/)."""
    state = base64.urlsafe_b64encode(site_url.encode()).decode()
    return {"url": gsc.authorize_url(_gsc_redirect_uri(), state)}


@router.get("/admin/gsc/callback")
async def gsc_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # The authenticated dashboard lives on the app host (PUBLIC_BASE_URL), not the apex.
    site = get_settings().PUBLIC_BASE_URL.rstrip("/")
    dest = f"{site}/dashboard/blog"
    if not code or not state:
        return RedirectResponse(url=f"{dest}?gsc=error")
    try:
        site_url = base64.urlsafe_b64decode(state.encode()).decode()
        tok = await gsc.exchange_code(code, _gsc_redirect_uri())
        if not tok.get("refresh_token"):
            return RedirectResponse(url=f"{dest}?gsc=noretoken")
        await gsc.connect(
            db, tenant_id=await owner_tenant_id(db),
            refresh_token=tok["refresh_token"], email=tok.get("email"), site_url=site_url,
        )
    except Exception:
        return RedirectResponse(url=f"{dest}?gsc=error")
    return RedirectResponse(url=f"{dest}?gsc=connected")


@router.get("/admin/analytics")
async def analytics(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SEO analytics (GSC impact + PSI). Populated in F4; returns empty scaffolding now."""
    from app.models import SeoSnapshot

    tid = await owner_tenant_id(db)
    rows = (
        await db.execute(
            select(SeoSnapshot)
            .where(SeoSnapshot.tenant_id == tid)
            .order_by(SeoSnapshot.date.desc())
            .limit(60)
        )
    ).scalars().all()
    gsc = [r.payload for r in rows if r.kind == "gsc_day"]
    psi = next((r.payload for r in rows if r.kind == "psi"), None)
    return {"gsc": gsc, "psi": psi}


@router.post("/admin/speed/run")
async def run_speed(
    payload: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run a PageSpeed Insights audit now and persist the snapshot (Speed tab button)."""
    from app.services import site_speed

    return await site_speed.run_daily(db, tenant_id=await owner_tenant_id(db))
