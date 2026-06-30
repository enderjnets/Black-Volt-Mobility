"""Smart reservation extraction tests (SIMULATED — no vision/network calls)."""
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


def _live(monkeypatch, mapping: dict[bytes, dict | None]):
    """Switch the service to the live coding-VLM path with a per-image canned
    result keyed by the raw image bytes (so tests drive grouping deterministically
    without any network)."""
    s = get_settings()
    monkeypatch.setattr(s, "SMART_SIMULATED", False)
    monkeypatch.setattr(s, "SMART_VISION_API_KEY", "k")
    monkeypatch.setattr(s, "SMART_VISION_PROVIDER", "minimax_coding_vlm")

    async def fake_one(media_type, raw, attempts=2):
        return mapping.get(raw)

    monkeypatch.setattr(smart, "_vlm_one", fake_one)


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


# ─── Grouping (live path, mocked per-image VLM) ────────────────────────────────
@pytest.mark.asyncio
async def test_group_two_clients_split(monkeypatch):
    _live(
        monkeypatch,
        {
            b"a": smart._coerce({"name": "Ana", "pickup": "Hotel A", "date": "Jun 14"}),
            b"b": smart._coerce({"name": "Bob", "pickup": "Hotel B", "date": "Jun 15"}),
        },
    )
    out = await smart.extract_reservation([("image/png", b"a"), ("image/png", b"b")])
    assert len(out) == 2
    assert {r["name"] for r in out} == {"Ana", "Bob"}


@pytest.mark.asyncio
async def test_group_same_name_merges(monkeypatch):
    _live(
        monkeypatch,
        {
            b"1": smart._coerce({"name": "Ana", "pickup": "Hotel A"}),
            b"2": smart._coerce({"name": "Ana", "date": "Jun 14", "time": "06:30"}),
        },
    )
    out = await smart.extract_reservation([("image/png", b"1"), ("image/png", b"2")])
    assert len(out) == 1
    assert out[0]["name"] == "Ana"
    assert out[0]["pickup"] == "Hotel A"
    assert out[0]["time"] == "06:30"


@pytest.mark.asyncio
async def test_group_keyless_continuation_merges(monkeypatch):
    """A follow-up bubble with no name/phone continues the most recent reservation."""
    _live(
        monkeypatch,
        {
            b"1": smart._coerce({"name": "Ana", "pickup": "Hotel A"}),
            b"2": smart._coerce({"time": "07:15", "passengers": 3}),
        },
    )
    out = await smart.extract_reservation([("image/png", b"1"), ("image/png", b"2")])
    assert len(out) == 1
    assert out[0]["name"] == "Ana"
    assert out[0]["time"] == "07:15"
    assert out[0]["passengers"] == 3


@pytest.mark.asyncio
async def test_group_same_phone_merges_despite_name_variation(monkeypatch):
    _live(
        monkeypatch,
        {
            b"1": smart._coerce({"name": "Ana", "phone": "+1 303 555 0100", "pickup": "Hotel A"}),
            b"2": smart._coerce({"name": "Ana G.", "phone": "(303) 555-0100", "time": "06:30"}),
        },
    )
    out = await smart.extract_reservation([("image/png", b"1"), ("image/png", b"2")])
    assert len(out) == 1
    assert out[0]["pickup"] == "Hotel A"
    assert out[0]["time"] == "06:30"


@pytest.mark.asyncio
async def test_merge_flag_forces_single_reservation(monkeypatch):
    _live(
        monkeypatch,
        {
            b"a": smart._coerce({"name": "Ana", "pickup": "Hotel A"}),
            b"b": smart._coerce({"name": "Bob", "dropoff": "Denver Intl (DEN)"}),
        },
    )
    out = await smart.extract_reservation(
        [("image/png", b"a"), ("image/png", b"b")], merge=True
    )
    assert len(out) == 1
    assert out[0]["name"] == "Bob"  # later overrides earlier
    assert out[0]["pickup"] == "Hotel A"
    assert out[0]["dropoff"] == "Denver Intl (DEN)"


@pytest.mark.asyncio
async def test_all_images_failed_returns_empty(monkeypatch):
    _live(monkeypatch, {})  # every image → None
    out = await smart.extract_reservation([("image/png", b"x"), ("image/png", b"y")])
    assert out == []


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
