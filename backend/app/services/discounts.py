from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount import DiscountCampaign, DiscountCode

DRIVER_MAX_PCT = 50.0
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class DiscountError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _gen_code() -> str:
    return "BV-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


async def create_code(
    db: AsyncSession,
    *,
    tenant_id: int,
    is_admin: bool,
    code: str,
    discount_pct: float,
    max_uses: int,
    expires_at: dt.datetime,
    created_by_email: str,
    campaign_id: int | None = None,
) -> DiscountCode:
    if discount_pct <= 0 or discount_pct > 100:
        raise DiscountError("pct_out_of_range")
    if not is_admin and discount_pct > DRIVER_MAX_PCT:
        raise DiscountError("pct_too_high")
    if max_uses < 1:
        raise DiscountError("max_uses_invalid")
    norm = (code or "").strip().upper() or _gen_code()
    existing = await db.scalar(select(DiscountCode).where(DiscountCode.code == norm))
    if existing is not None:
        raise DiscountError("duplicate")
    row = DiscountCode(
        tenant_id=tenant_id,
        code=norm,
        discount_pct=float(discount_pct),
        max_uses=max_uses,
        expires_at=expires_at,
        created_by_email=created_by_email,
        campaign_id=campaign_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_codes(db: AsyncSession, tenant_id: int) -> list[DiscountCode]:
    res = await db.scalars(
        select(DiscountCode)
        .where(DiscountCode.tenant_id == tenant_id)
        .order_by(DiscountCode.created_at.desc())
    )
    return list(res)


async def _get_owned(db: AsyncSession, tenant_id: int, code_id: int) -> DiscountCode:
    row = await db.scalar(
        select(DiscountCode).where(
            DiscountCode.id == code_id, DiscountCode.tenant_id == tenant_id
        )
    )
    if row is None:
        raise DiscountError("not_found")
    return row


async def set_active(
    db: AsyncSession, tenant_id: int, code_id: int, active: bool
) -> DiscountCode:
    row = await _get_owned(db, tenant_id, code_id)
    row.active = active
    await db.commit()
    await db.refresh(row)
    return row


async def delete_code(db: AsyncSession, tenant_id: int, code_id: int) -> None:
    row = await _get_owned(db, tenant_id, code_id)
    await db.delete(row)
    await db.commit()


async def validate_code(db: AsyncSession, code: str) -> DiscountCode:
    norm = (code or "").strip().upper()
    row = await db.scalar(select(DiscountCode).where(DiscountCode.code == norm))
    if row is None:
        raise DiscountError("not_found")
    if not row.active:
        raise DiscountError("inactive")
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.UTC)
    if exp < _now():
        raise DiscountError("expired")
    if row.used_count >= row.max_uses:
        raise DiscountError("exhausted")
    return row


async def redeem(db: AsyncSession, code_row: DiscountCode) -> None:
    res = await db.execute(
        update(DiscountCode)
        .where(
            DiscountCode.id == code_row.id,
            DiscountCode.used_count < DiscountCode.max_uses,
        )
        .values(used_count=DiscountCode.used_count + 1)
    )
    if res.rowcount == 0:
        raise DiscountError("exhausted")
    await db.commit()


async def create_campaign(
    db: AsyncSession,
    *,
    name: str,
    discount_pct: float,
    max_uses: int,
    expires_at: dt.datetime,
    created_by_email: str,
    created_by_tenant_id: int,
    driver_tenant_ids: list[int],
) -> tuple[DiscountCampaign, list[DiscountCode]]:
    if discount_pct <= 0 or discount_pct > 100:
        raise DiscountError("pct_out_of_range")
    if not driver_tenant_ids:
        raise DiscountError("no_drivers")
    camp = DiscountCampaign(
        name=name.strip(),
        discount_pct=float(discount_pct),
        max_uses=max_uses,
        expires_at=expires_at,
        created_by_email=created_by_email,
        tenant_id=created_by_tenant_id,
    )
    db.add(camp)
    await db.flush()
    base = "".join(ch for ch in name.strip().upper() if ch.isalnum())[:12] or "PROMO"
    codes: list[DiscountCode] = []
    for tid in driver_tenant_ids:
        suffix = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        row = DiscountCode(
            tenant_id=tid,
            code=f"{base}-{suffix}",
            discount_pct=float(discount_pct),
            max_uses=max_uses,
            expires_at=expires_at,
            created_by_email=created_by_email,
            campaign_id=camp.id,
        )
        db.add(row)
        codes.append(row)
    await db.commit()
    for c in codes:
        await db.refresh(c)
    await db.refresh(camp)
    return camp, codes
