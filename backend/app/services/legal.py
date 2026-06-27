"""Legal-agreement consent: who must sign what, and recording acceptance.

Gate matrix:
- passenger              -> client_terms
- driver / non-owner admin (staff) -> driver_agreement
- principal owner (master/password session) or an email in OWNER_EMAILS -> exempt
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.legal import CLIENT_TERMS, DRIVER_AGREEMENT, audience, current_version
from app.models.allowed_user import AllowedUser
from app.models.document_consent import (
    SUBJECT_ALLOWED_USER,
    SUBJECT_CLIENT,
    DocumentConsent,
)
from app.services import auth as auth_svc
from app.services.tenancy import get_default_tenant


async def _is_principal_owner(db: AsyncSession, payload: dict) -> bool:
    """The dueño: the master/password session — owner role, NO email, no client,
    default tenant. Pinned Google admins also sit on the default tenant but carry an
    email, so the email check is what separates the owner from non-owner admins
    (who must sign the driver agreement)."""
    if payload.get("role") != auth_svc.ROLE_OWNER:
        return False
    if payload.get("email") or payload.get("cid") is not None:
        return False
    default = await get_default_tenant(db)
    return payload.get("tid") == default.id


async def required_doc(db: AsyncSession, payload: dict) -> str | None:
    """Which legal document this session must have signed, or None if exempt."""
    role = payload.get("role")
    if role == auth_svc.ROLE_PASSENGER:
        return CLIENT_TERMS
    if role in auth_svc.STAFF_ROLES:
        if await _is_principal_owner(db, payload):
            return None
        email = (payload.get("email") or "").lower()
        if email and email in get_settings().owner_emails_list:
            return None
        return DRIVER_AGREEMENT
    return None


async def _existing_consent(
    db: AsyncSession,
    doc_type: str,
    version: str,
    *,
    client_id: int | None = None,
    allowed_user_id: int | None = None,
) -> DocumentConsent | None:
    stmt = select(DocumentConsent).where(
        DocumentConsent.doc_type == doc_type,
        DocumentConsent.version == version,
    )
    if client_id is not None:
        stmt = stmt.where(DocumentConsent.client_id == client_id)
    elif allowed_user_id is not None:
        stmt = stmt.where(DocumentConsent.allowed_user_id == allowed_user_id)
    else:
        return None
    return (await db.execute(stmt)).scalars().first()


async def _resolve_subject(
    db: AsyncSession, payload: dict
) -> tuple[str, int | None, int | None]:
    """Return ``(subject_type, client_id, allowed_user_id)`` for the session."""
    if payload.get("role") == auth_svc.ROLE_PASSENGER:
        cid = payload.get("cid")
        return (SUBJECT_CLIENT, int(cid) if cid is not None else None, None)
    email = (payload.get("email") or "").lower()
    if not email:
        return (SUBJECT_ALLOWED_USER, None, None)
    au = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    return (SUBJECT_ALLOWED_USER, None, au.id if au else None)


async def pending_agreements(db: AsyncSession, payload: dict) -> list[dict]:
    """Documents the current user still needs to sign (at the current version)."""
    doc = await required_doc(db, payload)
    if doc is None:
        return []
    version = current_version(doc)
    _subject_type, client_id, allowed_user_id = await _resolve_subject(db, payload)
    existing = await _existing_consent(
        db, doc, version, client_id=client_id, allowed_user_id=allowed_user_id
    )
    if existing is not None:
        return []
    return [{"doc_type": doc, "version": version, "audience": audience(doc)}]


async def record_consent(
    db: AsyncSession,
    payload: dict,
    doc_type: str,
    *,
    version: str,
    lang: str,
    signed_name: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> DocumentConsent:
    subject_type, client_id, allowed_user_id = await _resolve_subject(db, payload)
    if client_id is None and allowed_user_id is None:
        # No identifiable subject — refuse rather than write an orphan all-NULL row
        # (which the unique constraints can't dedupe and which would loop the gate).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unresolved_subject"
        )
    existing = await _existing_consent(
        db, doc_type, version, client_id=client_id, allowed_user_id=allowed_user_id
    )
    if existing is not None:
        return existing
    row = DocumentConsent(
        tenant_id=payload.get("tid"),
        doc_type=doc_type,
        version=version,
        subject_type=subject_type,
        client_id=client_id,
        allowed_user_id=allowed_user_id,
        signed_name=(signed_name or None),
        lang=lang,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent accept won the race; treat as idempotent success.
        await db.rollback()
        existing = await _existing_consent(
            db, doc_type, version, client_id=client_id, allowed_user_id=allowed_user_id
        )
        if existing is not None:
            return existing
        raise
    await db.refresh(row)
    return row


async def ensure_signed(db: AsyncSession, payload: dict) -> None:
    """Raise 403 ``agreement_required`` if the session has unsigned agreements.

    Defense-in-depth on top of the frontend gate: callers attach this to the
    sensitive mutation endpoints so the gate cannot be bypassed via the API.
    """
    pending = await pending_agreements(db, payload)
    if pending:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "agreement_required",
                "pending": [p["doc_type"] for p in pending],
            },
        )
