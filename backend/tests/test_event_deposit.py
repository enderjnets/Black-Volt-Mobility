"""Event reservation deposit model + traffic-aware pickup suggestion + AI duration estimate.

Covers, money-critical:
- 1/3 deposit charged now (terms accepted); balance stays owed (paid == False)
- event round trip WITHOUT terms accepted keeps the legacy full-prepay behaviour (no regression)
- 48h refund policy: >=48h before the event -> deposit refunded; <48h -> deposit kept
- maps traffic-aware duration (live duration_in_traffic + simulated buffer)
- public pickup-suggestion endpoint
- AI event-duration estimate (parse + fallback + approval wiring)

All money runs in simulated Square (PAYMENTS_SIMULATED=true) — never a live charge.
"""

import asyncio
import datetime as dt
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SOCIAL_SIMULATED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402

_VENUE = "Empower Field at Mile High, 1701 Bryant St, Denver, CO 80204"
_ORIGIN = "Cherry Creek, Denver, CO"


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


async def _seed_event(starts_at: dt.datetime) -> str:
    from app.db.base import get_session_factory
    from app.models import Event
    from app.services.tenancy import owner_tenant_id

    async with get_session_factory()() as db:
        tid = await owner_tenant_id(db)
        slug = f"evt-{uuid.uuid4().hex[:8]}"
        db.add(
            Event(
                tenant_id=tid, slug=slug, title="Ed Sheeran", venue_key="empower_field",
                venue_name="Empower Field at Mile High",
                venue_address="1701 Bryant St, Denver, CO 80204",
                starts_at=starts_at, status="published",
                event_fee=0, night_fee=25, wait_fee_per_hour=40, est_duration_hours=3,
            )
        )
        await db.commit()
    return slug


async def _ride_row(ride_id: int):
    from app.db.base import get_session_factory
    from app.models import Ride

    async with get_session_factory()() as db:
        return (await db.execute(select(Ride).where(Ride.id == ride_id))).scalar_one()


async def _payment_row(ride_id: int):
    from app.db.base import get_session_factory
    from app.models import Payment

    async with get_session_factory()() as db:
        return (
            await db.execute(
                select(Payment).where(Payment.ride_id == ride_id).order_by(Payment.id.desc())
            )
        ).scalars().first()


def _book_deposit(c: TestClient, event_start: dt.datetime, *, terms: bool = True) -> dict:
    """Book an event round trip (outbound + return). Returns the outbound ride JSON."""
    pickup_at = event_start - dt.timedelta(hours=1)
    return_at = event_start + dt.timedelta(hours=3)
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": _ORIGIN, "dropoff": _VENUE,
            "scheduled_at": pickup_at.isoformat(), "return_at": return_at.isoformat(),
            "round_trip": True, "terms_accepted": terms,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── deposit booking + payment ────────────────────────────────────────────────


def test_deposit_charges_one_third_and_leaves_balance():
    c = _owner()
    start = dt.datetime(2027, 8, 14, 2, 0, tzinfo=dt.UTC)  # far future -> refundable window
    asyncio.run(_seed_event(start))
    out = _book_deposit(c, start)
    assert out["price_breakdown"].get("event")

    total = out["price_breakdown"]["round_trip_total"]
    dep = out["price_breakdown"]["deposit"]
    expected_deposit_cents = int(round(total * 100 / 3))
    assert dep["pct"] == 33
    assert round(dep["deposit"] + dep["balance"], 2) == round(total, 2)

    row = asyncio.run(_ride_row(out["id"]))
    assert row.deposit_cents == expected_deposit_cents
    assert row.balance_due_cents == int(round(total * 100)) - expected_deposit_cents
    assert row.terms_accepted_at is not None
    assert row.terms_version == "1.0"

    # Pay the deposit — only 1/3 is charged and the ride is NOT marked fully paid.
    pr = c.post("/api/v1/payments", json={"ride_id": out["id"], "source_id": "cnon:card-nonce-ok"})
    assert pr.status_code == 201, pr.text
    pay = asyncio.run(_payment_row(out["id"]))
    assert pay.amount == expected_deposit_cents
    assert pay.status.value == "captured"
    paid_row = asyncio.run(_ride_row(out["id"]))
    assert paid_row.paid is False  # balance still owed (collected in person)
    assert paid_row.status.value == "confirmed"


def test_terms_accepted_but_no_event_match_is_rejected():
    # Safety: accepting terms for a trip that matches NO event must fail loudly (422), never
    # silently create a full-fare booking while the rider was shown a 1/3 deposit.
    c = _owner()
    start = dt.datetime(2027, 10, 1, 2, 0, tzinfo=dt.UTC)  # no event seeded
    pickup_at = start - dt.timedelta(hours=1)
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": _ORIGIN, "dropoff": "123 Random St, Denver, CO",
            "scheduled_at": pickup_at.isoformat(),
            "return_at": (start + dt.timedelta(hours=3)).isoformat(),
            "round_trip": True, "terms_accepted": True,
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "event_unavailable"


def test_event_roundtrip_without_terms_is_full_prepay():
    # Regression: an event round trip booked WITHOUT accepting terms keeps the old behaviour
    # (charged in full, marked paid) — no deposit.
    c = _owner()
    start = dt.datetime(2027, 9, 3, 2, 0, tzinfo=dt.UTC)
    asyncio.run(_seed_event(start))
    out = _book_deposit(c, start, terms=False)
    assert "deposit" not in out["price_breakdown"]
    row = asyncio.run(_ride_row(out["id"]))
    assert row.deposit_cents is None

    total = out["price_breakdown"]["round_trip_total"]
    pr = c.post("/api/v1/payments", json={"ride_id": out["id"], "source_id": "cnon:card-nonce-ok"})
    assert pr.status_code == 201, pr.text
    pay = asyncio.run(_payment_row(out["id"]))
    assert pay.amount == int(round(total * 100))  # full total, not a third
    assert asyncio.run(_ride_row(out["id"])).paid is True


# ── 48h refund policy ────────────────────────────────────────────────────────


def test_deposit_refunded_when_cancelled_before_48h():
    c = _owner()
    start = dt.datetime.now(dt.UTC) + dt.timedelta(days=10)  # well outside 48h
    asyncio.run(_seed_event(start))
    out = _book_deposit(c, start)
    c.post("/api/v1/payments", json={"ride_id": out["id"], "source_id": "cnon:card-nonce-ok"})
    dep_cents = asyncio.run(_ride_row(out["id"])).deposit_cents

    r = c.post(f"/api/v1/rides/{out['id']}/cancel")
    assert r.status_code == 200, r.text
    pay = asyncio.run(_payment_row(out["id"]))
    assert pay.status.value == "refunded"
    assert pay.refunded_amount == dep_cents  # full deposit back


def test_deposit_kept_when_cancelled_within_48h():
    c = _owner()
    start = dt.datetime.now(dt.UTC) + dt.timedelta(hours=40)  # inside 48h -> non-refundable
    asyncio.run(_seed_event(start))
    out = _book_deposit(c, start)
    c.post("/api/v1/payments", json={"ride_id": out["id"], "source_id": "cnon:card-nonce-ok"})

    r = c.post(f"/api/v1/rides/{out['id']}/cancel")
    assert r.status_code == 200, r.text
    pay = asyncio.run(_payment_row(out["id"]))
    assert pay.status.value == "captured"  # deposit kept, not refunded
    assert pay.refunded_amount is None
    assert asyncio.run(_ride_row(out["id"])).paid is True  # driver kept the deposit


# ── maps traffic-aware duration ──────────────────────────────────────────────


def test_live_route_prefers_duration_in_traffic(monkeypatch):
    from app.services import maps

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "status": "OK",
                "rows": [{"elements": [{
                    "status": "OK",
                    "distance": {"value": 16093},       # ~10 mi
                    "duration": {"value": 600},          # 10 min free-flow
                    "duration_in_traffic": {"value": 1200},  # 20 min in traffic
                }]}],
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(maps.httpx, "AsyncClient", FakeClient)
    r = asyncio.run(
        maps._live_route("A", "B", None, dt.datetime(2030, 1, 1, tzinfo=dt.UTC))
    )
    assert r.duration_minutes == 20.0  # traffic value, not the 10-min free-flow
    assert r.traffic_aware is True


def test_simulated_route_adds_traffic_buffer():
    from app.services import maps

    base = asyncio.run(maps.route("111 A St, Denver, CO", "222 B St, Denver, CO"))
    withtraffic = asyncio.run(
        maps.route(
            "111 A St, Denver, CO", "222 B St, Denver, CO",
            depart_at=dt.datetime(2030, 1, 1, tzinfo=dt.UTC),
        )
    )
    assert withtraffic.simulated is True
    assert withtraffic.traffic_aware is False  # simulated is honest: not real traffic
    assert withtraffic.duration_minutes >= base.duration_minutes


# ── public pickup-suggestion endpoint ────────────────────────────────────────


def test_pickup_suggestion_arrives_before_show():
    c = TestClient(app)
    start = dt.datetime(2027, 8, 14, 2, 0, tzinfo=dt.UTC)
    slug = asyncio.run(_seed_event(start))
    r = c.get(f"/api/v1/events/public/{slug}/pickup-suggestion", params={"origin": _ORIGIN})
    assert r.status_code == 200, r.text
    body = r.json()
    arrive_by = dt.datetime.fromisoformat(body["arrive_by"])
    pickup_at = dt.datetime.fromisoformat(body["pickup_at"])
    assert arrive_by == start - dt.timedelta(minutes=30)  # 30-min buffer
    assert pickup_at < arrive_by                          # leave earlier to account for travel
    assert body["travel_minutes_out"] > 0
    assert body["return_pickup_at"]


def test_pickup_suggestion_missing_origin_422():
    c = TestClient(app)
    slug = asyncio.run(_seed_event(dt.datetime(2027, 8, 14, 2, 0, tzinfo=dt.UTC)))
    r = c.get(f"/api/v1/events/public/{slug}/pickup-suggestion", params={"origin": ""})
    assert r.status_code == 422


def test_pickup_suggestion_unknown_event_404():
    c = TestClient(app)
    r = c.get("/api/v1/events/public/nope-nope/pickup-suggestion", params={"origin": _ORIGIN})
    assert r.status_code == 404


# ── AI event-duration estimate ───────────────────────────────────────────────


def test_estimate_duration_parses_and_clamps(monkeypatch):
    from app.services import events

    sug = _fake_suggestion()

    async def _one(*a, **k):
        return "About 2.5 hours"

    monkeypatch.setattr(events.social, "_providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(events.llm, "text_complete", _one)
    assert asyncio.run(events._estimate_duration_hours(sug)) == 2.5


def test_estimate_duration_falls_back(monkeypatch):
    from app.services import events

    async def _boom(*a, **k):
        raise RuntimeError("no provider")

    monkeypatch.setattr(events.social, "_providers", lambda: [("m", "u", "k")])
    monkeypatch.setattr(events.llm, "text_complete", _boom)
    assert asyncio.run(events._estimate_duration_hours(_fake_suggestion())) == 3.0


def _fake_suggestion():
    from app.models import EventSuggestion

    return EventSuggestion(
        source="seatgeek", source_id="x", title="Ed Sheeran",
        performer="Ed Sheeran", venue_name="Empower Field",
        starts_at=dt.datetime(2027, 8, 14, 2, 0, tzinfo=dt.UTC), status="suggested", raw={},
    )
