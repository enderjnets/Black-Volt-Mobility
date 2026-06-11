"""Square Subscriptions API in SIMULATED mode (no real Square calls).

The driver-subscribe endpoint is PUBLIC (a brand-new driver has no session yet),
so unlike the rides/payments tests these calls carry no auth cookie. Each case
uses a unique email so it never collides with rows left by earlier runs (the
suite runs against a long-lived dev database)."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
# A placeholder plan-variation id stands in for the real Square one while simulated.
os.environ["SQUARE_PLAN_OPERATOR_MONTHLY"] = "PLACEHOLDER_MONTHLY_VARIATION_ID"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _email() -> str:
    return f"driver-{uuid.uuid4().hex[:10]}@example.com"


def _subscribe(email: str, *, plan: str = "operator", source: str = "cnon:card-nonce-ok"):
    return client.post(
        "/api/v1/subscriptions",
        json={"plan_key": plan, "source_id": source, "email": email},
    )


def test_create_subscription_simulated():
    r = _subscribe(_email())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["simulated"] is True
    assert body["subscription_id"].startswith("SIMSUB-")


def test_invalid_plan_key_400():
    r = _subscribe(_email(), plan="bogus")
    assert r.status_code == 400, r.text


def test_idempotent_same_email_plan():
    """Subscribing twice with the same email+plan returns the SAME subscription —
    no duplicate is created."""
    email = _email()
    r1 = _subscribe(email)
    r2 = _subscribe(email)
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["subscription_id"] == r2.json()["subscription_id"]


def test_missing_email_422():
    r = client.post("/api/v1/subscriptions", json={"plan_key": "operator", "source_id": "x"})
    assert r.status_code == 422


def test_square_error_detail_is_sanitized(monkeypatch):
    """A Square failure must NOT leak the raw API body to the (anonymous) caller —
    only the stable public code. The full message is for server logs."""
    from app.services import subscriptions_square

    async def boom(*, email, idempotency_seed=None, **kw):
        raise subscriptions_square.SubscriptionError(
            "square_customer:400:SECRET-SQUARE-BODY", public_code="square_customer"
        )

    monkeypatch.setattr(subscriptions_square, "create_customer", boom)
    r = _subscribe(_email())
    assert r.status_code == 402, r.text
    assert r.json()["detail"] == "square_customer"
    assert "SECRET-SQUARE-BODY" not in r.text
