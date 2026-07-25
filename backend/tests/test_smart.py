"""Smart reservation extraction tests (SIMULATED — no vision/network calls)."""
import json
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["CALENDAR_SIMULATED"] = "true"

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import llm as llm_mod  # noqa: E402
from app.services import smart  # noqa: E402

# 1×1 transparent PNG.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _live(monkeypatch, mapping: dict[bytes, str | None], step2: str | Exception = ""):
    """Switch the service to the live two-step coding-VLM path without any network:
    `mapping` gives each image's step-1 transcript keyed by its raw bytes (None =
    that image failed), and `step2` is what the step-2 text call returns (or raises).
    Returns the list of prompts step 2 was called with, so tests can assert every
    transcript reached it."""
    s = get_settings()
    monkeypatch.setattr(s, "SMART_SIMULATED", False)
    monkeypatch.setattr(s, "SMART_VISION_API_KEY", "k")
    monkeypatch.setattr(s, "SMART_VISION_PROVIDER", "minimax_coding_vlm")

    async def fake_transcribe(media_type, raw, attempts=2):
        return mapping.get(raw)

    monkeypatch.setattr(smart, "_vlm_transcribe_one", fake_transcribe)

    seen: list[str] = []

    async def fake_text(**kw):
        seen.append(kw["prompt"])
        if isinstance(step2, Exception):
            raise step2
        return step2

    monkeypatch.setattr(llm_mod, "text_complete", fake_text)
    monkeypatch.setattr(
        llm_mod, "providers", lambda: [("m", "https://example.invalid", "k")]
    )
    return seen


@pytest.mark.asyncio
async def test_extract_simulated_returns_sample():
    out = await smart.extract_reservation([("image/png", _PNG)])
    assert isinstance(out, list) and len(out) == 1
    r = out[0]
    assert set(r.keys()) == set(smart.RESERVATION_KEYS)
    assert r["pickup"] == smart.SAMPLE_EXTRACTION["pickup"]
    assert r["dropoff"] == "Denver Intl (DEN)"


def test_parse_json_extracts_object():
    obj = smart._parse_json('Sure! {"name": "Ana", "pax": 2} done')
    assert obj == {"name": "Ana", "pax": 2}


def test_parse_json_raises_without_object():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        smart._parse_json("I cannot read this image, sorry.")


def test_coerce_empty_is_all_null():
    out = smart._coerce({})
    assert set(out.keys()) == set(smart.RESERVATION_KEYS)
    assert all(v is None for v in out.values())


@pytest.mark.asyncio
async def test_extract_survives_vlm_exception(monkeypatch):
    """A transient TLS/network error from the VLM must degrade to an empty list,
    never crash the request (regression for SSLV3_ALERT_BAD_RECORD_MAC → 500)."""
    import ssl

    from app.services import llm

    s = get_settings()
    monkeypatch.setattr(s, "SMART_SIMULATED", False)
    monkeypatch.setattr(s, "SMART_VISION_API_KEY", "k")
    monkeypatch.setattr(s, "SMART_VISION_PROVIDER", "minimax_coding_vlm")

    async def boom(**kw):
        raise ssl.SSLError("bad record mac")

    monkeypatch.setattr(llm, "minimax_vlm_understand", boom)
    out = await smart.extract_reservation([("image/png", b"x"), ("image/png", b"y")])
    assert out == []


# ─── Two-step pipeline (transcribe per image → extract with full context) ──────
def _res(**kw) -> str:
    """Step-2 style answer with one reservation object."""
    return json.dumps({"reservations": [kw]})


@pytest.mark.asyncio
async def test_step2_sees_every_transcript(monkeypatch):
    """The whole point of the two-step pipeline: ONE call carrying ALL transcripts,
    so the model can tell which end of the trip a lone address belongs to."""
    seen = _live(
        monkeypatch,
        {b"chat": "KIND: chat\nTEXT:\nTHEM: pick me up at DIA Friday 12:30",
         b"card": "KIND: contact-card\nTEXT:\nAna Ruiz\n7373 Old Mill Trail, 80301"},
        _res(name="Ana Ruiz", pickup="Denver Intl (DEN)", dropoff="7373 Old Mill Trail"),
    )
    out = await smart.extract_reservation([("image/png", b"chat"), ("image/png", b"card")])
    assert len(seen) == 1, "step 2 must be a single call, not one per image"
    assert "pick me up at DIA" in seen[0] and "7373 Old Mill Trail" in seen[0]
    assert "Image 1 transcript" in seen[0] and "Image 2 transcript" in seen[0]
    assert out[0]["pickup"] == "Denver Intl (DEN)"
    assert out[0]["dropoff"] == "7373 Old Mill Trail"


@pytest.mark.asyncio
async def test_model_grouping_two_clients(monkeypatch):
    """Grouping is the model's job now: two reservations come back as two."""
    _live(
        monkeypatch,
        {b"a": "KIND: chat\nTITLE: Ana\nTEXT:\nhotel A Jun 14",
         b"b": "KIND: chat\nTITLE: Bob\nTEXT:\nhotel B Jun 15"},
        json.dumps({"reservations": [
            {"name": "Ana", "pickup": "Hotel A", "date": "Jun 14"},
            {"name": "Bob", "pickup": "Hotel B", "date": "Jun 15"},
        ]}),
    )
    out = await smart.extract_reservation([("image/png", b"a"), ("image/png", b"b")])
    assert {r["name"] for r in out} == {"Ana", "Bob"}


@pytest.mark.asyncio
async def test_merge_flag_asks_for_one_and_collapses_extras(monkeypatch):
    """merge=True must yield exactly one reservation even if step 2 returns two."""
    seen = _live(
        monkeypatch,
        {b"a": "t1", b"b": "t2"},
        json.dumps({"reservations": [
            {"name": "Ana", "pickup": "Hotel A"},
            {"name": "Ana R.", "dropoff": "Denver Intl (DEN)"},
        ]}),
    )
    out = await smart.extract_reservation(
        [("image/png", b"a"), ("image/png", b"b")], merge=True
    )
    assert "ONE single reservation" in seen[0]
    assert len(out) == 1
    assert out[0]["pickup"] == "Hotel A"
    assert out[0]["dropoff"] == "Denver Intl (DEN)"
    assert out[0]["name"] == "Ana R."  # later overrides earlier


@pytest.mark.asyncio
async def test_failed_image_is_skipped_not_fatal(monkeypatch):
    """One unreadable screenshot must not sink the batch — the rest still extract."""
    seen = _live(
        monkeypatch,
        {b"ok": "KIND: chat\nTEXT:\nAna, DIA at 06:30", b"bad": None},
        _res(name="Ana", time="06:30"),
    )
    out = await smart.extract_reservation([("image/png", b"bad"), ("image/png", b"ok")])
    assert "Image 1 transcript" in seen[0]
    assert "Image 2 transcript" not in seen[0]  # only the readable one made it
    assert out[0]["name"] == "Ana"


@pytest.mark.asyncio
async def test_all_images_failed_returns_empty(monkeypatch):
    _live(monkeypatch, {}, _res(name="never"))  # every image → None
    out = await smart.extract_reservation([("image/png", b"x"), ("image/png", b"y")])
    assert out == []


@pytest.mark.asyncio
async def test_step2_failure_returns_empty(monkeypatch):
    """Step 2 dying (network/provider) degrades to [] so the UI asks for manual entry."""
    _live(monkeypatch, {b"x": "t"}, RuntimeError("provider down"))
    out = await smart.extract_reservation([("image/png", b"x")])
    assert out == []


@pytest.mark.asyncio
async def test_step2_unparsable_returns_empty(monkeypatch):
    _live(monkeypatch, {b"x": "t"}, "I could not read the screenshots, sorry.")
    out = await smart.extract_reservation([("image/png", b"x")])
    assert out == []


@pytest.mark.asyncio
async def test_step2_tolerates_prose_and_bare_object(monkeypatch):
    """Small models wrap JSON in prose and sometimes drop the "reservations" key."""
    _live(
        monkeypatch,
        {b"x": "t"},
        'Sure! Here you go:\n```json\n{"name": "Ana", "lang": "spanish"}\n```',
    )
    out = await smart.extract_reservation([("image/png", b"x")])
    assert len(out) == 1
    assert out[0]["name"] == "Ana"
    assert out[0]["lang"] == "ES"  # _coerce still normalizes each reservation


def test_parse_reservations_drops_empty_objects():
    out = smart._parse_reservations(
        json.dumps({"reservations": [{"name": "Ana"}, {"name": None}, {}]})
    )
    assert len(out) == 1 and out[0]["name"] == "Ana"


def test_parse_reservations_rejects_non_list():
    with pytest.raises(ValueError):
        smart._parse_reservations(json.dumps({"reservations": "Ana"}))


# ─── Endpoint ──────────────────────────────────────────────────────────────────
def test_endpoint_requires_staff():
    c = TestClient(app)  # no session
    r = c.post("/api/v1/rides/extract", files={"files": ("a.png", _PNG, "image/png")})
    assert r.status_code == 401


def test_endpoint_extracts_simulated():
    c = _owner()
    r = c.post("/api/v1/rides/extract", files={"files": ("sms.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True
    assert body["count"] == 1
    assert body["reservations"][0]["dropoff"] == "Denver Intl (DEN)"


def test_endpoint_rejects_non_image():
    c = _owner()
    r = c.post("/api/v1/rides/extract", files={"files": ("note.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_endpoint_rejects_too_many_images():
    c = _owner()
    n = get_settings().SMART_MAX_IMAGES + 1
    files = [("files", (f"s{i}.png", _PNG, "image/png")) for i in range(n)]
    r = c.post("/api/v1/rides/extract", files=files)
    assert r.status_code == 400
    assert "too_many" in r.json()["detail"]


def test_endpoint_accepts_max_images():
    c = _owner()
    n = get_settings().SMART_MAX_IMAGES
    files = [("files", (f"s{i}.png", _PNG, "image/png")) for i in range(n)]
    r = c.post("/api/v1/rides/extract", files=files)
    assert r.status_code == 200, r.text
    assert "reservations" in r.json()
