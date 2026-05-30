"""Pure unit tests for the HMAC session token (no DB needed)."""
import os

os.environ.setdefault("AUTH_SECRET", "unit-test-secret")

from app.config import get_settings  # noqa: E402
from app.services import auth  # noqa: E402

get_settings.cache_clear()


def test_token_roundtrip_owner():
    tok = auth.make_token(role=auth.ROLE_OWNER, tenant_id=1)
    p = auth.decode_token(tok)
    assert p is not None
    assert p["role"] == auth.ROLE_OWNER
    assert p["tid"] == 1
    assert p["sub"] == "blackvolt"


def test_token_roundtrip_passenger():
    tok = auth.make_token(role=auth.ROLE_PASSENGER, tenant_id=3, email="a@b.com", client_id=42)
    p = auth.decode_token(tok)
    assert p["role"] == auth.ROLE_PASSENGER
    assert p["email"] == "a@b.com"
    assert p["cid"] == 42


def test_tampered_token_rejected():
    tok = auth.make_token(role=auth.ROLE_OWNER, tenant_id=1)
    body, sig = tok.rsplit(".", 1)
    assert auth.decode_token(body + ".deadbeef") is None
    assert auth.decode_token(None) is None
    assert auth.decode_token("garbage") is None


def test_expired_token_rejected():
    tok = auth.make_token(role=auth.ROLE_OWNER, tenant_id=1, ttl_hours=-1)
    assert auth.decode_token(tok) is None


def test_check_password(monkeypatch):
    monkeypatch.setattr(get_settings(), "DASHBOARD_PASSWORD", "s3cret", raising=False)
    assert auth.check_password("s3cret") is True
    assert auth.check_password("nope") is False
