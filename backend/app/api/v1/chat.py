"""Joules chat API.

Passenger (require_passenger): one rolling conversation per client — post a
message and get Joules' reply, or load the history. Staff (require_staff): list
conversations for their tenant, read a thread (clears the unread badge), and
close a thread. Every conversation is scoped to the session's tenant + client;
staff only ever see their own tenant's threads (no cross-tenant view in v1).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_passenger, require_staff, resolve_tenant_id
from app.db.base import get_db
from app.models import (
    ChatConversation,
    ChatMessage,
    ChatRole,
    ChatStatus,
    Client,
    NotificationKind,
    Tenant,
)
from app.services import email, joules, notifications, ratelimit

router = APIRouter(prefix="/chat", tags=["chat"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ChatMessageOut(BaseModel):
    id: int
    role: str
    body: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ChatHistoryOut(BaseModel):
    conversation_id: int | None
    status: str | None
    messages: list[ChatMessageOut]


class ChatSendIn(BaseModel):
    message: str = Field(min_length=1, max_length=joules.MAX_MESSAGE_CHARS)
    lang: str | None = Field(default=None, max_length=5)


class ChatSendOut(BaseModel):
    reply: str
    escalated: bool
    conversation_id: int


class ThreadListItem(BaseModel):
    id: int
    client_name: str | None
    client_email: str | None
    client_phone: str | None
    status: str
    unread: int
    last_message_at: dt.datetime
    snippet: str


class ThreadDetailOut(BaseModel):
    id: int
    status: str
    client_name: str | None
    client_email: str | None
    client_phone: str | None
    messages: list[ChatMessageOut]


# ─── Helpers ─────────────────────────────────────────────────────────────────


async def _conversation_for(
    db: AsyncSession, tenant_id: int, client_id: int
) -> ChatConversation | None:
    return (
        await db.execute(
            select(ChatConversation).where(
                ChatConversation.tenant_id == tenant_id,
                ChatConversation.client_id == client_id,
            )
        )
    ).scalar_one_or_none()


async def _messages(db: AsyncSession, conversation_id: int, limit: int = 50) -> list[ChatMessage]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(reversed(rows))


# ─── Passenger endpoints ─────────────────────────────────────────────────────


@router.get("", response_model=ChatHistoryOut)
async def get_chat(
    payload: dict = Depends(require_passenger),
    db: AsyncSession = Depends(get_db),
) -> ChatHistoryOut:
    tenant_id = await resolve_tenant_id(db, payload)
    client_id = int(payload["cid"])
    conv = await _conversation_for(db, tenant_id, client_id)
    if conv is None:
        return ChatHistoryOut(conversation_id=None, status=None, messages=[])
    msgs = await _messages(db, conv.id)
    return ChatHistoryOut(
        conversation_id=conv.id,
        status=conv.status.value,
        messages=[
            ChatMessageOut(id=m.id, role=m.role.value, body=m.body, created_at=m.created_at)
            for m in msgs
        ],
    )


@router.post("/messages", response_model=ChatSendOut)
async def send_message(
    body: ChatSendIn,
    payload: dict = Depends(require_passenger),
    db: AsyncSession = Depends(get_db),
) -> ChatSendOut:
    tenant_id = await resolve_tenant_id(db, payload)
    client_id = int(payload["cid"])

    if not ratelimit.allow(
        f"chat:{tenant_id}:{client_id}:m", limit=5, window_seconds=60
    ) or not ratelimit.allow(
        f"chat:{tenant_id}:{client_id}:h", limit=30, window_seconds=3600
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="chat_rate_limited"
        )

    text = body.message.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty_message"
        )

    client = (
        await db.execute(select(Client).where(Client.id == client_id))
    ).scalar_one_or_none()
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()

    now = dt.datetime.now(dt.UTC)
    conv = await _conversation_for(db, tenant_id, client_id)
    if conv is None:
        try:
            async with db.begin_nested():
                conv = ChatConversation(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    status=ChatStatus.OPEN,
                    lang=(body.lang or (client.lang if client else None)),
                    last_message_at=now,
                )
                db.add(conv)
                await db.flush()
        except IntegrityError:
            # A concurrent first message won the UNIQUE(tenant_id, client_id)
            # race; adopt the row it created instead of 500-ing.
            conv = await _conversation_for(db, tenant_id, client_id)
            if conv is None:
                raise
            if conv.status == ChatStatus.CLOSED:
                conv.status = ChatStatus.OPEN
    elif conv.status == ChatStatus.CLOSED:
        conv.status = ChatStatus.OPEN

    # History BEFORE persisting this turn (chronological, trimmed by the service).
    prior = await _messages(db, conv.id, limit=joules.HISTORY_WINDOW)
    history = [{"role": m.role.value, "content": m.body} for m in prior if m.role != ChatRole.OWNER]

    db.add(ChatMessage(tenant_id=tenant_id, conversation_id=conv.id, role=ChatRole.USER, body=text))

    lang_hint = body.lang or conv.lang or (client.lang if client else None)
    reply_text, escalated = await joules.reply(
        db, tenant=tenant, client=client, history=history, user_text=text, lang_hint=lang_hint
    )

    db.add(
        ChatMessage(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role=ChatRole.ASSISTANT,
            body=reply_text,
            escalated=escalated,
        )
    )
    if body.lang:
        conv.lang = body.lang
    conv.last_message_at = now
    unread_before = conv.unread_for_staff or 0
    conv.unread_for_staff = unread_before + 1

    newly_escalated = escalated and conv.status != ChatStatus.ESCALATED
    if newly_escalated:
        conv.status = ChatStatus.ESCALATED
        conv.escalated_at = now

    await db.flush()

    if newly_escalated:
        transcript = await _messages(db, conv.id, limit=10)
        try:
            await email.notify_owner_chat_escalation(
                db, conversation=conv, client=client, messages=transcript
            )
        except Exception:  # escalation email must never break the reply
            pass

    await db.commit()

    # Bell notification (best-effort, after the messages are durable). A newly
    # escalated chat notifies as chat_escalated; otherwise notify once per unread
    # batch (unread_before == 0) so a run of passenger messages isn't spammy.
    client_name = (
        (getattr(client, "name", None) or getattr(client, "email", None)) if client else None
    )
    if newly_escalated:
        await notifications.emit(
            db,
            tenant_id=conv.tenant_id,
            kind=NotificationKind.chat_escalated,
            data={"conversation_id": conv.id, "client_name": client_name},
        )
    elif unread_before == 0:
        await notifications.emit(
            db,
            tenant_id=conv.tenant_id,
            kind=NotificationKind.chat_message,
            data={"conversation_id": conv.id, "client_name": client_name},
        )
    return ChatSendOut(reply=reply_text, escalated=escalated, conversation_id=conv.id)


# ─── Staff endpoints ─────────────────────────────────────────────────────────


@router.get("/threads", response_model=list[ThreadListItem])
async def list_threads(
    status_filter: str | None = Query(default=None, alias="status"),
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadListItem]:
    tenant_id = await resolve_tenant_id(db, payload)
    stmt = (
        select(ChatConversation, Client)
        .join(Client, Client.id == ChatConversation.client_id)
        .where(ChatConversation.tenant_id == tenant_id)
        .order_by(ChatConversation.last_message_at.desc())
        .limit(100)
    )
    if status_filter:
        try:
            stmt = stmt.where(ChatConversation.status == ChatStatus(status_filter))
        except ValueError:
            pass  # unknown status → ignore the filter rather than 500 on the enum
    rows = (await db.execute(stmt)).all()

    items: list[ThreadListItem] = []
    for conv, client in rows:
        last = (
            await db.execute(
                select(ChatMessage.body)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(ChatMessage.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        snippet = (last or "")[:120]
        items.append(
            ThreadListItem(
                id=conv.id,
                client_name=client.name,
                client_email=client.email,
                client_phone=client.phone,
                status=conv.status.value,
                unread=conv.unread_for_staff or 0,
                last_message_at=conv.last_message_at,
                snippet=snippet,
            )
        )
    return items


async def _staff_conversation(
    db: AsyncSession, tenant_id: int, conversation_id: int
) -> ChatConversation:
    conv = (
        await db.execute(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread_not_found")
    return conv


@router.get("/threads/{conversation_id}", response_model=ThreadDetailOut)
async def get_thread(
    conversation_id: int,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> ThreadDetailOut:
    tenant_id = await resolve_tenant_id(db, payload)
    conv = await _staff_conversation(db, tenant_id, conversation_id)
    client = (
        await db.execute(select(Client).where(Client.id == conv.client_id))
    ).scalar_one_or_none()
    msgs = await _messages(db, conv.id, limit=200)
    if conv.unread_for_staff:
        conv.unread_for_staff = 0
        await db.commit()
    return ThreadDetailOut(
        id=conv.id,
        status=conv.status.value,
        client_name=client.name if client else None,
        client_email=client.email if client else None,
        client_phone=client.phone if client else None,
        messages=[
            ChatMessageOut(id=m.id, role=m.role.value, body=m.body, created_at=m.created_at)
            for m in msgs
        ],
    )


@router.post("/threads/{conversation_id}/close")
async def close_thread(
    conversation_id: int,
    payload: dict = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = await resolve_tenant_id(db, payload)
    conv = await _staff_conversation(db, tenant_id, conversation_id)
    conv.status = ChatStatus.CLOSED
    await db.commit()
    return {"ok": True, "status": conv.status.value}
