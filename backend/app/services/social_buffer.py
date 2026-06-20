"""Buffer GraphQL adapter — Black Volt's real social-publishing path.

The owner's Buffer account holds the IG/FB/TikTok OAuth tokens and performs the
actual publishing; we push owner-approved posts to it with a personal API key.
This module is the thin, DB-free client for that handoff (mirrors render_client).

GraphQL endpoint + shapes verified live against the account on 2026-06-20.
The API key is read from settings, never logged, never returned to a client.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("blackvolt.social.buffer")

BUFFER_API_URL = "https://api.buffer.com"

_CHANNELS_Q = """
query Channels($orgId: OrganizationId!) {
  channels(input: { organizationId: $orgId }) {
    id name service displayName isDisconnected isLocked
  }
}
"""

# createPost returns a PostActionPayload union: PostActionSuccess wraps the Post,
# every other member is a typed error carrying a human message.
_CREATE_POST_M = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id status dueAt channelId } }
    ... on InvalidInputError { message }
    ... on UnauthorizedError { message }
    ... on NotFoundError { message }
    ... on LimitReachedError { message }
    ... on RestProxyError { message code }
    ... on UnexpectedError { message }
  }
}
"""

_NETWORK_META = {
    "instagram": lambda: {"instagram": {"type": "reel", "shouldShareToFeed": True}},
}


class BufferError(Exception):
    """A Buffer HTTP or GraphQL failure (message is sanitized — never the key)."""

    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


def is_live() -> bool:
    return get_settings().is_buffer_live


async def _gql(query: str, variables: dict) -> dict:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.BUFFER_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                BUFFER_API_URL, json={"query": query, "variables": variables}, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("buffer request failed: %s", type(e).__name__)
        raise BufferError("buffer_request_failed", transient=True) from e
    if data.get("errors"):
        msgs = "; ".join(str(err.get("message", "?")) for err in data["errors"])
        logger.error("buffer graphql error: %s", msgs)
        raise BufferError(f"buffer_graphql_error: {msgs}")
    return data.get("data") or {}


async def list_channels() -> list[dict]:
    settings = get_settings()
    data = await _gql(_CHANNELS_Q, {"orgId": settings.BUFFER_ORG_ID})
    out = []
    for c in data.get("channels") or []:
        out.append({
            "id": c.get("id"),
            "service": c.get("service"),
            "name": c.get("name"),
            "display_name": c.get("displayName") or c.get("name"),
            "connected": not c.get("isDisconnected") and not c.get("isLocked"),
        })
    return out


async def create_post(
    *,
    channel_id: str,
    service: str,
    text: str,
    video_url: str,
    thumbnail_url: str | None = None,
    mode: str,
    due_at=None,
) -> dict:
    video: dict = {"url": video_url}
    if thumbnail_url:
        video["thumbnailUrl"] = thumbnail_url
    input_obj: dict = {
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": mode,
        "text": text,
        "assets": [{"video": video}],
    }
    if mode == "customScheduled" and due_at is not None:
        input_obj["dueAt"] = due_at.isoformat() if hasattr(due_at, "isoformat") else due_at
    meta_fn = _NETWORK_META.get(service)
    if meta_fn:
        input_obj["metadata"] = meta_fn()
    data = await _gql(_CREATE_POST_M, {"input": input_obj})
    result = data.get("createPost") or {}
    if result.get("__typename") == "PostActionSuccess":
        post = result.get("post") or {}
        return {"id": post.get("id"), "status": post.get("status"), "due_at": post.get("dueAt")}
    # Any other union member is a terminal rejection from Buffer (bad input, limit
    # reached, …) — retrying won't help, so surface it as a non-transient error.
    msg = result.get("message") or result.get("__typename") or "create_failed"
    raise BufferError(f"buffer_create_rejected: {msg}")
