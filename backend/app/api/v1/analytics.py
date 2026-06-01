"""Analytics API: open event ingest (/track) + staff-only summary.

/track is open (like /quote) so the public portal can report usage. It accepts a
JSON body OR a navigator.sendBeacon payload (text/plain body that is JSON). Events
are pseudonymous; country is derived from Cloudflare's CF-IPCountry header, never a
raw IP. /analytics/summary backs the driver Insights dashboard (staff only)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_payload, require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import analytics

router = APIRouter(tags=["analytics"])


class TrackBody(BaseModel):
    events: list[dict] = []


def _country(request: Request) -> str | None:
    c = request.headers.get("CF-IPCountry") or request.headers.get("cf-ipcountry")
    if not c or c in ("XX", "T1"):  # CF placeholders for unknown / Tor
        return None
    return c[:2].upper()


@router.post("/track", status_code=202)
async def track(request: Request, db: AsyncSession = Depends(get_db)):
    """Ingest a batch of usage events. Open endpoint; fails soft (never blocks the
    page) — returns {ok, count} and swallows malformed payloads."""
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}")
    except (ValueError, TypeError):
        return {"ok": False, "count": 0}
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not events:
        return {"ok": True, "count": 0}

    payload = current_payload(request)
    tenant_id = await resolve_tenant_id(db, payload)
    ctx = {
        "client_id": (payload or {}).get("cid"),
        "role": (payload or {}).get("role") or "anon",
        "country": _country(request),
        "user_agent": request.headers.get("user-agent"),
    }
    try:
        n = await analytics.record_events(db, tenant_id=tenant_id, events=events, ctx=ctx)
    except Exception:
        await db.rollback()
        return {"ok": False, "count": 0}
    return {"ok": True, "count": n}


@router.get("/analytics/summary")
async def analytics_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
    days: int = Query(default=30, ge=1, le=365),
):
    tenant_id = await resolve_tenant_id(db, payload)
    return await analytics.summary(db, tenant_id=tenant_id, days=days)
