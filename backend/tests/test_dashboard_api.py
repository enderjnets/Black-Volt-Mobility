"""Dashboard API tests (stats + clients + enriched ride detail). DB-backed."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _owner():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _make_ride(c, name="Test Rider"):
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek",
            "dropoff": "Denver Intl (DEN)",
            "pax": 1,
            "passenger_name": name,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_stats_requires_staff():
    assert client.get("/api/v1/dashboard/stats").status_code == 401


def test_stats_shape():
    c = _owner()
    _make_ride(c)
    _make_ride(c)
    r = c.get("/api/v1/dashboard/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "today" in body and "revenue" in body["today"]
    assert body["totals"]["rides"] >= 2
    assert len(body["week"]) == 7
    # Weekly chart is earnings-based now: each day carries a revenue, plus a total.
    assert all("revenue" in d for d in body["week"])
    assert "week_total" in body


def test_revenue_counts_only_paid_rides_today():
    c = _owner()
    before = c.get("/api/v1/dashboard/stats").json()["today"]["revenue"]
    rid = _make_ride(c, name="Payer")
    fare = c.get(f"/api/v1/rides/{rid}").json()["fare_total"] or 0
    assert fare > 0
    # An unpaid ride does not move revenue.
    assert c.get("/api/v1/dashboard/stats").json()["today"]["revenue"] == before
    # Marking it paid (service day = today via created_at) adds exactly its fare.
    assert c.patch(f"/api/v1/rides/{rid}", json={"paid": True}).status_code == 200
    body = c.get("/api/v1/dashboard/stats").json()
    assert round(body["today"]["revenue"] - before, 2) == round(fare, 2)
    assert body["week_total"] >= body["today"]["revenue"]


def test_clients_requires_staff():
    assert client.get("/api/v1/clients").status_code == 401


def test_clients_returns_list():
    c = _owner()
    r = c.get("/api/v1/clients")
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["clients"], list)


def test_list_rides_has_client_name():
    c = _owner()
    _make_ride(c, name="Jane Doe")
    rides = c.get("/api/v1/rides").json()["rides"]
    assert any(x.get("client_name") == "Jane Doe" for x in rides)


def test_ride_detail_has_client_and_payment():
    c = _owner()
    rid = _make_ride(c)
    # authorize a (simulated) payment
    pay = c.post("/api/v1/payments", json={"ride_id": rid, "source_id": "cnon:card-nonce-ok"})
    assert pay.status_code == 201, pay.text
    detail = c.get(f"/api/v1/rides/{rid}").json()
    assert "client" in detail
    assert detail["payment"] is not None
    assert detail["payment"]["status"] == "authorized"
