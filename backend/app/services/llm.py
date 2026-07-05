"""LLM client — thin wrapper over the `anthropic` SDK with a per-call base_url.

Both Kimi and MiniMax speak the anthropic-messages protocol, so a single SDK
with a swappable `base_url` serves every provider. This module is provider- and
feature-agnostic: callers pass the model/base_url/api_key they want. Today only
`vision_complete` is used (Smart reservation extraction); Phase 7 reuses the
same client for chat. NEVER pass an Anthropic OAuth token here — product traffic
goes to Kimi / MiniMax only (see CLAUDE.md anti-pattern #1).
"""
from __future__ import annotations

from app.config import get_settings


class LLMError(RuntimeError):
    pass


def _client(base_url: str, api_key: str):
    """Build an AsyncAnthropic pointed at a provider's anthropic-compatible API."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        api_key=api_key,
        base_url=base_url,
        timeout=get_settings().LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


async def vision_complete(
    *,
    prompt: str,
    images: list[tuple[str, str]],
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 1024,
) -> str:
    """Send one user message (text prompt + N base64 images) and return the text.

    `images` is a list of (media_type, base64_data) tuples — all images land in
    a single message so the model reasons over them as one conversation. Raises
    LLMError on transport/SDK failure or an empty/non-text response.
    """
    if not api_key:
        raise LLMError("vision:no_api_key")
    content: list[dict] = [{"type": "text", "text": prompt}]
    for media_type, data in images:
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )
    try:
        resp = await _client(base_url, api_key).messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:  # SDK / network / API error
        raise LLMError(f"vision:{type(e).__name__}") from e
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    if not text:
        raise LLMError("vision:empty_response")
    return text


async def text_complete(
    *,
    prompt: str,
    system: str | None = None,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 400,
) -> str:
    """Send one text-only user message (with an optional system prompt) and return
    the text. Mirrors `vision_complete` for plain chat/completion work (e.g. the
    My Stats coach). Raises LLMError on transport/SDK failure or an empty response.
    NEVER pass an Anthropic OAuth token (CLAUDE.md anti-pattern #1)."""
    if not api_key:
        raise LLMError("text:no_api_key")
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    if system:
        kwargs["system"] = system
    try:
        resp = await _client(base_url, api_key).messages.create(**kwargs)
    except Exception as e:  # SDK / network / API error
        raise LLMError(f"text:{type(e).__name__}") from e
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    if not text:
        raise LLMError("text:empty_response")
    return text


async def chat_complete(
    *,
    messages: list[dict],
    system: str | None = None,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 500,
) -> str:
    """Multi-turn chat completion. ``messages`` is an ordered list of
    ``{"role": "user"|"assistant", "content": "<text>"}`` turns (plain-string
    content is wrapped into the anthropic text block shape). Returns the model's
    text reply. Mirrors ``text_complete`` but keeps conversation history. Raises
    LLMError on transport/SDK failure or an empty response. NEVER pass an
    Anthropic OAuth token (CLAUDE.md anti-pattern #1)."""
    if not api_key:
        raise LLMError("chat:no_api_key")
    norm: list[dict] = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        norm.append({"role": m["role"], "content": content})
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": norm}
    if system:
        kwargs["system"] = system
    try:
        resp = await _client(base_url, api_key).messages.create(**kwargs)
    except Exception as e:  # SDK / network / API error
        raise LLMError(f"chat:{type(e).__name__}") from e
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    if not text:
        raise LLMError("chat:empty_response")
    return text


def providers() -> list[tuple[str, str, str]]:
    """Ordered ``(model, base_url, api_key)`` triples for the configured LLM
    chain (primary → fallback), skipping any provider with no API key. Shared by
    every text/chat feature so callers never import a private helper."""
    s = get_settings()
    by_name = {
        "kimi": (s.KIMI_MODEL, s.KIMI_BASE_URL, s.KIMI_API_KEY),
        "minimax": (s.MINIMAX_MODEL, s.MINIMAX_BASE_URL, s.MINIMAX_API_KEY),
    }
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name in (s.LLM_PRIMARY, s.LLM_FALLBACK):
        key = (name or "").strip().lower()
        if key in by_name and key not in seen:
            seen.add(key)
            triple = by_name[key]
            if triple[2]:  # has an api key
                out.append(triple)
    return out


async def minimax_vlm_understand(
    *,
    host: str,
    api_key: str,
    prompt: str,
    image_data_url: str,
    timeout: float | None = None,
) -> str:
    """MiniMax Coding Plan vision tool: POST {host}/v1/coding_plan/vlm with one
    image (base64 data URL) + a prompt; returns the text `content`. This is the
    MiniMax-native API (not anthropic): Bearer auth, `base_resp.status_code` for
    errors. One image per call — callers merge multiple images. Raises LLMError.
    """
    import httpx

    if not api_key:
        raise LLMError("vlm:no_api_key")
    to = timeout if timeout is not None else get_settings().LLM_TIMEOUT_SECONDS
    try:
        async with httpx.AsyncClient(timeout=to) as http:
            r = await http.post(
                f"{host}/v1/coding_plan/vlm",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"prompt": prompt, "image_url": image_data_url},
            )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        # Any transport failure (HTTP, JSON, or a raw TLS/SSL glitch like
        # SSLV3_ALERT_BAD_RECORD_MAC that httpx doesn't wrap) → one LLMError the
        # caller can retry/degrade on. Never let a network error escape raw.
        raise LLMError(f"vlm:{type(e).__name__}") from e
    base = data.get("base_resp", {})
    if base.get("status_code") not in (0, None):
        raise LLMError(f"vlm:{base.get('status_code')}:{base.get('status_msg')}")
    text = (data.get("content") or "").strip()
    if not text:
        raise LLMError("vlm:empty_response")
    return text
