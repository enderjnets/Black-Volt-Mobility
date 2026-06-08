"""Manual/Smart ride creation must persist the passenger as a real Client, plus
client search and create/delete CRUD. DB-backed (long-lived dev database, so each
case uses a unique phone/name to stay isolated from accumulated rows)."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _uniq() -> tuple[str, str]:
    """A unique (name, phone) pair so this case never collides with other rows."""
    tag = uuid.uuid4().hex[:10]
    return f"Persist {tag}", f"+1303{tag[:7]}"


def _make_ride(c: TestClient, *, name: str, phone: str | None = None, client_id=None) -> dict:
    body = {"pickup": "Cherry Creek", "dropoff": "Denver Intl (DEN)", "pax": 1}
    if name:
        body["passenger_name"] = name
    if phone:
        body["passenger_phone"] = phone
    if client_id:
        body["client_id"] = client_id
    r = c.post("/api/v1/rides", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _find_client(c: TestClient, name: str) -> dict | None:
    for cl in c.get("/api/v1/clients").json()["clients"]:
        if cl["name"] == name:
            return cl
    return None


# ── Part 1: a manual/smart ride creates + links a Client ────────────────────
def test_create_ride_persists_new_client():
    name, phone = _uniq()
    c = _owner()
    rid = _make_ride(c, name=name, phone=phone)["id"]

    cl = _find_client(c, name)
    assert cl is not None, "the typed passenger should now exist in Clients"
    assert cl["phone"] == phone
    assert cl["rides_count"] == 1

    # The ride is linked to that client (detail resolves the client object).
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert detail["client"] is not None
    assert detail["client"]["id"] == cl["id"]


def test_same_phone_dedups_to_one_client():
    name, phone = _uniq()
    c = _owner()
    _make_ride(c, name=name, phone=phone)
    _make_ride(c, name=name, phone=phone)  # same contact → must reuse the client

    matches = [cl for cl in c.get("/api/v1/clients").json()["clients"] if cl["phone"] == phone]
    assert len(matches) == 1
    assert matches[0]["rides_count"] == 2


def test_ride_without_name_or_phone_creates_no_client():
    c = _owner()
    before = len(c.get("/api/v1/clients").json()["clients"])
    r = c.post(
        "/api/v1/rides",
        json={"pickup": "Cherry Creek", "dropoff": "Denver Intl (DEN)", "pax": 1},
    )
    assert r.status_code == 201, r.text
    after = len(c.get("/api/v1/clients").json()["clients"])
    assert after == before  # no empty client row


# ── Part 2: client search (autocomplete) ────────────────────────────────────
def test_client_search_matches_name_and_phone():
    name, phone = _uniq()
    c = _owner()
    _make_ride(c, name=name, phone=phone)

    by_name = c.get("/api/v1/clients/search", params={"q": name[:10]})
    assert by_name.status_code == 200, by_name.text
    hits = by_name.json()["clients"]
    assert any(h["name"] == name for h in hits)
    assert {"id", "name", "phone", "lang"} <= set(hits[0].keys())

    by_phone = c.get("/api/v1/clients/search", params={"q": phone[-7:]}).json()["clients"]
    assert any(h["phone"] == phone for h in by_phone)


def test_client_search_limits_results():
    c = _owner()
    r = c.get("/api/v1/clients/search", params={"q": "Persist"})
    assert r.status_code == 200
    assert len(r.json()["clients"]) <= 8


def test_client_search_requires_staff():
    assert TestClient(app).get("/api/v1/clients/search", params={"q": "x"}).status_code == 401


# ── Part 3: create + delete CRUD ────────────────────────────────────────────
def test_create_client_then_appears_in_list():
    name, phone = _uniq()
    c = _owner()
    r = c.post(
        "/api/v1/clients",
        json={"name": name, "phone": phone, "email": "x@example.com", "lang": "Spanish"},
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["name"] == name and d["phone"] == phone and d["lang"] == "ES"
    assert _find_client(c, name) is not None


def test_create_client_requires_name():
    c = _owner()
    assert c.post("/api/v1/clients", json={"phone": "+13030000000"}).status_code == 422


def test_delete_client_preserves_ride_history():
    name, phone = _uniq()
    c = _owner()
    rid = _make_ride(c, name=name, phone=phone)["id"]
    cl = _find_client(c, name)
    assert cl is not None

    r = c.delete(f"/api/v1/clients/{cl['id']}")
    assert r.status_code in (200, 204), r.text

    # Client is gone from the roster…
    assert _find_client(c, name) is None
    # …but the ride survives and still shows the passenger's name.
    rides = c.get("/api/v1/rides").json()["rides"]
    mine = next((x for x in rides if x["id"] == rid), None)
    assert mine is not None
    assert mine["client_name"] == name


def test_delete_client_not_found():
    assert _owner().delete("/api/v1/clients/99999999").status_code == 404


def test_create_and_delete_require_staff():
    anon = TestClient(app)
    assert anon.post("/api/v1/clients", json={"name": "x"}).status_code == 401
    assert anon.delete("/api/v1/clients/1").status_code == 401
