"""pricing-scout — a tiny, isolated Playwright service that estimates live Uber prices.

The backend POSTs {origins, destination, when} (HMAC-signed). For each origin we try to
read an Uber Black / Black SUV price from uber.com and return it. EVERY failure mode —
captcha, layout change, login wall, timeout, IP block — degrades to ``null`` for that
origin; the service never raises, so the caller cleanly falls back to its formula.

This container is optional and internal-network only. It holds no Uber credentials.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pricing-scout")

SECRET = os.environ.get("PRICING_SCOUT_SECRET", "")
UBER_PRICE_URL = "https://www.uber.com/global/en/price-estimate/"

app = FastAPI(title="Black Volt pricing-scout")


def _verify(raw: bytes, signature: str | None) -> bool:
    if not SECRET or not signature:
        return False
    expected = base64.b64encode(
        hmac.new(SECRET.encode("utf-8"), raw, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, signature)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


async def _price_one(page, origin: str, destination: str) -> dict | None:
    """Best-effort single-route price read. Returns {"black","black_suv"} or None."""
    try:
        await page.goto(UBER_PRICE_URL, wait_until="domcontentloaded", timeout=25000)
        # Uber's public estimator uses labelled inputs; selectors are intentionally broad
        # and every miss returns None (caller uses the formula fallback).
        pu = page.get_by_placeholder("Enter pickup location")
        do = page.get_by_placeholder("Enter destination")
        await pu.fill(origin, timeout=8000)
        await page.keyboard.press("Enter")
        await do.fill(destination, timeout=8000)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)
        text = await page.content()
        # Extract "$NN" fares associated with Black / Black SUV rows.
        black = _find_price(text, ("UberX Black", "Black", "Uber Black"))
        suv = _find_price(text, ("Black SUV",))
        if black is None and suv is None:
            return None
        black = black if black is not None else (round(suv / 1.25, 2) if suv else None)
        suv = suv if suv is not None else (round(black * 1.25, 2) if black else None)
        return {"black": black, "black_suv": suv}
    except Exception as e:  # noqa: BLE001 — best-effort, never propagate
        logger.info("price read failed for %s: %s", origin, e)
        return None


def _find_price(html: str, labels: tuple[str, ...]) -> float | None:
    import re

    for label in labels:
        m = re.search(re.escape(label) + r"[^$]{0,120}?\$(\d+(?:\.\d{1,2})?)", html)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


@app.post("/scrape")
async def scrape(
    request: Request, x_bv_scout_signature: str | None = Header(default=None)
) -> dict:
    raw = await request.body()
    if not _verify(raw, x_bv_scout_signature):
        raise HTTPException(status_code=401, detail="bad_signature")
    import json

    payload = json.loads(raw or b"{}")
    origins = payload.get("origins") or []
    destination = payload.get("destination") or ""
    prices: dict[str, dict] = {}
    if not origins or not destination:
        return {"prices": prices}

    # Import Playwright lazily so /health works even if the browser image is missing.
    try:
        from playwright.async_api import async_playwright
    except Exception as e:  # noqa: BLE001
        logger.warning("playwright unavailable: %s", e)
        return {"prices": prices}

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox"])
            context = await browser.new_context(locale="en-US")
            page = await context.new_page()
            for origin in origins:
                got = await _price_one(page, origin, destination)
                if got:
                    prices[origin] = got
            await browser.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("scout session failed: %s", e)
    return {"prices": prices}
