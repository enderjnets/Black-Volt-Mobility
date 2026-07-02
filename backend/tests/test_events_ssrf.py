"""SSRF guard on the event hero download — including per-redirect-hop validation."""

import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["SOCIAL_SIMULATED"] = "true"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.services import events  # noqa: E402


def test_is_safe_public_url_classifier():
    assert events._is_safe_public_url("file:///etc/passwd") is False
    assert events._is_safe_public_url("http://localhost/x") is False
    assert events._is_safe_public_url("http://127.0.0.1/x") is False
    assert events._is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False
    assert events._is_safe_public_url("http://10.0.0.5/x") is False
    assert events._is_safe_public_url("http://192.168.1.1/x") is False
    assert events._is_safe_public_url("not a url") is False
    assert events._is_safe_public_url("https://media.ticketmaster.com/img.jpg") is True


class _Resp:
    def __init__(self, *, redirect_to=None, content=b""):
        self.is_redirect = redirect_to is not None
        self.headers = {"location": redirect_to} if redirect_to else {}
        self.content = content
        self.url = "http://cdn.example/x"

    def raise_for_status(self):
        pass


@pytest.mark.asyncio
async def test_download_rejects_redirect_to_private_host(monkeypatch):
    # Entry URL is public, but it 302s to the cloud-metadata IP. The guard must validate
    # the redirect target BEFORE following it and abort → None (no bytes returned).
    checked: list[str] = []

    def fake_safe(url: str) -> bool:
        checked.append(url)
        return "169.254" not in url  # public entry ok; metadata target rejected

    monkeypatch.setattr(events, "_is_safe_public_url", fake_safe)

    async def fake_get(self, url):
        return _Resp(redirect_to="http://169.254.169.254/latest/meta-data/")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await events._download_image("http://cdn.example/img.jpg")
    assert out is None
    assert any("169.254" in c for c in checked)  # the redirect target was validated


@pytest.mark.asyncio
async def test_download_follows_safe_redirect_then_returns_image(monkeypatch):
    # A redirect to another PUBLIC host is followed, and a valid image is returned.
    _PNG = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d4944415478da6360000002000001e221bc330000000049454e44ae426082"
    )
    monkeypatch.setattr(events, "_is_safe_public_url", lambda url: True)
    seq = [
        _Resp(redirect_to="http://cdn2.example/final.png"),
        _Resp(content=_PNG),
    ]

    async def fake_get(self, url):
        return seq.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    out = await events._download_image("http://cdn.example/img.png")
    assert out is not None
    assert out[1] == "png"
