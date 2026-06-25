"""Passenger saved-address book API.

A signed-in passenger manages their own labeled addresses with exactly one
default. Scoping is by the session's client_id (`cid`) + tenant (`tid`) — never
a value from the request body — so a passenger can only ever read or mutate
their own rows; anything else returns 404 (same posture as rides.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_passenger
from app.db.base import get_db
from app.models import ClientAddress
from app.services import addresses as addr_svc

router = APIRouter(tags=["me"])


class AddressCreate(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    address: str = Field(min_length=1, max_length=400)
    is_default: bool = False


class AddressPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, min_length=1, max_length=400)
    is_default: bool | None = None


def _scope(payload: dict) -> tuple[int, int]:
    """Trusted (client_id, tenant_id) from the session token. Both required —
    a passenger token always carries them."""
    cid = int(payload["cid"])
    tid = payload.get("tid")
    if tid is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_tenant")
    return cid, int(tid)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


async def _load_owned(db: AsyncSession, payload: dict, address_id: int) -> ClientAddress:
    cid, tid = _scope(payload)
    row = await addr_svc.get_owned(db, tenant_id=tid, client_id=cid, address_id=address_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="address_not_found")
    return row


@router.get("/me/addresses")
async def list_addresses(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    cid, tid = _scope(payload)
    rows = await addr_svc.list_for(db, tenant_id=tid, client_id=cid)
    return {"addresses": [addr_svc.serialize(r) for r in rows]}


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
async def create_address(
    body: AddressCreate,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    cid, tid = _scope(payload)
    address = _clean(body.address)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="address_required"
        )
    row = await addr_svc.create(
        db, tenant_id=tid, client_id=cid, address=address,
        label=_clean(body.label), is_default=body.is_default,
    )
    return addr_svc.serialize(row)


@router.patch("/me/addresses/{address_id}")
async def update_address(
    address_id: int,
    body: AddressPatch,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    cid, tid = _scope(payload)
    row = await _load_owned(db, payload, address_id)
    changes = body.model_dump(exclude_unset=True)

    if "address" in changes:
        cleaned = _clean(changes["address"])
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="address_required"
            )
        row.address = cleaned

    if "label" in changes:
        row.label = _clean(changes["label"])

    if "is_default" in changes:
        if changes["is_default"]:
            await addr_svc.clear_defaults(db, tenant_id=tid, client_id=cid, except_id=row.id)
            row.is_default = True
        else:
            row.is_default = False

    await db.flush()
    await addr_svc.ensure_one_default(db, tenant_id=tid, client_id=cid)
    await db.commit()
    await db.refresh(row)
    return addr_svc.serialize(row)


@router.post("/me/addresses/{address_id}/default")
async def make_default(
    address_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    cid, tid = _scope(payload)
    row = await _load_owned(db, payload, address_id)
    row = await addr_svc.set_default(db, tenant_id=tid, client_id=cid, row=row)
    return addr_svc.serialize(row)


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_passenger),
):
    cid, tid = _scope(payload)
    row = await _load_owned(db, payload, address_id)
    await addr_svc.delete_row(db, tenant_id=tid, client_id=cid, row=row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
