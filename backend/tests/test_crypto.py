"""Encryption-at-rest for OAuth refresh tokens (Fernet, fail-closed)."""
import os

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import crypto  # noqa: E402


def _set_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(get_settings(), "CALENDAR_TOKEN_ENC_KEY", key, raising=False)
    return key


def test_round_trip(monkeypatch):
    _set_key(monkeypatch)
    secret = "1//0gRefreshTokenSecretValue-abc_DEF"
    enc = crypto.encrypt(secret)
    assert enc != secret  # actually transformed
    assert secret not in enc  # plaintext not embedded
    assert crypto.decrypt(enc) == secret


def test_encrypt_requires_key(monkeypatch):
    """Fail-closed: never persist a token in plaintext when no key is set."""
    monkeypatch.setattr(get_settings(), "CALENDAR_TOKEN_ENC_KEY", "", raising=False)
    with pytest.raises(crypto.CryptoError):
        crypto.encrypt("anything")


def test_decrypt_tampered_fails(monkeypatch):
    _set_key(monkeypatch)
    enc = crypto.encrypt("hello world")
    tampered = enc[:-3] + ("zzz" if not enc.endswith("zzz") else "aaa")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(tampered)


def test_decrypt_wrong_key_fails(monkeypatch):
    _set_key(monkeypatch)
    enc = crypto.encrypt("hello world")
    monkeypatch.setattr(
        get_settings(), "CALENDAR_TOKEN_ENC_KEY", Fernet.generate_key().decode("ascii"),
        raising=False,
    )
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(enc)


def test_invalid_key_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "CALENDAR_TOKEN_ENC_KEY", "not-a-valid-key", raising=False)
    with pytest.raises(crypto.CryptoError):
        crypto.encrypt("x")
