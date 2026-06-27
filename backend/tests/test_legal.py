"""Legal agreement tests. DB-backed — run with Postgres available.

DASHBOARD_PASSWORD is set at import (before app import) so conftest's session-start
data-reset fixture actually runs when this module is run on its own. The autouse
fixture below additionally pins this module's env and refreshes the settings cache
per test, so the shared settings singleton can't be contaminated by other modules."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ.setdefault("AUTH_SECRET", "api-test-secret")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("GOOGLE_ADMIN_EMAILS", "admin@bv.com")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.legal import (  # noqa: E402
    audience,
    current_version,
    is_known_doc,
    load_doc,
    normalize_lang,
)
from app.main import app  # noqa: E402
from app.services import auth as auth_service  # noqa: E402

client = TestClient(app)

_ENV = {
    "DASHBOARD_PASSWORD": "test-pw",
    "AUTH_SECRET": "api-test-secret",
    "AUTH_ENABLED": "true",
    "GOOGLE_ADMIN_EMAILS": "admin@bv.com",
    "OWNER_EMAILS": "enderjnets@gmail.com",
}


@pytest.fixture(autouse=True)
def _isolate_settings():
    """Force this module's required env + a fresh settings cache for each test,
    then restore so later modules are unaffected."""
    saved = {k: os.environ.get(k) for k in _ENV}
    os.environ.update(_ENV)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()


def _patch_google(monkeypatch, *, email, sub, name="Test User"):
    parts = name.split()
    monkeypatch.setattr(
        auth_service,
        "verify_google_id_token",
        lambda _tok: {
            "email": email,
            "sub": sub,
            "name": name,
            "given_name": parts[0],
            "family_name": parts[-1],
        },
    )


def test_doc_loading_and_metadata():
    assert is_known_doc("client_terms")
    assert is_known_doc("driver_agreement")
    assert not is_known_doc("nope")
    assert current_version("client_terms") == "1.0"
    assert audience("driver_agreement") == "driver"
    assert normalize_lang("fr") == "en"
    assert normalize_lang("es") == "es"
    title, body = load_doc("client_terms", "en")
    assert title and len(body) > 200


def test_passenger_must_sign_client_terms(monkeypatch):
    _patch_google(
        monkeypatch, email="rider-legal@example.com", sub="sub-legal-rider", name="Rider Legal"
    )
    r = client.post("/api/v1/auth/login/google", json={"id_token": "x"})
    assert r.status_code == 200 and r.json()["role"] == "passenger"

    assert client.get("/api/v1/auth/me").json()["agreements_pending"] == ["client_terms"]

    doc = client.get("/api/v1/agreements/client_terms?lang=en")
    assert doc.status_code == 200
    assert doc.json()["version"] == "1.0"
    assert doc.json()["audience"] == "client"
    assert len(doc.json()["content_md"]) > 200

    # a passenger may only fetch their own document
    assert client.get("/api/v1/agreements/driver_agreement").status_code == 403

    # stale version is rejected
    stale = client.post(
        "/api/v1/agreements/client_terms/accept", json={"version": "0.9", "lang": "en"}
    )
    assert stale.status_code == 409

    ok = client.post(
        "/api/v1/agreements/client_terms/accept", json={"version": "1.0", "lang": "en"}
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True

    assert client.get("/api/v1/auth/me").json()["agreements_pending"] == []

    # accepting again is idempotent
    again = client.post(
        "/api/v1/agreements/client_terms/accept", json={"version": "1.0", "lang": "en"}
    )
    assert again.status_code == 200


def test_principal_owner_is_exempt():
    r = client.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").json()["agreements_pending"] == []


def test_non_owner_admin_must_sign_driver_agreement(monkeypatch):
    _patch_google(monkeypatch, email="admin@bv.com", sub="sub-legal-admin", name="Admin Boss")
    r = client.post("/api/v1/auth/login/google", json={"id_token": "x"})
    assert r.status_code == 200 and r.json()["role"] == "owner"

    assert client.get("/api/v1/auth/me").json()["agreements_pending"] == ["driver_agreement"]

    # not their document
    assert client.get("/api/v1/agreements/client_terms").status_code == 403

    # the driver agreement requires a typed legal name (electronic signature)
    no_name = client.post(
        "/api/v1/agreements/driver_agreement/accept", json={"version": "1.0", "lang": "en"}
    )
    assert no_name.status_code == 422

    ok = client.post(
        "/api/v1/agreements/driver_agreement/accept",
        json={"version": "1.0", "lang": "en", "signed_name": "Admin Boss"},
    )
    assert ok.status_code == 200

    assert client.get("/api/v1/auth/me").json()["agreements_pending"] == []


def test_public_documents_are_unauthenticated():
    fresh = TestClient(app)  # no cookie → truly anonymous
    for doc in ("client_terms", "privacy_policy", "driver_agreement"):
        r = fresh.get(f"/api/v1/agreements/public/{doc}?lang=en")
        assert r.status_code == 200, doc
        body = r.json()
        assert body["doc_type"] == doc
        assert body["version"] == "1.0"
        assert len(body["content_md"]) > 200
    es = fresh.get("/api/v1/agreements/public/privacy_policy?lang=es")
    assert es.status_code == 200 and es.json()["lang"] == "es"
    assert fresh.get("/api/v1/agreements/public/nope").status_code == 404


def test_unsigned_passenger_cannot_book_server_side(monkeypatch):
    """The gate is enforced server-side, not just in the UI: an unsigned passenger
    cannot create a ride via the API."""
    _patch_google(
        monkeypatch, email="rider-gate@example.com", sub="sub-gate-rider", name="Gate Rider"
    )
    assert client.post("/api/v1/auth/login/google", json={"id_token": "x"}).status_code == 200

    body = {"pickup": "Cherry Creek", "dropoff": "DEN", "pax": 1, "passenger_name": "Gate Rider"}
    blocked = client.post("/api/v1/rides", json=body)
    assert blocked.status_code == 403
    detail = blocked.json().get("detail")
    assert isinstance(detail, dict) and detail.get("error") == "agreement_required"

    # after signing, the booking is no longer blocked by the gate
    client.post("/api/v1/agreements/client_terms/accept", json={"version": "1.0", "lang": "en"})
    assert client.post("/api/v1/rides", json=body).status_code != 403
