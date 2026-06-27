"""Legal agreement endpoints: fetch the document a user must sign, and accept it."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth
from app.db.base import get_db
from app.legal import (
    DRIVER_AGREEMENT,
    audience,
    current_version,
    is_known_doc,
    load_doc,
    normalize_lang,
)
from app.services import legal as legal_svc

router = APIRouter(prefix="/agreements", tags=["agreements"])


@router.get("/pending")
async def list_pending(
    payload: dict = Depends(require_auth), db: AsyncSession = Depends(get_db)
):
    return {"pending": await legal_svc.pending_agreements(db, payload)}


@router.get("/{doc_type}")
async def get_document(
    doc_type: str,
    lang: str = "en",
    payload: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if not is_known_doc(doc_type):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_document")
    # A user may only fetch the document that applies to them.
    if await legal_svc.required_doc(db, payload) != doc_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_your_document")
    title, content_md = load_doc(doc_type, lang)
    return {
        "doc_type": doc_type,
        "version": current_version(doc_type),
        "audience": audience(doc_type),
        "lang": normalize_lang(lang),
        "title": title,
        "content_md": content_md,
    }


class AcceptBody(BaseModel):
    version: str
    lang: str = "en"
    signed_name: str | None = None


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.post("/{doc_type}/accept")
async def accept_document(
    doc_type: str,
    body: AcceptBody,
    request: Request,
    payload: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if not is_known_doc(doc_type):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_document")
    if await legal_svc.required_doc(db, payload) != doc_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_your_document")
    if body.version != current_version(doc_type):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="stale_version")
    if doc_type == DRIVER_AGREEMENT and not (body.signed_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="signed_name_required"
        )
    await legal_svc.record_consent(
        db,
        payload,
        doc_type,
        version=body.version,
        lang=normalize_lang(body.lang),
        signed_name=(body.signed_name or None),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True}
