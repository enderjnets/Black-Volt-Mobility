"""Volt Blog Autopilot — site speed (Google PageSpeed Insights).

Daily snapshot of the public site's Core Web Vitals via the free PSI API, stored as a
SeoSnapshot(kind="psi") for the dashboard Speed tab. Skips cleanly when no API key is
configured. Mirrors Soro's "site speed" module — but on real Lighthouse data.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SeoSnapshot

logger = logging.getLogger("blackvolt.blog.speed")

_PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_DENVER_OFFSET = dt.timedelta(hours=-6)  # display date in Denver (approx; DST-agnostic label)


def _denver_date() -> str:
    return (dt.datetime.now(dt.UTC) + _DENVER_OFFSET).strftime("%Y-%m-%d")


def parse_psi(data: dict) -> dict:
    """Extract the numbers the dashboard cares about from a PSI response."""
    lh = data.get("lighthouseResult", {})
    cats = lh.get("categories", {})
    audits = lh.get("audits", {})

    def score(cat: str):
        s = cats.get(cat, {}).get("score")
        return round(s * 100) if isinstance(s, int | float) else None

    def metric(key: str):
        a = audits.get(key, {})
        return a.get("displayValue") or a.get("numericValue")

    opportunities = [
        {"id": k, "title": a.get("title"), "savings_ms": a.get("numericValue")}
        for k, a in audits.items()
        if a.get("details", {}).get("type") == "opportunity"
        and (a.get("numericValue") or 0) > 100
    ]
    opportunities.sort(key=lambda o: o.get("savings_ms") or 0, reverse=True)
    return {
        "performance": score("performance"),
        "seo": score("seo"),
        "accessibility": score("accessibility"),
        "best_practices": score("best-practices"),
        "lcp": metric("largest-contentful-paint"),
        "cls": metric("cumulative-layout-shift"),
        "tbt": metric("total-blocking-time"),
        "fcp": metric("first-contentful-paint"),
        "top_opportunities": opportunities[:5],
        "strategy": "mobile",
    }


async def _fetch(url: str, key: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.get(
                _PSI_URL,
                params={
                    "url": url,
                    "key": key,
                    "strategy": "mobile",
                    "category": ["performance", "seo", "accessibility", "best-practices"],
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("PSI fetch failed url=%s: %s", url, e)
        return None


async def _upsert(db: AsyncSession, *, tenant_id: int, date: str, payload: dict) -> None:
    existing = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tenant_id,
                SeoSnapshot.kind == "psi",
                SeoSnapshot.date == date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = payload
    else:
        db.add(SeoSnapshot(tenant_id=tenant_id, kind="psi", date=date, payload=payload))


async def run_daily(db: AsyncSession, *, tenant_id: int) -> dict:
    """Run PSI against the public site + blog and persist a snapshot."""
    settings = get_settings()
    key = settings.GOOGLE_PSI_API_KEY
    if not key:
        return {"skipped": "no_psi_key"}
    site = settings.PUBLIC_SITE_URL.rstrip("/")
    data = await _fetch(f"{site}/blog", key)
    if data is None:
        return {"skipped": "fetch_failed"}
    payload = parse_psi(data)
    await _upsert(db, tenant_id=tenant_id, date=_denver_date(), payload=payload)
    await db.commit()
    logger.info("PSI snapshot tenant=%s perf=%s", tenant_id, payload.get("performance"))
    return {"ok": True, "performance": payload.get("performance")}
