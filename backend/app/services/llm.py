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
