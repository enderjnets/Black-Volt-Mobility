"""Record of a user accepting a versioned legal document (clickwrap / e-signature).

One row per (subject, document, version). Captures who signed, which version, when,
the IP/user-agent at signing, the language shown, and — for drivers — the typed
legal name used as the electronic signature.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SUBJECT_CLIENT = "client"
SUBJECT_ALLOWED_USER = "allowed_user"


class DocumentConsent(Base):
    __tablename__ = "document_consents"
    __table_args__ = (
        UniqueConstraint("client_id", "doc_type", "version", name="uq_consent_client_doc_ver"),
        UniqueConstraint(
            "allowed_user_id", "doc_type", "version", name="uq_consent_user_doc_ver"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True
    )
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=True
    )
    allowed_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("allowed_users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    signed_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
