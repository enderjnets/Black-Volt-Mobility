"""Smart reservation: read screenshots of a client's message → reservation fields.

Two modes (settings.smart_live):
- **Live** — MiniMax-M3 vision. Two provider paths:
  - `minimax_coding_vlm` (product default): the VLM accepts ONE image per call, so
    extracting per image left the model blind to the rest of the conversation — a
    lone contact card can't say whether its address is the pickup or the dropoff,
    and it guessed differently every run. Instead each image is TRANSCRIBED
    (concurrent, one call each — a deterministic task the VLM is reliable at) and
    a single text call then extracts reservations from all transcripts TOGETHER,
    grouping by client itself. `merge=True` forces one reservation.
  - `minimax_anthropic`: all images in one vision call (already whole-context).
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
    '- "flight": the flight CODE only — airline IATA letters + FLIGHT NUMBER, e.g. '
    '"UA 2766". If the text names an airline but NO flight number ("United", "flying '
    'United", "on Southwest"), "flight" is null and the airline goes in "notes" — '
    "NEVER return an airline code or name without its number.\n"
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


# ── two-step pipeline (coding-VLM path) ───────────────────────────────────────
# A transcript is short by nature; the cap only stops a runaway response from
# blowing up step 2's prompt (6 images x 6k chars still fits comfortably).
_MAX_TRANSCRIPT_CHARS = 6000
_STEP2_MAX_TOKENS = 1600  # several reservations of JSON, with headroom

# Step 1 asks the VLM only to TRANSCRIBE. Extraction from a single image forced it
# to guess a whole trip's shape from one bubble; transcription has one right answer.
TRANSCRIBE_PROMPT = (
    "Transcribe this screenshot for a human reader. It is a phone or computer "
    "capture related to a ride request — SMS, WhatsApp, iMessage, email, a contact "
    "card, a flight itinerary, or typed notes.\n"
    "Output plain text, no JSON, no markdown fences, in this shape:\n"
    "KIND: <one of chat / contact-card / email / itinerary / notes / other>\n"
    "TITLE: <the contact name or thread/screen title at the very top, or none>\n"
    "TEXT:\n"
    "<every piece of readable text, VERBATIM, in top-to-bottom order. Keep phone "
    "numbers, addresses, ZIP codes, dates, times, flight codes and prices EXACTLY "
    "as written — never reformat or correct them. Prefix each chat bubble with who "
    "sent it when the layout makes that clear: 'THEM:' for the customer (incoming, "
    "usually left) and 'ME:' for the driver (outgoing, usually right). Skip only "
    "the phone status bar and app navigation chrome.>\n"
    "Transcribe what is actually visible. Never invent or complete missing text."
)

# Step 2 turns ALL transcripts into reservations in ONE text call, so the model can
# see the whole conversation before deciding which address is which end of the trip.
_MULTI_RULES = (
    "The transcripts below come from screenshots the driver uploaded together, in "
    "upload order. They may cover ONE customer or SEVERAL different customers.\n"
    "Group them yourself: transcripts about the same customer (same name, phone, or "
    "an obvious continuation of the same thread) belong to ONE reservation; a "
    "clearly different customer is a SEPARATE reservation. A contact card or an "
    "itinerary with no conversation of its own belongs to the customer it names, or "
    "to the neighbouring conversation when it names nobody new.\n"
    "Return ONLY this JSON — no prose, no markdown fences:\n"
    '{"reservations": [ <one reservation object per customer, in the order they '
    "first appear> ]}\n"
)
_MERGE_RULES = (
    "The transcripts below all come from screenshots of ONE single reservation for "
    "ONE customer, in upload order. Combine them into exactly one reservation "
    "(later messages override earlier ones).\n"
    "Return ONLY this JSON — no prose, no markdown fences:\n"
    '{"reservations": [ <exactly one reservation object> ]}\n'
)
# The address-placement rule is the whole reason this step exists: it is decidable
# only with every transcript in view.
_CONTEXT_RULES = (
    "\nDeciding pickup vs dropoff — read the CONVERSATION, never the layout:\n"
    "- An address that appears alone (a contact card, a saved address, a signature) "
    "is one END of the trip, but WHICH end is stated only in the conversation. If "
    "the customer is being picked up at an airport/hotel, that lone address is the "
    "dropoff; if they are being taken TO the airport, it is the pickup.\n"
    "- Prefer a concrete street address over a vague reference to the same place: "
    'if the conversation says "her house" / "mi casa" and another transcript shows '
    "that customer's street address, use the street address for that end of the "
    "trip. Keep a vague reference in \"notes\" instead of as pickup/dropoff — never "
    "put a vague phrase in a field when a real address is available.\n"
    "- Use ONLY text present in the transcripts. If a detail was never written, the "
    "value is null. NEVER invent an address, phone, date, time or price.\n"
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
        s = str(flight).strip()[:40]
        # An airline with no number ("United", "UA") is not a flight — the form field
        # expects a code the driver can track. Belt-and-braces for the prompt rule.
        out["flight"] = s if any(ch.isdigit() for ch in s) else None
    return out


def _parse_json(text: str) -> dict:
    """Extract the first {...} object from a model response (it may wrap prose)."""
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no_json_object")
    return json.loads(text[a : b + 1])


def _parse_reservations(text: str) -> list[dict]:
    """Parse step 2's answer into a list of coerced reservations. Accepts the asked
    shape {"reservations": [...]}, a bare list, or a single reservation object (small
    models drop the wrapper), and tolerates prose/fences around the JSON."""
    obj = _parse_json(text)
    items = obj.get("reservations") if isinstance(obj, dict) else None
    if items is None:
        items = [obj]  # bare reservation object
    if isinstance(items, dict):  # {"reservations": {...}} — single, unwrapped
        items = [items]
    if not isinstance(items, list):
        raise ValueError("reservations_not_a_list")
    out = [_coerce(it) for it in items if isinstance(it, dict)]
    return [r for r in out if any(_has(v) for v in r.values())]


def _has(v) -> bool:
    return v is not None and str(v).strip() != ""


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


async def _vlm_transcribe_one(media_type: str, raw: bytes, attempts: int = 2) -> str | None:
    """Step 1: transcribe one image via the coding-plan VLM, retrying transient
    failures (the endpoint is slow and occasionally returns a system error).
    Returns the transcript text, or None if every attempt failed."""
    import base64

    settings = get_settings()
    data_url = f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            text = await llm.minimax_vlm_understand(
                host=settings.SMART_VISION_HOST,
                api_key=settings.SMART_VISION_API_KEY,
                prompt=TRANSCRIBE_PROMPT,
                image_data_url=data_url,
                timeout=settings.SMART_VISION_TIMEOUT,
            )
            logger.info("vlm content (%d bytes img): %s", len(raw), (text or "")[:300])
            text = (text or "").strip()
            if text:
                return text[:_MAX_TRANSCRIPT_CHARS]
            last = ValueError("empty_transcript")
        except Exception as e:  # transient TLS/network/parse → retry, then skip
            last = e
    logger.warning("vlm image skipped after retries: %s", last)
    return None


def _step2_prompt(transcripts: list[str], *, merge: bool) -> str:
    """Build step 2's prompt: the extraction contract + whole-conversation rules +
    every transcript, labelled by upload order so the model can reason about them."""
    body = "\n\n".join(
        f"--- Image {i} transcript ---\n{t}" for i, t in enumerate(transcripts, 1)
    )
    rules = _MERGE_RULES if merge else _MULTI_RULES
    return (
        f"{_prompt()}\n\n{rules}{_CONTEXT_RULES}\n"
        f"Each reservation object has EXACTLY the keys described above.\n\n{body}"
    )


async def _extract_from_transcripts(transcripts: list[str], *, merge: bool) -> list[dict]:
    """Step 2: ONE text call over ALL transcripts (Kimi primary, MiniMax fallback —
    the same provider chain the rest of the product uses). Raises LLMError when no
    provider produced a parsable answer, so the caller degrades to []."""
    prompt = _step2_prompt(transcripts, merge=merge)
    last: Exception | None = None
    for model, base_url, api_key in llm.providers():
        try:
            text = await llm.text_complete(
                prompt=prompt,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=_STEP2_MAX_TOKENS,
                timeout=get_settings().SMART_VISION_TIMEOUT,
            )
            logger.info("smart step2 (%d transcripts): %s", len(transcripts), text[:400])
            out = _parse_reservations(text)
            if out:
                return out
            last = ValueError("no_reservations")
        except Exception as e:  # provider/transport/parse → try the next provider
            last = e
    raise llm.LLMError(f"smart:step2_failed:{last}")


async def _extract_coding_vlm(
    images: list[tuple[str, bytes]], *, merge: bool
) -> list[dict]:
    """MiniMax Coding Plan VLM, two steps: transcribe each image (concurrent, one
    call per image — the endpoint takes only one) then extract reservations from all
    transcripts in a SINGLE text call. A single image failing is skipped, not fatal,
    so partial input still yields fields."""
    import asyncio

    results = await asyncio.gather(
        *(_vlm_transcribe_one(mt, raw) for mt, raw in images), return_exceptions=True
    )
    transcripts = [t for t in results if isinstance(t, str) and t.strip()]
    if not transcripts:
        raise llm.LLMError("vlm:all_images_failed")
    groups = await _extract_from_transcripts(transcripts, merge=merge)
    if merge and len(groups) > 1:  # contract says one; collapse defensively
        groups = _merge_all(groups)
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
