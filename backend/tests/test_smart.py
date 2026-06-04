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


@pytest.mark.asyncio
async def test_extract_simulated_returns_sample():
    out = await smart.extract_reservation([("image/png", _PNG)])
    assert set(out.keys()) == set(smart.RESERVATION_KEYS)
    assert out["pickup"] == smart.SAMPLE_EXTRACTION["pickup"]
    assert out["dropoff"] == "Denver Intl (DEN)"


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
    """A transient TLS/network error from the VLM must degrade to all-null, never
    crash the request (regression for SSLV3_ALERT_BAD_RECORD_MAC → 500)."""
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
    assert set(out.keys()) == set(smart.RESERVATION_KEYS)
    assert all(v is None for v in out.values())


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
    assert body["image_count"] == 1
    assert body["fields"]["dropoff"] == "Denver Intl (DEN)"


def test_endpoint_rejects_non_image():
    c = _owner()
    r = c.post("/api/v1/rides/extract", files={"files": ("note.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_endpoint_rejects_too_many_images():
    c = _owner()
    files = [("files", (f"s{i}.png", _PNG, "image/png")) for i in range(6)]
    r = c.post("/api/v1/rides/extract", files=files)
    assert r.status_code == 400
    assert "too_many" in r.json()["detail"]


def test_endpoint_accepts_multiple_images():
    c = _owner()
    files = [("files", (f"s{i}.png", _PNG, "image/png")) for i in range(3)]
    r = c.post("/api/v1/rides/extract", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["image_count"] == 3
