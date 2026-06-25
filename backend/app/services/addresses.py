"""Saved address-book persistence + the one-default invariant.

All queries are scoped by client_id (and tenant_id when known); callers pass
the trusted values from the session token, never the request body. The
"exactly one default" rule lives here so the API layer stays thin and every
mutation path keeps the invariant inside a single transaction.
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClientAddress


def serialize(a: ClientAddress) -> dict:
    return {
        "id": a.id,
        "label": a.label,
        "address": a.address,
        "is_default": a.is_default,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _scope(stmt, *, tenant_id: int | None, client_id: int):
    stmt = stmt.where(ClientAddress.client_id == client_id)
    if tenant_id is not None:
        stmt = stmt.where(ClientAddress.tenant_id == tenant_id)
    return stmt


async def list_for(
    db: AsyncSession, *, tenant_id: int | None, client_id: int
) -> list[ClientAddress]:
    stmt = _scope(select(ClientAddress), tenant_id=tenant_id, client_id=client_id).order_by(
        ClientAddress.is_default.desc(),
        ClientAddress.created_at.asc(),
        ClientAddress.id.asc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_owned(
    db: AsyncSession, *, tenant_id: int | None, client_id: int, address_id: int
) -> ClientAddress | None:
    stmt = _scope(
        select(ClientAddress).where(ClientAddress.id == address_id),
        tenant_id=tenant_id,
        client_id=client_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_for(db: AsyncSession, *, tenant_id: int | None, client_id: int) -> int:
    stmt = _scope(
        select(func.count()).select_from(ClientAddress),
        tenant_id=tenant_id,
        client_id=client_id,
    )
    return int((await db.execute(stmt)).scalar_one())


async def clear_defaults(
    db: AsyncSession, *, tenant_id: int | None, client_id: int, except_id: int | None = None
) -> None:
    stmt = update(ClientAddress).where(ClientAddress.client_id == client_id)
    if tenant_id is not None:
        stmt = stmt.where(ClientAddress.tenant_id == tenant_id)
    if except_id is not None:
        stmt = stmt.where(ClientAddress.id != except_id)
    await db.execute(stmt.values(is_default=False))


async def ensure_one_default(
    db: AsyncSession, *, tenant_id: int | None, client_id: int
) -> None:
    """Promote the oldest remaining address to default if none is set."""
    rows = await list_for(db, tenant_id=tenant_id, client_id=client_id)
    if rows and not any(r.is_default for r in rows):
        oldest = min(rows, key=lambda r: r.id)
        oldest.is_default = True


async def create(
    db: AsyncSession,
    *,
    tenant_id: int,
    client_id: int,
    address: str,
    label: str | None,
    is_default: bool,
) -> ClientAddress:
    # The very first saved address is always the default, even if not requested.
    existing = await count_for(db, tenant_id=tenant_id, client_id=client_id)
    make_default = is_default or existing == 0
    if make_default:
        await clear_defaults(db, tenant_id=tenant_id, client_id=client_id)
    row = ClientAddress(
        tenant_id=tenant_id,
        client_id=client_id,
        address=address,
        label=label,
        is_default=make_default,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def set_default(
    db: AsyncSession, *, tenant_id: int | None, client_id: int, row: ClientAddress
) -> ClientAddress:
    await clear_defaults(db, tenant_id=tenant_id, client_id=client_id, except_id=row.id)
    row.is_default = True
    await db.commit()
    await db.refresh(row)
    return row


async def delete_row(
    db: AsyncSession, *, tenant_id: int | None, client_id: int, row: ClientAddress
) -> None:
    was_default = row.is_default
    await db.delete(row)
    await db.flush()
    if was_default:
        await ensure_one_default(db, tenant_id=tenant_id, client_id=client_id)
    await db.commit()
