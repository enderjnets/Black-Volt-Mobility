"""Smart reservation: read screenshots of a client's message → reservation fields.

Two modes (settings.smart_live):
- **Live** — MiniMax-M3 vision via `llm.vision_complete`. Screenshots are read one
  per call (concurrent) and then GROUPED by client (name/phone): bubbles from the
  same client/thread merge into one reservation, different clients split into
  separate reservations. Pass `merge=True` to force everything into a single
  reservation (used when filling one existing ride).
- **Simulated** — default; returns a deterministic sample so the Smart tab works
  end-to-end without a vision key/billing. Extraction is best-effort: any failure
  degrades to an empty result (the UI then asks the driver to fill it by hand).
"""
from __future__ import annotations

import json
import logging
import re

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
    "premium chauffeur / airport-transfer service in Denver. The screenshots are "
    "phone or computer captures of SMS, WhatsApp, iMessage, email, or typed notes "
    "— they may include a status bar, app chrome, timestamps, contact names, and "
    "several chat bubbles. IGNORE the app UI and focus on the customer's message "
    "text. When several images are given, they are ONE conversation with the SAME "
    "customer — combine them into a SINGLE reservation (later messages override "
    "earlier ones). Read carefully and extract whatever details you can actually "
    "see; partial results are expected.\n"
    "Return ONLY a JSON object — no prose, no markdown fences, nothing else — with "
    "EXACTLY these keys, using null ONLY when that detail is truly not present:\n"
    '{"name": string|null, "phone": string|null, "lang": "EN"|"ES"|null, '
    '"pickup": string|null, "dropoff": string|null, "date": string|null, '
    '"time": string|null, "flight": string|null, "passengers": number|null, '
    '"fare": number|null, "notes": string|null}\n'
    "Notes:\n"
    '- "name": the customer name (often the chat/contact title at the top).\n'
    '- "lang": EXACTLY "EN" or "ES" (the two-letter code only), guessed from the '
    "language the customer wrote in.\n"
    '- "flight": the flight CODE only — airline IATA + number, e.g. "UA 2766" — '
    "NOT the airline's full name.\n"
    '- "date"/"time": keep them short and human (e.g. "Jun 14", "06:30"). 24h time.\n'
    '- "fare": numeric dollars only if explicitly stated, else null.\n'
    '- Denver International should be normalized to "Denver Intl (DEN)".'
)


def _prompt() -> str:
    """EXTRACT_PROMPT anchored to today's date (driver timezone) so the model
    resolves relative dates and the PICKUP date, instead of grabbing a date from
    a flight itinerary or guessing the wrong month/year."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        today = datetime.now(ZoneInfo(get_settings().CALENDAR_TIMEZONE))
    except Exception:  # bad tz name → UTC
        from datetime import UTC

        today = datetime.now(UTC)
    ds = f"{today:%A}, {today:%b} {today.day} {today.year}"
    return (
        EXTRACT_PROMPT
        + f"\n- TODAY is {ds}. The \"date\" is the customer's PICKUP date — NOT a "
        "flight departure/return date in an itinerary. Resolve relative dates "
        '("today"/"hoy", "tomorrow"/"mañana", weekday names like "Friday"/'
        '"viernes") against TODAY. If only a day-of-month is given, choose the '
        "nearest such date that is today or in the future."
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
    """Keep only the canonical keys; normalize the two that hit backend limits so
    real/AI data never 422s downstream: lang → EN|ES, flight ≤ 40 chars. Unknown
    keys are dropped; the rest pass through (the frontend stringifies/validates)."""
    out = {k: obj.get(k) for k in RESERVATION_KEYS}
    lang = out.get("lang")
    if lang is not None:
        s = str(lang).strip().lower()
        out["lang"] = ("ES" if s.startswith(("es", "sp")) else "EN") if s else None
    flight = out.get("flight")
    if flight is not None:
        out["flight"] = str(flight).strip()[:40] or None
    return out


def _parse_json(text: str) -> dict:
    """Extract the first {...} object from a model response (it may wrap prose)."""
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no_json_object")
    return json.loads(text[a : b + 1])


def _has(v) -> bool:
    return v is not None and str(v).strip() != ""


def _client_key(d: dict) -> str | None:
    """Identity used to decide which images belong to the same reservation. Phone
    wins (most reliable — normalized to its last 10 digits); else the lowercased
    name; else None (a key-less continuation bubble)."""
    phone = d.get("phone")
    if _has(phone):
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) >= 7:
            return "p:" + digits[-10:]
    name = d.get("name")
    if _has(name):
        return "n:" + " ".join(str(name).split()).lower()
    return None


def _empty() -> dict:
    return {k: None for k in RESERVATION_KEYS}


def _merge_into(target: dict, fields: dict) -> None:
    """Merge fields into target in place; later (present) values override earlier."""
    for k, v in fields.items():
        if k in target and _has(v):
            target[k] = v


def _merge_all(dicts: list[dict]) -> list[dict]:
    """Collapse every image into ONE reservation (merge=True path / RideDetail)."""
    merged = _empty()
    for fields in dicts:
        _merge_into(merged, fields)
    return [merged]


def _group_by_client(dicts: list[dict]) -> list[dict]:
    """Group per-image results (in image order) into distinct reservations: same
    client key → same reservation; a new key → a new reservation; a key-less
    image continues the most recent reservation (e.g. a follow-up bubble that
    repeats no name). Empty results are dropped."""
    groups: list[dict] = []
    keys: list[str | None] = []
    for fields in dicts:
        if not any(_has(v) for v in fields.values()):
            continue
        key = _client_key(fields)
        idx: int | None = None
        if key is not None:
            for i, k in enumerate(keys):
                if k == key:
                    idx = i
                    break
        if idx is None:
            if key is None and groups:  # key-less continuation → latest group
                idx = len(groups) - 1
            else:
                groups.append(_empty())
                keys.append(key)
                idx = len(groups) - 1
        _merge_into(groups[idx], fields)
        if keys[idx] is None and key is not None:  # group adopts the first key it sees
            keys[idx] = key
    return groups


async def _extract_anthropic(images: list[tuple[str, bytes]]) -> list[dict]:
    """MiniMax-M3 over the anthropic endpoint: all images in one call. This path
    always yields a single merged reservation (grouping lives in the coding-VLM
    product path)."""
    import base64

    settings = get_settings()
    payload = [(mt, base64.b64encode(raw).decode("ascii")) for mt, raw in images]
    text = await llm.vision_complete(
        prompt=_prompt(),
        images=payload,
        model=settings.SMART_VISION_MODEL,
        base_url=settings.SMART_VISION_BASE_URL,
        api_key=settings.SMART_VISION_API_KEY,
        max_tokens=1024,
    )
    return [_coerce(_parse_json(text))]


async def _vlm_one(media_type: str, raw: bytes, attempts: int = 2) -> dict | None:
    """Extract one image via the coding-plan VLM, retrying transient failures
    (the endpoint is slow and occasionally returns a system error). Returns the
    coerced fields, or None if every attempt failed."""
    import base64

    settings = get_settings()
    data_url = f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            text = await llm.minimax_vlm_understand(
                host=settings.SMART_VISION_HOST,
                api_key=settings.SMART_VISION_API_KEY,
                prompt=_prompt(),
                image_data_url=data_url,
                timeout=settings.SMART_VISION_TIMEOUT,
            )
            logger.info("vlm content (%d bytes img): %s", len(raw), (text or "")[:300])
            return _coerce(_parse_json(text))
        except Exception as e:  # transient TLS/network/parse → retry, then skip
            last = e
    logger.warning("vlm image skipped after retries: %s", last)
    return None


async def _extract_coding_vlm(
    images: list[tuple[str, bytes]], *, merge: bool
) -> list[dict]:
    """MiniMax Coding Plan VLM: one (concurrent) call per image. A single image
    failing is skipped, not fatal, so partial input still yields fields. Results
    are then grouped by client into one or more reservations (or all into one
    when `merge`)."""
    import asyncio

    results = await asyncio.gather(
        *(_vlm_one(mt, raw) for mt, raw in images), return_exceptions=True
    )
    valid = [f for f in results if isinstance(f, dict)]
    if not valid and images:
        raise llm.LLMError("vlm:all_images_failed")
    if merge:
        return _merge_all(valid)
    groups = _group_by_client(valid)
    if not groups:
        logger.warning("vlm returned no fields from %d image(s)", len(images))
    return groups


async def extract_reservation(
    images: list[tuple[str, bytes]], *, merge: bool = False
) -> list[dict]:
    """Read screenshots → a LIST of reservations. `images` is (media_type, raw_bytes).

    Best-effort: returns canonical-key dicts (values may be null). With `merge`
    every image is collapsed into a single reservation. In simulated mode returns
    one SAMPLE_EXTRACTION; on a live failure returns [] so the caller can prompt
    for manual entry."""
    settings = get_settings()
    if not settings.smart_live:
        return [_coerce(dict(SAMPLE_EXTRACTION))]
    try:
        if settings.SMART_VISION_PROVIDER == "minimax_anthropic":
            return await _extract_anthropic(images)
        return await _extract_coding_vlm(images, merge=merge)
    except Exception as e:  # safety net — extraction must never 500 the endpoint
        logger.warning("smart extract failed: %s", e)
        return []
