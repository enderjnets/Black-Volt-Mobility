"""Symmetric encryption for secrets at rest (OAuth refresh tokens).

Fernet (AES-128-CBC + HMAC-SHA256 authentication) keyed by
``settings.CALENDAR_TOKEN_ENC_KEY``. **Fail-closed**: encryption refuses to run
without a configured key, so a refresh token is never written in plaintext, and
decryption raises on any tamper / wrong-key / malformed input.
"""
from __future__ import annotations

from app.config import get_settings


class CryptoError(RuntimeError):
    """Raised when encryption/decryption cannot be performed safely."""


def _fernet():
    key = (get_settings().CALENDAR_TOKEN_ENC_KEY or "").strip()
    if not key:
        raise CryptoError("calendar_token_enc_key_missing")
    from cryptography.fernet import Fernet

    try:
        return Fernet(key.encode("utf-8"))
    except Exception as e:  # malformed / wrong-length key
        raise CryptoError(f"invalid_enc_key: {e}") from e


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string → urlsafe-base64 token. Raises CryptoError if no key."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a token produced by :func:`encrypt`. Raises CryptoError on any
    tamper, wrong key, or malformed input — callers must treat this as a hard
    failure (never fall back to plaintext)."""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except CryptoError:
        raise
    except (InvalidToken, Exception) as e:
        raise CryptoError("decrypt_failed") from e
