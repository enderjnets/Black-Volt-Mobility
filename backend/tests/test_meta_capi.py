"""Meta Conversions API service — hashing, gating, and payload shape (no network)."""
import hashlib
from types import SimpleNamespace

import pytest

from app.services import meta_capi


def _sha(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def test_purchase_event_id_matches_backend_contract():
    assert meta_capi.purchase_event_id(42) == "purchase_42"


def test_email_hashing_normalizes_and_rejects_junk():
    assert meta_capi._hash_email("  Ender@Example.COM ") == _sha("ender@example.com")
    assert meta_capi._hash_email("not-an-email") is None
    assert meta_capi._hash_email("") is None
    assert meta_capi._hash_email(None) is None


def test_phone_hashing_adds_country_code_for_bare_us_number():
    assert meta_capi._hash_phone("(720) 594-6249") == _sha("17205946249")
    assert meta_capi._hash_phone("+1 720 594 6249") == _sha("17205946249")
    assert meta_capi._hash_phone("") is None


def _fake_settings(**over):
    base = dict(
        META_CAPI_ENABLED=True,
        META_CAPI_SIMULATED=False,
        META_PIXEL_ID="PIX123",
        META_CAPI_ACCESS_TOKEN="tok",
        META_GRAPH_VERSION="v21.0",
        META_TEST_EVENT_CODE="",
    )
    base.update(over)
    s = SimpleNamespace(**base)
    s.capi_live = bool(
        s.META_CAPI_ENABLED
        and not s.META_CAPI_SIMULATED
        and s.META_PIXEL_ID
        and s.META_CAPI_ACCESS_TOKEN
    )
    return s


class _FakeResp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "{}"


class _FakeClient:
    """Captures the single POST so the test can assert on the payload."""

    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        _FakeClient.calls.append({"url": url, "json": json})
        return _FakeResp(200)


@pytest.mark.asyncio
async def test_no_op_when_not_live(monkeypatch):
    monkeypatch.setattr(meta_capi, "get_settings", lambda: _fake_settings(META_CAPI_ENABLED=False))
    _FakeClient.calls = []
    monkeypatch.setattr(meta_capi.httpx, "AsyncClient", _FakeClient)
    out = await meta_capi.send_purchase(ride_id=1, event_time=100, value=120.0, email="a@b.com")
    assert out == {"sent": False, "simulated": True}
    assert _FakeClient.calls == []


@pytest.mark.asyncio
async def test_skips_when_no_user_data(monkeypatch):
    monkeypatch.setattr(meta_capi, "get_settings", _fake_settings)
    _FakeClient.calls = []
    monkeypatch.setattr(meta_capi.httpx, "AsyncClient", _FakeClient)
    out = await meta_capi.send_purchase(ride_id=1, event_time=100, value=120.0)
    assert out["status"] == "no_user_data"
    assert _FakeClient.calls == []


@pytest.mark.asyncio
async def test_live_post_hashes_pii_and_sets_event_id(monkeypatch):
    monkeypatch.setattr(
        meta_capi, "get_settings", lambda: _fake_settings(META_TEST_EVENT_CODE="TEST42")
    )
    _FakeClient.calls = []
    monkeypatch.setattr(meta_capi.httpx, "AsyncClient", _FakeClient)

    out = await meta_capi.send_purchase(
        ride_id=99,
        event_time=1234,
        value=450.0,
        currency="usd",
        email="Ender@Example.com",
        phone="720-594-6249",
        first_name="Ender",
        last_name="Ocando",
        client_ip="203.0.113.7",
        user_agent="UA/1.0",
        fbp="fb.1.abc",
        fbc="fb.1.click",
    )
    assert out["sent"] is True
    assert len(_FakeClient.calls) == 1
    call = _FakeClient.calls[0]

    assert call["url"] == "https://graph.facebook.com/v21.0/PIX123/events"
    # Token travels in the body, never the URL/query.
    assert call["json"]["access_token"] == "tok"
    assert "access_token" not in call["url"]

    ev = call["json"]["data"][0]
    assert ev["event_name"] == "Purchase"
    assert ev["event_id"] == "purchase_99"
    assert ev["action_source"] == "website"
    assert ev["custom_data"] == {"currency": "USD", "value": 450.0}
    assert call["json"]["test_event_code"] == "TEST42"

    ud = ev["user_data"]
    # Raw PII must never appear; only SHA-256 hashes.
    blob = str(ud)
    assert "Ender@Example.com".lower() not in blob
    assert "7205946249" not in blob
    assert ud["em"] == [_sha("ender@example.com")]
    assert ud["ph"] == [_sha("17205946249")]
    assert ud["fn"] == [_sha("ender")]
    assert ud["ln"] == [_sha("ocando")]
    # IP/UA/fbp/fbc are sent raw (Meta matches them un-hashed).
    assert ud["client_ip_address"] == "203.0.113.7"
    assert ud["client_user_agent"] == "UA/1.0"
    assert ud["fbp"] == "fb.1.abc"
    assert ud["fbc"] == "fb.1.click"


@pytest.mark.asyncio
async def test_http_error_is_swallowed(monkeypatch):
    class _Boom(_FakeClient):
        async def post(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(meta_capi, "get_settings", _fake_settings)
    monkeypatch.setattr(meta_capi.httpx, "AsyncClient", _Boom)
    out = await meta_capi.send_purchase(ride_id=1, event_time=100, value=10.0, email="a@b.com")
    assert out == {"sent": False, "simulated": False, "status": "error"}
