"""One-tap shift log: the owner's four buttons become state segments and offers.

The model (demand_model.py) needs two things the Uber export cannot give: minutes
spent waiting in each cell (exposure) and the offers that arrived there, by product.
Every tap carries a client-generated id so a retried POST from a flaky connection is
a no-op, never a double count. Pings only extend the open segment's `last_ping_at`.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import DriverStateSegment, EarnerState, OfferEvent, SegmentSource, UberProduct
from app.services.demand_model import DENVER

KINDS = ("online", "here", "ping", "offer", "offline")
PRODUCTS = tuple(p.value for p in UberProduct)


def cell_of(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    import h3

    return h3.latlng_to_cell(lat, lng, 8)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def in_den_lot(lat: float | None, lng: float | None) -> bool:
    s = get_settings()
    if lat is None or lng is None or s.DEN_LOT_LAT is None or s.DEN_LOT_LNG is None:
        return False
    return _haversine_m(lat, lng, s.DEN_LOT_LAT, s.DEN_LOT_LNG) <= s.DEN_LOT_RADIUS_M


def _r5(v: float | None) -> float | None:
    return None if v is None else round(v, 5)


async def _open_segment(db: AsyncSession, tenant_id: int) -> DriverStateSegment | None:
    return (
        await db.execute(
            select(DriverStateSegment)
            .where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.source == SegmentSource.LIVE,
                DriverStateSegment.end_at.is_(None),
            )
            .order_by(DriverStateSegment.begin_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _close(seg: DriverStateSegment, at: datetime, lat: float | None, lng: float | None) -> None:
    seg.end_at = at
    seg.end_lat = _r5(lat) if lat is not None else seg.end_lat
    seg.end_lng = _r5(lng) if lng is not None else seg.end_lng


def _new_segment(
    tenant_id: int, key: str, state: EarnerState, at: datetime, lat, lng
) -> DriverStateSegment:
    return DriverStateSegment(
        tenant_id=tenant_id,
        dedup_key=key,
        state=state,
        begin_at=at,
        begin_lat=_r5(lat),
        begin_lng=_r5(lng),
        h3_r8=cell_of(lat, lng),
        zone_key="den_lot" if in_den_lot(lat, lng) else None,
        source=SegmentSource.LIVE,
    )


def _seg_dict(seg: DriverStateSegment, kind: str) -> dict:
    return {
        "id": seg.id,
        "kind": kind,
        "at": seg.begin_at.isoformat(),
        "lat": seg.begin_lat,
        "lng": seg.begin_lng,
        "h3_r8": seg.h3_r8,
        "product": None,
        "accepted": None,
        "fare": None,
        "zone_key": seg.zone_key,
        "no_position": seg.begin_lat is None,
    }


def _offer_dict(o: OfferEvent) -> dict:
    return {
        "id": o.id,
        "kind": "offer",
        "at": o.at.isoformat(),
        "lat": o.lat,
        "lng": o.lng,
        "h3_r8": o.h3_r8,
        "product": o.product.value,
        "accepted": o.accepted,
        "fare": float(o.fare) if o.fare is not None else None,
        "zone_key": "den_lot" if in_den_lot(o.lat, o.lng) else None,
        "no_position": o.lat is None,
    }


async def log_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    client_event_id: str,
    kind: str,
    at: datetime | None = None,
    lat: float | None = None,
    lng: float | None = None,
    product: str | None = None,
    accepted: bool | None = None,
    fare: float | None = None,
    dest_text: str | None = None,
) -> tuple[dict, bool]:
    if kind not in KINDS:
        raise ValueError("bad_kind")
    if kind == "offer" and product not in PRODUCTS:
        raise ValueError("bad_product")
    now = (at or datetime.now(UTC)).astimezone(UTC)

    # Idempotency: the same tap id always returns the row it created.
    if kind == "offer":
        dup = (
            await db.execute(
                select(OfferEvent).where(
                    OfferEvent.tenant_id == tenant_id, OfferEvent.client_event_id == client_event_id
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return _offer_dict(dup), False
    else:
        dup = (
            await db.execute(
                select(DriverStateSegment).where(
                    DriverStateSegment.tenant_id == tenant_id,
                    DriverStateSegment.dedup_key == client_event_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return _seg_dict(dup, kind), False

    current = await _open_segment(db, tenant_id)

    if kind == "ping":
        if current is not None:
            current.last_ping_at = now
            current.end_lat = _r5(lat) if lat is not None else current.end_lat
            current.end_lng = _r5(lng) if lng is not None else current.end_lng
            await db.commit()
            return _seg_dict(current, "ping"), True
        # A ping with nothing open behaves like "online".
        kind = "online"

    if kind in ("online", "here"):
        if current is not None:
            _close(current, now, lat, lng)
        seg = _new_segment(tenant_id, client_event_id, EarnerState.OPEN, now, lat, lng)
        db.add(seg)
        await db.commit()
        await db.refresh(seg)
        return _seg_dict(seg, kind), True

    if kind == "offline":
        if current is not None:
            _close(current, now, lat, lng)
        seg = _new_segment(tenant_id, client_event_id, EarnerState.OFFLINE, now, lat, lng)
        seg.end_at = now
        db.add(seg)
        await db.commit()
        await db.refresh(seg)
        return _seg_dict(seg, "offline"), True

    # kind == "offer"
    offer = OfferEvent(
        tenant_id=tenant_id,
        client_event_id=client_event_id,
        at=now,
        lat=_r5(lat),
        lng=_r5(lng),
        h3_r8=cell_of(lat, lng),
        product=UberProduct(product),
        accepted=bool(accepted),
        fare=fare,
        dest_text=(dest_text or None),
    )
    db.add(offer)
    if accepted:
        if current is not None:
            _close(current, now, lat, lng)
        db.add(
            _new_segment(
                tenant_id, f"{client_event_id}:enroute", EarnerState.ENROUTE, now, lat, lng
            )
        )
    await db.commit()
    await db.refresh(offer)
    return _offer_dict(offer), True


async def today(db: AsyncSession, *, tenant_id: int, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).astimezone(DENVER)
    start = datetime.combine(now.date(), time(0), tzinfo=DENVER).astimezone(UTC)
    end = start + timedelta(days=2)  # generous; filtered below by local date
    segs = (
        await db.execute(
            select(DriverStateSegment)
            .where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.source == SegmentSource.LIVE,
                DriverStateSegment.begin_at >= start,
                DriverStateSegment.begin_at < end,
            )
            .order_by(DriverStateSegment.begin_at.asc())
        )
    ).scalars().all()
    segs = [s for s in segs if s.begin_at.astimezone(DENVER).date() == now.date()]
    offers = (
        await db.execute(
            select(OfferEvent)
            .where(OfferEvent.tenant_id == tenant_id, OfferEvent.at >= start, OfferEvent.at < end)
            .order_by(OfferEvent.at.asc())
        )
    ).scalars().all()
    offers = [o for o in offers if o.at.astimezone(DENVER).date() == now.date()]

    events: list[dict] = []
    for s in segs:
        if s.state == EarnerState.ENROUTE:
            continue  # represented by its accepted offer
        events.append(_seg_dict(s, "online" if s.state == EarnerState.OPEN else "offline"))
    events += [_offer_dict(o) for o in offers]
    events.sort(key=lambda e: e["at"], reverse=True)

    current = await _open_segment(db, tenant_id)
    state = current.state.value if current is not None else "offline"
    seg_out = []
    for s in segs:
        if s.state == EarnerState.OFFLINE:
            continue
        end_at = s.end_at or s.last_ping_at or s.begin_at
        seg_out.append(
            {
                "state": s.state.value,
                "begin_at": s.begin_at.isoformat(),
                "end_at": s.end_at.isoformat() if s.end_at else None,
                "minutes": round((end_at - s.begin_at).total_seconds() / 60.0, 1),
                "zone_key": s.zone_key,
                "h3_r8": s.h3_r8,
            }
        )
    return {
        "state": state,
        "open_since": current.begin_at.isoformat() if current is not None else None,
        "events": events,
        "segments": seg_out,
    }
