"""Passenger cancellation + driver refund decision, /trips driver contact
fallback, and driver new-ride/cancellation email hooks."""
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models import AllowedUser, Payment  # noqa: E402
from app.models.payment import PaymentStatus  # noqa: E402
from app.models.ride import RideStatus  # noqa: E402
from app.services import email as emailsvc  # noqa: E402
from tests.test_book_pay_gating import (  # noqa: E402
    _passenger_client,
    _seed_client_in_tenant,
    _seed_driver_tenant,
    _seed_passenger,
    _seed_ride,
    _session_factory,
)

client = TestClient(app)


# --- local helpers ---------------------------------------------------------
def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _make_ride_at(c: TestClient, scheduled_at: datetime) -> int:
    r = c.post(
        "/api/v1/rides",
        json={
            "pickup": "Cherry Creek",
            "dropoff": "Denver Intl (DEN)",
            "pax": 1,
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _authorize(c: TestClient, ride_id: int) -> dict:
    r = c.post("/api/v1/payments", json={"ride_id": ride_id, "source_id": "cnon:card-nonce-ok"})
    assert r.status_code == 201, r.text
    return r.json()


def _seed_payment(
    *,
    tenant_id: int,
    ride_id: int,
    amount: int = 7400,
    status: PaymentStatus = PaymentStatus.AUTHORIZED,
) -> int:
    async def go() -> int:
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                p = Payment(
                    tenant_id=tenant_id,
                    ride_id=ride_id,
                    amount=amount,
                    currency="USD",
                    status=status,
                    simulated=True,
                    square_payment_id="SIMUL-seeded",
                )
                db.add(p)
                await db.commit()
                await db.refresh(p)
                return p.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _payment_db(pid: int) -> tuple[str, int | None, int]:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                p = await db.get(Payment, pid)
                return (p.status.value, p.refunded_amount, p.amount)
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _ride_paid(ride_id: int) -> bool:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                from app.models.ride import Ride

                r = await db.get(Ride, ride_id)
                return r.paid
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _seed_allowed_user(tenant_id: int, email: str) -> None:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                db.add(AllowedUser(email=email, tenant_id=tenant_id, name="Driver"))
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _load_ride(ride_id: int):
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                from app.models.ride import Ride

                return await db.get(Ride, ride_id)
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _soon() -> datetime:
    return datetime.now(UTC) + timedelta(hours=2)


def _far() -> datetime:
    return datetime(2030, 1, 1, 15, 0, tzinfo=UTC)


def _ride(tid: int, cid: int, status: RideStatus, when: datetime) -> int:
    return _seed_ride(tenant_id=tid, client_id=cid, status=status, scheduled_at=when)


# --- passenger cancel: permissions ----------------------------------------
def test_passenger_cannot_cancel_others_ride():
    cid_a, tid = _seed_passenger()
    cid_b = _seed_client_in_tenant(tid)
    ride_id = _ride(tid, cid_a, RideStatus.CONFIRMED, _far())
    c = _passenger_client(cid_b, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 403, r.text


def test_passenger_cannot_cancel_en_route():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.EN_ROUTE, _soon())
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 409, r.text


def test_cancel_is_idempotent():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _far())
    c = _passenger_client(cid, tid)
    assert c.post(f"/api/v1/rides/{ride_id}/cancel").status_code == 200
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


# --- passenger cancel: money (>=24h auto full refund) ----------------------
def test_cancel_far_future_voids_authorized_hold():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _far())
    pid = _seed_payment(tenant_id=tid, ride_id=ride_id, status=PaymentStatus.AUTHORIZED)
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_at"]
    assert body["cancellation_fee_eligible"] is False
    assert _payment_db(pid)[0] == "canceled"


def test_cancel_far_future_refunds_captured_in_full():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _far())
    pid = _seed_payment(tenant_id=tid, ride_id=ride_id, amount=7400, status=PaymentStatus.CAPTURED)
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 200, r.text
    status, refunded, amount = _payment_db(pid)
    assert status == "refunded"
    assert refunded == amount == 7400


# --- passenger cancel: <24h leaves payment pending for the driver ----------
def test_cancel_within_24h_leaves_payment_pending():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _soon())
    pid = _seed_payment(tenant_id=tid, ride_id=ride_id, status=PaymentStatus.AUTHORIZED)
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_fee_eligible"] is True
    # Payment untouched — the driver still has to decide the refund.
    assert _payment_db(pid)[0] == "authorized"


# --- driver refund decision (staff, owner tenant) --------------------------
def test_refund_decision_full_refund_voids_authorized():
    c = _owner()
    ride_id = _make_ride_at(c, _soon())
    pay = _authorize(c, ride_id)
    assert pay["status"] == "authorized"
    assert c.post(f"/api/v1/rides/{ride_id}/cancel").json()["status"] == "cancelled"
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 0})
    assert r.status_code == 200, r.text
    assert _payment_db(pay["id"])[0] == "canceled"


def test_refund_decision_20pct_fee_captures_and_partial_refunds():
    c = _owner()
    ride_id = _make_ride_at(c, _soon())
    pay = _authorize(c, ride_id)
    amount = pay["amount"]
    assert c.post(f"/api/v1/rides/{ride_id}/cancel").json()["cancellation_fee_eligible"] is True
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 20})
    assert r.status_code == 200, r.text
    status, refunded, amt = _payment_db(pay["id"])
    fee = round(amount * 20 / 100)
    assert status == "refunded"
    assert refunded == amount - fee  # the 80% refunded; driver kept the 20% fee
    assert _ride_paid(ride_id) is True


def test_refund_decision_30pct_fee_partial_refunds():
    c = _owner()
    ride_id = _make_ride_at(c, _soon())
    pay = _authorize(c, ride_id)
    amount = pay["amount"]
    c.post(f"/api/v1/rides/{ride_id}/cancel")
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 30})
    assert r.status_code == 200, r.text
    _, refunded, _ = _payment_db(pay["id"])
    assert refunded == amount - round(amount * 30 / 100)


def test_refund_decision_fee_rejected_when_not_eligible():
    c = _owner()
    ride_id = _make_ride_at(c, _far())  # >=24h away -> no fee allowed
    _authorize(c, ride_id)
    c.post(f"/api/v1/rides/{ride_id}/cancel")  # auto full refund already happened
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 20})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "fee_not_eligible"


def test_refund_decision_rejects_non_cancelled_ride():
    c = _owner()
    ride_id = _make_ride_at(c, _soon())
    _authorize(c, ride_id)  # ride is CONFIRMED, not cancelled
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 0})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "ride_not_cancelled"


def test_refund_decision_invalid_pct_422():
    c = _owner()
    ride_id = _make_ride_at(c, _soon())
    c.post(f"/api/v1/rides/{ride_id}/cancel")
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 50})
    assert r.status_code == 422, r.text


def test_refund_decision_requires_staff():
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CANCELLED, _soon())
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/refund-decision", json={"fee_pct": 20})
    assert r.status_code in (401, 403), r.text


# --- /trips driver contact fallback (the production bug) -------------------
def test_assigned_driver_resolved_from_owning_tenant():
    did = _seed_driver_tenant("+13035551212", "Kia EV9", 4.97)
    cid = _seed_client_in_tenant(did)
    ride_id = _ride(did, cid, RideStatus.CONFIRMED, _far())
    c = _passenger_client(cid, did)
    rows = c.get("/api/v1/rides").json()["rides"]
    row = next(r for r in rows if r["id"] == ride_id)
    assert "assigned_driver" in row
    assert row["assigned_driver"]["phone"] == "+13035551212"
    assert row["assigned_driver"]["vehicle"] == "Kia EV9"


def test_no_driver_contact_when_owning_tenant_has_no_phone():
    # A bare passenger tenant has no driver phone -> no contact surfaced.
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _far())
    c = _passenger_client(cid, tid)
    rows = c.get("/api/v1/rides").json()["rides"]
    row = next(r for r in rows if r["id"] == ride_id)
    assert "assigned_driver" not in row


# --- driver email hooks ----------------------------------------------------
def test_send_driver_new_ride_skips_without_recipient():
    cid, tid = _seed_passenger()  # tenant has no AllowedUser
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _far())
    ride = _load_ride(ride_id)
    assert asyncio.run(_call_helper(ride)) == "skipped"


def test_send_driver_new_ride_emails_recipient():
    did = _seed_driver_tenant("+13035550000", "Kia EV9", 5.0)
    _seed_allowed_user(did, f"driver-{os.urandom(3).hex()}@bvtest.local")
    cid = _seed_client_in_tenant(did)
    ride_id = _ride(did, cid, RideStatus.CONFIRMED, _far())
    ride = _load_ride(ride_id)
    # No live Resend key in tests -> simulated send.
    assert asyncio.run(_call_helper(ride)) == "simulated"


async def _call_helper(ride) -> str:
    eng, Sf = _session_factory()
    try:
        async with Sf() as db:
            return await emailsvc.send_driver_new_ride(db, ride=ride)
    finally:
        await eng.dispose()


def test_confirm_ride_notifies_driver(monkeypatch):
    calls = []

    async def _rec(db, *, ride):
        calls.append(ride.id)
        return "ok"

    monkeypatch.setattr("app.services.email.send_driver_new_ride", _rec)
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.QUOTED, _far())
    c = _passenger_client(cid, tid)
    r = c.post(f"/api/v1/rides/{ride_id}/confirm")
    assert r.status_code == 200, r.text
    assert calls == [ride_id]


def test_cancel_notifies_driver(monkeypatch):
    calls = []

    async def _rec(db, *, ride, refund_pending=False):
        calls.append((ride.id, refund_pending))
        return "ok"

    monkeypatch.setattr("app.services.email.send_driver_ride_cancelled", _rec)
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CONFIRMED, _soon())
    _seed_payment(tenant_id=tid, ride_id=ride_id, status=PaymentStatus.AUTHORIZED)
    c = _passenger_client(cid, tid)
    assert c.post(f"/api/v1/rides/{ride_id}/cancel").status_code == 200
    assert calls == [(ride_id, True)]  # <24h with a live payment -> refund pending


async def _settle(ride_id: int, caller_tenant: int, fee_pct: int):
    from app.models.ride import Ride
    from app.services import payments as pmod

    eng, Sf = _session_factory()
    try:
        async with Sf() as db:
            ride = await db.get(Ride, ride_id)
            return await pmod.settle_cancellation(
                db, tenant_id=caller_tenant, ride=ride, fee_pct=fee_pct
            )
    finally:
        await eng.dispose()


def test_settle_uses_ride_owner_tenant_not_caller():
    # Discount-handoff: the payment lives under the booking (owner) tenant; a
    # servicing driver acting under a different tenant must still settle it.
    cid, tid = _seed_passenger()
    ride_id = _ride(tid, cid, RideStatus.CANCELLED, _far())
    pid = _seed_payment(tenant_id=tid, ride_id=ride_id, status=PaymentStatus.AUTHORIZED)
    res = asyncio.run(_settle(ride_id, caller_tenant=999_999, fee_pct=0))
    assert res is not None
    assert _payment_db(pid)[0] == "canceled"
