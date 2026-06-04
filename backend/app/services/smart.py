"""Smart reservation: read screenshots of a client's message → reservation fields.

Two modes (settings.smart_live):
- **Live** — MiniMax-M3 vision via `llm.vision_complete`. Multiple screenshots are
  treated as ONE conversation and merged into a single reservation.
- **Simulated** — default; returns a deterministic sample so the Smart tab works
  end-to-end without a vision key/billing. Extraction is best-effort: any failure
  degrades to an empty result (the UI then asks the driver to fill it by hand).
"""
from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.services import llm

logger = logging.getLogger("blackvolt.smart")

# Canonical reservation keys the form binds to (mirrors AddRide.tsx BV_BLANK).
RESERVATION_KEYS = (
    "name",
    "phone",
    "lang",
    "pickup",
    "dropoff",
    "date",
    "time",
    "flight",
    "passengers",
    "fare",
    "notes",
)

EXTRACT_PROMPT = (
    "You read screenshots of a customer ride request for Black Volt Mobility, a "
    "premium chauffeur / airport-transfer service in Denver. The screenshots may "
    "be SMS, WhatsApp, email, or typed notes. When several images are given, they "
    "are ONE conversation with the SAME customer — combine them into a SINGLE "
    "reservation (later messages override earlier ones).\n"
    "Return ONLY a JSON object — no prose, no markdown fences — with EXACTLY these "
    "keys, using null when the info is not present:\n"
    '{"name": string|null, "phone": string|null, "lang": "EN"|"ES"|null, '
    '"pickup": string|null, "dropoff": string|null, "date": string|null, '
    '"time": string|null, "flight": string|null, "passengers": number|null, '
    '"fare": number|null, "notes": string|null}\n'
    "Notes:\n"
    '- "lang": guess from the language the customer wrote in.\n'
    '- "date"/"time": keep them short and human (e.g. "Jun 14", "06:30"). 24h time.\n'
    '- "fare": numeric dollars only if explicitly stated, else null.\n'
    '- Denver International should be normalized to "Denver Intl (DEN)".'
)

# Returned when simulated (no vision key) so the Smart tab is demoable offline.
SAMPLE_EXTRACTION: dict = {
    "name": "Daniel Ortega",
    "phone": None,
    "lang": "ES",
    "pickup": "The Crawford Hotel",
    "dropoff": "Denver Intl (DEN)",
    "date": "Jun 14",
    "time": "06:30",
    "flight": "UA 1455",
    "passengers": 2,
    "fare": None,
    "notes": "2 maletas grandes",
}


def _coerce(obj: dict) -> dict:
    """Keep only the canonical keys; pass values through untouched (the frontend
    stringifies and validates). Unknown keys are dropped."""
    return {k: obj.get(k) for k in RESERVATION_KEYS}


def _parse_json(text: str) -> dict:
    """Extract the first {...} object from a model response (it may wrap prose)."""
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no_json_object")
    return json.loads(text[a : b + 1])


def _has(v) -> bool:
    return v is not None and str(v).strip() != ""


async def _extract_anthropic(images: list[tuple[str, bytes]]) -> dict:
    """MiniMax-M3 over the anthropic endpoint: all images in one call."""
    import base64

    settings = get_settings()
    payload = [(mt, base64.b64encode(raw).decode("ascii")) for mt, raw in images]
    text = await llm.vision_complete(
        prompt=EXTRACT_PROMPT,
        images=payload,
        model=settings.SMART_VISION_MODEL,
        base_url=settings.SMART_VISION_BASE_URL,
        api_key=settings.SMART_VISION_API_KEY,
        max_tokens=1024,
    )
    return _coerce(_parse_json(text))


async def _extract_coding_vlm(images: list[tuple[str, bytes]]) -> dict:
    """MiniMax Coding Plan VLM: one image per call, merged into one reservation
    (later images override earlier — newer messages win). A single image failing
    to read/parse is skipped, not fatal, so partial input still yields fields."""
    import base64

    settings = get_settings()
    merged: dict = {k: None for k in RESERVATION_KEYS}
    ok = 0
    for media_type, raw in images:
        b64 = base64.b64encode(raw).decode("ascii")
        data_url = f"data:{media_type};base64,{b64}"
        try:
            text = await llm.minimax_vlm_understand(
                host=settings.SMART_VISION_HOST,
                api_key=settings.SMART_VISION_API_KEY,
                prompt=EXTRACT_PROMPT,
                image_data_url=data_url,
                timeout=settings.SMART_VISION_TIMEOUT,
            )
            fields = _coerce(_parse_json(text))
        except (llm.LLMError, ValueError, json.JSONDecodeError) as e:
            logger.warning("vlm image skipped: %s", e)
            continue
        ok += 1
        for k, v in fields.items():
            if _has(v):
                merged[k] = v
    if ok == 0 and images:
        raise llm.LLMError("vlm:all_images_failed")
    return merged


async def extract_reservation(images: list[tuple[str, bytes]]) -> dict:
    """Read screenshots → reservation fields. `images` is (media_type, raw_bytes).

    Best-effort: returns the canonical-key dict (values may be null). In simulated
    mode returns SAMPLE_EXTRACTION; on a live failure returns all-null so the
    caller can prompt for manual entry."""
    settings = get_settings()
    if not settings.smart_live:
        return _coerce(dict(SAMPLE_EXTRACTION))
    try:
        if settings.SMART_VISION_PROVIDER == "minimax_anthropic":
            return await _extract_anthropic(images)
        return await _extract_coding_vlm(images)
    except (llm.LLMError, ValueError, json.JSONDecodeError) as e:
        logger.warning("smart extract failed: %s", e)
        return {k: None for k in RESERVATION_KEYS}
