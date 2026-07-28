"""Volt Blog Autopilot — site speed, measured by us.

This used to call Google PageSpeed Insights. Keyless PSI is not "rate limited at low volume"
as the old code assumed: every keyless caller in the world shares one anonymous Google
project whose daily quota is permanently exhausted, so every single request came back 429
and the Speed tab never held one data point. Verified against the API directly:

    {"code":429,"message":"Quota exceeded for quota metric 'Queries' ...
     for consumer 'project_number:583797351490'"}

Rather than depend on a key the owner would have to mint and keep alive, we measure what a
server can honestly measure: how fast the page answers, how heavy it is, and what stands
between it and first paint. These are NOT Lighthouse scores — the payload says
`method: "self"` so nobody mistakes them for one — but they are real numbers that move when
the site gets better, which is more than the Speed tab has ever had.

Stored as SeoSnapshot(kind="speed") for the dashboard.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from time import perf_counter
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import BlogPost, SeoSnapshot

logger = logging.getLogger("blackvolt.blog.speed")

_DENVER_OFFSET = dt.timedelta(hours=-6)  # display date in Denver (approx; DST-agnostic label)

# Thresholds. Deliberately generous — this flags "something is wrong", it does not chase a
# score. Anything tighter would cry wolf on a cold container start.
TTFB_WARN_MS = 800
TOTAL_WARN_MS = 3000
HTML_WARN_KB = 200
IMAGES_WARN_KB = 900
BLOCKING_WARN = 3
# Enough to catch a page carrying a huge hero; not so many that one audit hammers the site.
MAX_IMAGES_CHECKED = 12
_PAGE_TIMEOUT = 25.0
_ASSET_TIMEOUT = 10.0

_HEAD_RE = re.compile(r"<head[^>]*>(.*?)</head>", re.I | re.S)
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>", re.I)
_LINK_RE = re.compile(r"<link\b([^>]*)>", re.I)
_IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_LOOKS_HTML = re.compile(r"<html|<head|<body", re.I)


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf"\b{name}\s*=\s*[\"']([^\"']*)[\"']", attrs, re.I)
    return m.group(1) if m else None


def _denver_date() -> str:
    return (dt.datetime.now(dt.UTC) + _DENVER_OFFSET).strftime("%Y-%m-%d")


def count_blocking(html: str) -> dict:
    """Scripts and stylesheets in <head> that hold up first paint.

    A `<script src>` without defer/async blocks parsing; a stylesheet blocks rendering.
    JSON-LD is data, not code, and never blocks — counting it would punish us for the
    structured data we deliberately emit on every article.
    """
    head = _HEAD_RE.search(html or "")
    if not head:
        return {"scripts": 0, "styles": 0}
    inner = head.group(1)
    scripts = 0
    for m in _SCRIPT_RE.finditer(inner):
        attrs = m.group(1)
        if not _attr(attrs, "src"):
            continue  # inline script: no round-trip to wait on
        kind = _attr(attrs, "type") or ""
        if "json" in kind.lower():
            continue
        if re.search(r"\b(defer|async)\b", attrs, re.I):
            continue
        scripts += 1
    styles = sum(
        1
        for m in _LINK_RE.finditer(inner)
        if "stylesheet" in (_attr(m.group(1), "rel") or "").lower()
    )
    return {"scripts": scripts, "styles": styles}


def image_urls(html: str, base: str) -> list[str]:
    """Absolute URLs of the images the page asks for, de-duplicated, data: URIs dropped."""
    out: list[str] = []
    seen: set[str] = set()
    for src in _IMG_SRC_RE.findall(html or ""):
        src = src.strip()
        if not src or src.startswith("data:"):
            continue
        url = urljoin(base, src)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def verdict(metrics: dict) -> dict:
    """Per-metric ok/warn. Separate from measurement so it is testable on its own."""
    out: dict[str, str] = {}

    def mark(key: str, bad: bool) -> None:
        out[key] = "warn" if bad else "ok"

    mark("status", metrics.get("status") != 200)
    mark("ttfb_ms", (metrics.get("ttfb_ms") or 0) > TTFB_WARN_MS)
    mark("total_ms", (metrics.get("total_ms") or 0) > TOTAL_WARN_MS)
    mark("html_kb", (metrics.get("html_kb") or 0) > HTML_WARN_KB)
    mark("compressed", not metrics.get("compressed"))
    blocking = (metrics.get("blocking_scripts") or 0) + (metrics.get("blocking_styles") or 0)
    mark("blocking", blocking > BLOCKING_WARN)
    if metrics.get("images_kb") is not None:
        mark("images_kb", metrics["images_kb"] > IMAGES_WARN_KB)
    return out


async def _image_weight(http: httpx.AsyncClient, urls: list[str]) -> tuple[int, int]:
    """Total KB of the first few images, and how many we could actually weigh.

    HEAD only: we never download the bytes, so auditing a page costs the site almost nothing.
    """
    total = 0
    counted = 0
    for url in urls[:MAX_IMAGES_CHECKED]:
        try:
            r = await http.head(url, timeout=_ASSET_TIMEOUT, follow_redirects=True)
            length = int(r.headers.get("content-length") or 0)
        except Exception:
            continue
        if length > 0:
            total += length
            counted += 1
    return round(total / 1024), counted


async def measure_page(http: httpx.AsyncClient, url: str) -> dict:
    """Time, weigh and inspect one page. Never raises — a failure is a recorded result."""
    out: dict = {"url": url, "path": urlparse(url).path or "/"}
    try:
        start = perf_counter()
        async with http.stream("GET", url, timeout=_PAGE_TIMEOUT, follow_redirects=True) as r:
            # Headers are in: this is real time-to-first-byte, which a plain GET hides.
            out["ttfb_ms"] = round((perf_counter() - start) * 1000)
            body = b"".join([chunk async for chunk in r.aiter_bytes()])
            out["total_ms"] = round((perf_counter() - start) * 1000)
            out["status"] = r.status_code
            out["http_version"] = r.http_version
            encoding = (r.headers.get("content-encoding") or "").lower()
            out["compressed"] = any(x in encoding for x in ("gzip", "br", "deflate", "zstd"))
        html = body.decode("utf-8", errors="replace")
        # Decoded size: httpx un-gzips as it streams. `compressed` above is what says
        # whether it travelled compressed, so the two together tell the whole story.
        out["html_kb"] = round(len(body) / 1024)
        if out.get("status") == 200 and not _LOOKS_HTML.search(html):
            # Caught in production: forcing `Accept-Encoding: br` made Cloudflare answer in
            # brotli, which httpx cannot decode without the optional package — so we parsed
            # 8KB of binary and confidently reported "0 images, 0 render-blocking". Silent
            # nonsense is worse than a visible failure, so an unreadable body is an error.
            out["error"] = "unreadable body — wrong content-encoding?"
            out["verdict"] = verdict(out)
            return out
        blocking = count_blocking(html)
        out["blocking_scripts"] = blocking["scripts"]
        out["blocking_styles"] = blocking["styles"]
        images = image_urls(html, url)
        out["images_found"] = len(images)
        out["images_kb"], out["images_counted"] = await _image_weight(http, images)
    except Exception as e:
        logger.info("speed measure failed url=%s: %s", url, e)
        out["error"] = str(e)[:200]
        out.setdefault("status", None)
    out["verdict"] = verdict(out)
    return out


async def _newest_post_path(db: AsyncSession, *, tenant_id: int) -> str | None:
    slug = (
        await db.execute(
            select(BlogPost.slug)
            .where(BlogPost.tenant_id == tenant_id, BlogPost.status == "published")
            .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return f"/blog/{slug}" if slug else None


async def _upsert(db: AsyncSession, *, tenant_id: int, date: str, payload: dict) -> None:
    existing = (
        await db.execute(
            select(SeoSnapshot).where(
                SeoSnapshot.tenant_id == tenant_id,
                SeoSnapshot.kind == "speed",
                SeoSnapshot.date == date,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = payload
    else:
        db.add(SeoSnapshot(tenant_id=tenant_id, kind="speed", date=date, payload=payload))


async def run_daily(db: AsyncSession, *, tenant_id: int) -> dict:
    """Measure the pages that matter and persist one snapshot. No API key, no quota."""
    site = get_settings().PUBLIC_SITE_URL.rstrip("/")
    paths = ["/", "/blog", "/book"]
    newest = await _newest_post_path(db, tenant_id=tenant_id)
    if newest:
        paths.append(newest)

    # No Accept-Encoding override: httpx advertises exactly what it can decode. Asking for
    # brotli it cannot unpack is how this shipped a page of binary as "0 images".
    async with httpx.AsyncClient() as http:
        pages = [await measure_page(http, f"{site}{p}") for p in paths]

    warnings = sum(1 for p in pages for v in p.get("verdict", {}).values() if v == "warn")
    payload = {
        "method": "self",
        "measured_at": dt.datetime.now(dt.UTC).isoformat(),
        "pages": pages,
        "summary": {
            "pages": len(pages),
            "warnings": warnings,
            "slowest_ttfb_ms": max((p.get("ttfb_ms") or 0) for p in pages) if pages else 0,
        },
    }
    await _upsert(db, tenant_id=tenant_id, date=_denver_date(), payload=payload)
    await db.commit()
    logger.info("speed snapshot tenant=%s pages=%s warnings=%s", tenant_id, len(pages), warnings)
    return {"ok": True, "pages": len(pages), "warnings": warnings}
