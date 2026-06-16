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


def test_revenue_counts_completed_unpaid_rides():
    c = _owner()
    before = c.get("/api/v1/dashboard/stats").json()["today"]["revenue"]
    rid = _make_ride(c, name="Completer")
    fare = c.get(f"/api/v1/rides/{rid}").json()["fare_total"] or 0
    assert fare > 0
    # Driver completed the ride (cash) but never toggled the "paid" flag — it must
    # still count as revenue.
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"}).status_code == 200
    body = c.get("/api/v1/dashboard/stats").json()
    assert round(body["today"]["revenue"] - before, 2) == round(fare, 2)
    assert body["week_total"] >= body["today"]["revenue"]


def test_cancelled_ride_never_counts_as_revenue():
    c = _owner()
    base = c.get("/api/v1/dashboard/stats").json()["today"]["revenue"]
    rid = _make_ride(c, name="Canceller")
    # Even a cancelled-but-paid ride must not inflate revenue.
    assert c.patch(f"/api/v1/rides/{rid}", json={"paid": True}).status_code == 200
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "cancelled"}).status_code == 200
    assert c.get("/api/v1/dashboard/stats").json()["today"]["revenue"] == base


def test_rides_today_counts_adhoc_and_excludes_cancelled():
    c = _owner()
    before = c.get("/api/v1/dashboard/stats").json()["today"]["rides"]
    # An ad-hoc ride (no scheduled_at, created today) counts toward today.
    rid = _make_ride(c, name="Adhoc")
    assert c.get("/api/v1/dashboard/stats").json()["today"]["rides"] == before + 1
    # Cancelling it drops it back out of the count.
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "cancelled"}).status_code == 200
    assert c.get("/api/v1/dashboard/stats").json()["today"]["rides"] == before


def test_week_requires_staff():
    assert client.get("/api/v1/dashboard/week").status_code == 401


def test_week_offset_zero_matches_stats():
    c = _owner()
    rid = _make_ride(c, name="WeekPayer")
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"}).status_code == 200
    wk = c.get("/api/v1/dashboard/week?offset=0").json()
    assert len(wk["days"]) == 7
    assert "start" in wk and "end" in wk and wk["offset"] == 0
    # The navigable current week equals the "This week" card on the dashboard.
    stats = c.get("/api/v1/dashboard/stats").json()
    assert wk["total"] == stats["week_total"]
    assert wk["total"] > 0  # the completed ride counts


def test_week_past_week_excludes_today():
    from datetime import UTC, datetime

    c = _owner()
    rid = _make_ride(c, name="TodayRide")
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"}).status_code == 200
    this_week = c.get("/api/v1/dashboard/week?offset=0").json()
    last_week = c.get("/api/v1/dashboard/week?offset=-1").json()
    # Last week ends strictly before this week starts; ranges don't overlap.
    assert last_week["end"] < this_week["start"]
    today_iso = datetime.now(UTC).date().isoformat()
    assert today_iso not in {d["date"] for d in last_week["days"]}
    assert today_iso in {d["date"] for d in this_week["days"]}


def test_week_rejects_future_and_out_of_range():
    c = _owner()
    assert c.get("/api/v1/dashboard/week?offset=1").status_code == 422  # no future weeks
    assert c.get("/api/v1/dashboard/week?offset=-300").status_code == 422  # > 5yr back


def test_weeks_requires_staff():
    assert client.get("/api/v1/dashboard/weeks").status_code == 401


def test_weeks_summary_shape_and_totals_match_week():
    c = _owner()
    rid = _make_ride(c, name="WeeksPayer")
    assert c.patch(f"/api/v1/rides/{rid}", json={"status": "completed"}).status_code == 200
    rows = c.get("/api/v1/dashboard/weeks?count=8").json()
    assert isinstance(rows, list) and len(rows) == 8
    # Offsets run 0, -1, ... -7; each has start/end/total.
    assert [r["offset"] for r in rows] == list(range(0, -8, -1))
    for r in rows:
        assert "start" in r and "end" in r and "total" in r
    # Each batch total matches the single-week endpoint for that offset.
    for o in (0, -1, -3):
        single = c.get(f"/api/v1/dashboard/week?offset={o}").json()["total"]
        batch = next(r["total"] for r in rows if r["offset"] == o)
        assert batch == single
    # Current week's total is positive (the completed ride counts).
    assert next(r["total"] for r in rows if r["offset"] == 0) > 0


def test_weeks_rejects_out_of_range_count():
    c = _owner()
    assert c.get("/api/v1/dashboard/weeks?count=0").status_code == 422
    assert c.get("/api/v1/dashboard/weeks?count=53").status_code == 422


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
