"""Signed short-lived OAuth state (CSRF) for the calendar connect flow."""
import os
import time

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")

from app.services import auth  # noqa: E402


def test_round_trip():
    token = auth.sign_state({"tid": 7, "n": "abc"})
    payload = auth.verify_state(token)
    assert payload is not None
    assert payload["tid"] == 7
    assert payload["n"] == "abc"
    assert "exp" in payload


def test_tampered_rejected():
    token = auth.sign_state({"tid": 7})
    body, sig = token.rsplit(".", 1)
    forged = body + "." + ("A" * len(sig))
    assert auth.verify_state(forged) is None


def test_payload_tamper_rejected():
    """Changing the payload without re-signing must fail (sig mismatch)."""
    token = auth.sign_state({"tid": 7})
    _, sig = token.rsplit(".", 1)
    import base64
    import json

    forged_body = base64.urlsafe_b64encode(
        json.dumps({"tid": 999, "exp": int(time.time()) + 600}).encode()
    ).decode().rstrip("=")
    assert auth.verify_state(f"{forged_body}.{sig}") is None


def test_expired_rejected():
    token = auth.sign_state({"tid": 7}, ttl_seconds=-1)
    assert auth.verify_state(token) is None


def test_garbage_rejected():
    assert auth.verify_state(None) is None
    assert auth.verify_state("") is None
    assert auth.verify_state("no-dot") is None
