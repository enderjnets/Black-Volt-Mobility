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

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
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
        scopes=SCOPES,
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
