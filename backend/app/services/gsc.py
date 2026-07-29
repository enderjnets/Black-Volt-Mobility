"""Volt Blog Autopilot — Google Search Console integration.

Per-tenant OAuth (reusing the Web OAuth client) → daily snapshot of real Search Console
data (clicks / impressions / CTR / position + top queries) stored as SeoSnapshot(
kind="gsc_day"). This powers the "Impact" analytics on REAL Google data (unlike Soro's
sum-of-volumes vanity metric), and feeds top queries back into keyword discovery.

Connecting requires the owner to complete Google consent once (webmasters.readonly). Until
then the snapshot job skips cleanly and the rest of the engine (autocomplete + LLM
discovery) is unaffected.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import BlogConfig, SeoSnapshot
from app.services import blog as blog_service

logger = logging.getLogger("blackvolt.blog.gsc")

# Read-write, not readonly: submitting the sitemap needs it. Search Console reported
# "URL is unknown to Google" for every published article — Google had never been told the
# site exists — and telling it is the one part of that we can automate.
SCOPES = [
    "https://www.googleapis.com/auth/webmasters",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _denver_date(offset_days: int = 0) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=-6, days=offset_days)).strftime("%Y-%m-%d")


def authorize_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode

    settings = get_settings()
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange an auth code for a refresh token + the connected account email."""
    import httpx

    settings = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as http:
        tok = await http.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        tok.raise_for_status()
        data = tok.json()
        email = None
        access = data.get("access_token")
        if access:
            ui = await http.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
            if ui.status_code == 200:
                email = ui.json().get("email")
    return {"refresh_token": data.get("refresh_token"), "email": email}


async def connect(
    db: AsyncSession, *, tenant_id: int, refresh_token: str, email: str | None, site_url: str
) -> None:
    cfg = await blog_service.ensure_config(db, tenant_id=tenant_id)
    cfg.gsc_refresh_token = refresh_token
    cfg.gsc_connected_email = email
    cfg.gsc_site_url = site_url
    await db.commit()


def parse_gsc(rows: list[dict], totals: dict | None = None) -> dict:
    """Summarize a Search Console searchAnalytics response into dashboard numbers."""
    top = [
        {
            "query": r.get("keys", [None])[0],
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": round((r.get("ctr", 0) or 0) * 100, 2),
            "position": round(r.get("position", 0) or 0, 1),
        }
        for r in rows
        if r.get("keys")
    ]
    clicks = totals.get("clicks") if totals else sum(r.get("clicks", 0) for r in rows)
    impressions = (
        totals.get("impressions") if totals else sum(r.get("impressions", 0) for r in rows)
    )
    ctr = round((clicks / impressions) * 100, 2) if impressions else 0.0
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "top_queries": sorted(top, key=lambda q: q["clicks"], reverse=True)[:25],
    }


def _credentials(refresh_token: str):
    from google.oauth2.credentials import Credentials

    settings = get_settings()
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        token_uri=_TOKEN_URL,
        # Deliberately no `scopes=`. A refresh token carries the scopes it was granted;
        # asking for more at refresh time makes Google reject the whole refresh with
        # `invalid_scope`. Widening SCOPES therefore broke reading Search Console too —
        # caught in production — instead of only the write we were adding. Without this
        # argument an old read-only token keeps reading, and only the sitemap submit fails,
        # with a 403 the caller turns into "reconnect once".
    )


def _query_gsc(refresh_token: str, site_url: str) -> dict:
    """Blocking Google API call — run via asyncio.to_thread from run_daily."""
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _credentials(refresh_token)
    creds.refresh(Request())
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    body = {
        "startDate": _denver_date(-3),
        "endDate": _denver_date(-1),
        "dimensions": ["query"],
        "rowLimit": 100,
    }
    resp = svc.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return resp or {}


# Google's URL Inspection quota is 2000/day; we only ever have a handful of articles, and
# checking politely keeps plenty of headroom for the owner's own Search Console use.
_MAX_INSPECTED = 10


def _is_permission_error(exc: Exception) -> bool:
    """A token minted before we asked for write access can read but not submit.

    Google answers 403 insufficientPermissions. That is not a failure to report as an error
    — it means "reconnect once", which is a completely different instruction for the owner.
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (401, 403):
        return True
    text = str(exc)
    # `invalid_scope`/`invalid_grant` come from the refresh step, not the API call — a
    # different exception type entirely, which is how this was missed the first time.
    return any(s in text for s in ("insufficientPermissions", "invalid_scope", "invalid_grant"))


_WRITE_SCOPE = "https://www.googleapis.com/auth/webmasters"


def _sitemaps_list(refresh_token: str, site_url: str) -> tuple[list[dict], list[str] | None]:
    """The sitemaps Google has on file, plus the scopes this token was actually granted.

    The scopes come free: Google returns them on the refresh we already perform. Knowing
    them up front is the difference between a button that explains itself and one that only
    fails after you press it.
    """
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _credentials(refresh_token)
    creds.refresh(Request())
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    resp = svc.sitemaps().list(siteUrl=site_url).execute() or {}
    granted = getattr(creds, "granted_scopes", None)
    return resp.get("sitemap", []) or [], granted


def _sitemaps_submit(refresh_token: str, site_url: str, feedpath: str) -> None:
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _credentials(refresh_token)
    creds.refresh(Request())
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    svc.sitemaps().submit(siteUrl=site_url, feedpath=feedpath).execute()


def default_feedpath() -> str:
    return f"{get_settings().PUBLIC_SITE_URL.rstrip('/')}/sitemap.xml"


async def _config(db: AsyncSession, tenant_id: int) -> BlogConfig | None:
    cfg = (
        await db.execute(select(BlogConfig).where(BlogConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if cfg is None or not cfg.gsc_refresh_token or not cfg.gsc_site_url:
        return None
    return cfg


async def sitemap_status(db: AsyncSession, *, tenant_id: int) -> dict:
    """What Google says about our sitemap: registered at all, and last read when.

    `last_downloaded: null` on every entry is the smoking gun for "Google has never come
    round", which is exactly the state the URL inspection reported.
    """
    import asyncio

    cfg = await _config(db, tenant_id)
    if cfg is None:
        return {"skipped": "gsc_not_connected"}
    try:
        rows, granted = await asyncio.to_thread(
            _sitemaps_list, cfg.gsc_refresh_token, cfg.gsc_site_url
        )
    except Exception as e:
        if _is_permission_error(e):
            return {"skipped": "needs_reauth"}
        logger.warning("sitemap list failed tenant=%s: %s", tenant_id, e)
        return {"skipped": "list_failed"}
    return {
        "expected": default_feedpath(),
        # None, not False, when Google did not say: "we don't know" must not disable the
        # button. Only a definite "this token cannot write" should replace it with a prompt.
        "can_submit": (_WRITE_SCOPE in granted) if granted else None,
        "sitemaps": [
            {
                "path": r.get("path"),
                "last_submitted": r.get("lastSubmitted"),
                "last_downloaded": r.get("lastDownloaded"),
                "pending": bool(r.get("isPending")),
                "warnings": int(r.get("warnings") or 0),
                "errors": int(r.get("errors") or 0),
            }
            for r in rows
        ],
    }


async def submit_sitemap(
    db: AsyncSession, *, tenant_id: int, feedpath: str | None = None
) -> dict:
    """Tell Google the sitemap exists. The one part of getting crawled we can automate."""
    import asyncio

    cfg = await _config(db, tenant_id)
    if cfg is None:
        return {"skipped": "gsc_not_connected"}
    path = feedpath or default_feedpath()
    try:
        await asyncio.to_thread(
            _sitemaps_submit, cfg.gsc_refresh_token, cfg.gsc_site_url, path
        )
    except Exception as e:
        if _is_permission_error(e):
            return {"skipped": "needs_reauth"}
        logger.warning("sitemap submit failed tenant=%s: %s", tenant_id, e)
        return {"skipped": "submit_failed"}
    logger.info("sitemap submitted tenant=%s path=%s", tenant_id, path)
    return {"ok": True, "path": path}


def _inspect_urls(refresh_token: str, site_url: str, urls: list[str]) -> dict:
    """Blocking Google API call — run via asyncio.to_thread, like _query_gsc."""
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _credentials(refresh_token)
    creds.refresh(Request())
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    out: dict[str, dict] = {}
    for url in urls[:_MAX_INSPECTED]:
        try:
            resp = svc.urlInspection().index().inspect(
                body={"inspectionUrl": url, "siteUrl": site_url}
            ).execute()
        except Exception as e:  # one bad URL must not lose the rest
            out[url] = {"error": str(e)[:200]}
            continue
        idx = (resp or {}).get("inspectionResult", {}).get("indexStatusResult", {}) or {}
        out[url] = {
            "verdict": idx.get("verdict"),
            "coverage": idx.get("coverageState"),
            "last_crawl": idx.get("lastCrawlTime"),
            "robots": idx.get("robotsTxtState"),
        }
    return out


async def run_indexing(db: AsyncSession, *, tenant_id: int) -> dict:
    """Ask Google whether each published article is actually indexed.

    "Is it live on our site" and "can anyone find it" are different questions, and only the
    second one pays. Cached as a snapshot and refreshed daily — never on a dashboard load.
    """
    import asyncio

    from app.models import BlogPost

    cfg = await _config(db, tenant_id)
    if cfg is None:
        return {"skipped": "gsc_not_connected"}

    site = get_settings().PUBLIC_SITE_URL.rstrip("/")
    slugs = (
        await db.execute(
            select(BlogPost.slug)
            .where(BlogPost.tenant_id == tenant_id, BlogPost.status == "published")
            .order_by(BlogPost.published_at.desc().nullslast())
            .limit(_MAX_INSPECTED)
        )
    ).scalars().all()
    if not slugs:
        return {"skipped": "no_published_posts"}
    urls = [f"{site}/blog/{s}" for s in slugs]

    try:
        results = await asyncio.to_thread(
            _inspect_urls, cfg.gsc_refresh_token, cfg.gsc_site_url, urls
        )
    except Exception as e:
        logger.warning("URL inspection failed tenant=%s: %s", tenant_id, e)
        return {"skipped": "inspection_failed"}

    payload = {
        "checked": len(results),
        "indexed": sum(1 for r in results.values() if r.get("verdict") == "PASS"),
        "urls": [{"url": u, **r} for u, r in results.items()],
    }
    date = _denver_date(-1)
    existing = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tenant_id,
                SeoSnapshot.kind == "indexing",
                SeoSnapshot.date == date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = payload
    else:
        db.add(SeoSnapshot(tenant_id=tenant_id, kind="indexing", date=date, payload=payload))
    await db.commit()
    logger.info(
        "indexing snapshot tenant=%s checked=%s indexed=%s",
        tenant_id, payload["checked"], payload["indexed"],
    )
    return {"ok": True, **{k: payload[k] for k in ("checked", "indexed")}}


async def run_daily(db: AsyncSession, *, tenant_id: int) -> dict:
    import asyncio

    cfg = (
        await db.execute(select(BlogConfig).where(BlogConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if cfg is None or not cfg.gsc_refresh_token or not cfg.gsc_site_url:
        return {"skipped": "gsc_not_connected"}
    try:
        resp = await asyncio.to_thread(_query_gsc, cfg.gsc_refresh_token, cfg.gsc_site_url)
    except Exception as e:
        logger.warning("GSC query failed tenant=%s: %s", tenant_id, e)
        return {"skipped": "query_failed"}
    payload = parse_gsc(resp.get("rows", []))
    date = _denver_date(-1)
    existing = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tenant_id,
                SeoSnapshot.kind == "gsc_day",
                SeoSnapshot.date == date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = payload
    else:
        db.add(SeoSnapshot(tenant_id=tenant_id, kind="gsc_day", date=date, payload=payload))
    await db.commit()
    logger.info("GSC snapshot tenant=%s clicks=%s", tenant_id, payload.get("clicks"))
    return {
        "ok": True,
        "clicks": payload.get("clicks"),
        "queries": len(payload.get("top_queries", [])),
    }
