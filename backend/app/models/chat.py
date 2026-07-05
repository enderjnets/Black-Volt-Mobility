"""Joules chatbot persistence (multi-tenant).

A `ChatConversation` is the single rolling thread a signed-in passenger has with
Joules (the public-site AI assistant): one per `(tenant_id, client_id)`. It
reopens on the next message if it was `CLOSED`. `ChatMessage` rows are the turns
(`user` / `assistant`, plus `owner` reserved for a future in-dashboard reply).
The owner reads these in the dashboard Inbox; `unread_for_staff` drives the badge
and `status`/`escalated_at` mark threads Joules handed off for a human.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class ChatStatus(str, enum.Enum):
    OPEN = "open"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    OWNER = "owner"


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_id", name="uq_chat_conv_tenant_client"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[ChatStatus] = mapped_column(
        pg_enum(ChatStatus, name="chat_status"),
        default=ChatStatus.OPEN,
        server_default=ChatStatus.OPEN.value,
        index=True,
        nullable=False,
    )
    lang: Mapped[str | None] = mapped_column(String(2), nullable=True)
    unread_for_staff: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    escalated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(pg_enum(ChatRole, name="chat_role"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    escalated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
