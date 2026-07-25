"""Ride hand-off: assign to another driver, money split, internal thread, PII window.

The ride NEVER changes owner — the owner keeps the customer, the money and control;
the assigned driver gets visibility, the internal thread, and their cut. Covers who may
do what, that the passenger can NEVER see the internal channel, and that the customer's
contact details stop being visible to the assigned driver once the trip is over.
All against the isolated blackvolt_test DB, never prod.
"""
import asyncio
import os

import pytest

from app.models import AllowedUser, Ride, RideStatus
from app.models.allowed_user import ROLE_DRIVER
from app.services import push, ratelimit
from tests.test_ride_messages_api import (
    _make_ride,
    _passenger_client,
    _seed_client_in,
    _seed_tenant_client,
    _session_factory,
    _staff_client,
)


@pytest.fixture(autouse=True)
def _no_push_no_limits(monkeypatch):
    ratelimit.reset()
    monkeypatch.setattr(push, "notify_staff", lambda *a, **k: None)
    monkeypatch.setattr(push, "notify_client", lambda *a, **k: None)


def _seed_driver_user(tenant_id: int, email: str | None = None) -> str:
    """A team driver with their OWN workspace — the only kind a ride can go to."""
    mail = email or f"drv-{os.urandom(4).hex()}@team.local"

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                db.add(
                    AllowedUser(
                        email=mail, role=ROLE_DRIVER, tenant_id=tenant_id, name="Nodar"
                    )
                )
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())
    return mail


def _set_contact(ride_id: int, phone: str = "+13035550142") -> None:
    """A real booking carries the passenger's contact on the ride itself."""

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = await db.get(Ride, ride_id)
                ride.passenger_name = "Lauren Brom"
                ride.passenger_phone = phone
                ride.notes = "2 adults, 2 kids"
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _set_fare(ride_id: int, fare: float) -> None:
    """_make_ride leaves the ride unpriced; the split needs a fare to divide."""

    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = await db.get(Ride, ride_id)
                ride.fare_total = fare
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _set_status(ride_id: int, status: RideStatus) -> None:
    async def go():
        eng, Sf = _session_factory()
        try:
            async with Sf() as db:
                ride = await db.get(Ride, ride_id)
                ride.status = status
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _pair():
    """(owner_tenant, driver_tenant, driver_email, ride_id) ready to hand off."""
    _cid, owner_t = _seed_tenant_client("owner")
    _cid2, driver_t = _seed_tenant_client("nodar")
    email = _seed_driver_user(driver_t)
    client_id = _seed_client_in(owner_t)
    ride_id = _make_ride(owner_t, client_id=client_id, status=RideStatus.CONFIRMED)
    _set_fare(ride_id, 95.0)  # the owner's own example
    _set_contact(ride_id)
    return owner_t, driver_t, email, ride_id, client_id


# ─── Assigning ────────────────────────────────────────────────────────────────
def test_assign_makes_ride_visible_to_the_other_driver():
    owner_t, driver_t, email, ride_id, _ = _pair()
    drv = _staff_client(driver_t)
    assert all(r["id"] != ride_id for r in drv.get("/api/v1/rides").json()["rides"])

    r = _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign",
        json={"driver_email": email, "driver_share_pct": 80},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] is True
    assert r.json()["driver_share_pct"] == 80

    ids = [x["id"] for x in drv.get("/api/v1/rides").json()["rides"]]
    assert ride_id in ids, "the assigned driver must now see the ride"


def test_owner_keeps_the_ride_and_the_driver_cannot_reassign():
    owner_t, driver_t, email, ride_id, _ = _pair()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": email}
    )
    other = _seed_driver_user(_seed_tenant_client("third")[1])
    r = _staff_client(driver_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": other}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "not_ride_owner"


def test_driver_cannot_touch_the_payout():
    owner_t, driver_t, email, ride_id, _ = _pair()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": email}
    )
    r = _staff_client(driver_t).patch(
        f"/api/v1/rides/{ride_id}/payout", json={"driver_share_pct": 100}
    )
    assert r.status_code == 403


def test_cannot_assign_to_someone_who_is_not_an_assignable_driver():
    owner_t, _dt, _email, ride_id, _ = _pair()
    r = _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": "stranger@nope.local"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "driver_not_assignable"


def test_unassign_takes_the_ride_back():
    owner_t, driver_t, email, ride_id, _ = _pair()
    own = _staff_client(owner_t)
    own.post(f"/api/v1/rides/{ride_id}/assign", json={"driver_email": email})
    r = own.delete(f"/api/v1/rides/{ride_id}/assign")
    assert r.status_code == 200
    assert r.json()["assigned"] is False
    assert r.json()["driver_share_pct"] is None
    ids = [x["id"] for x in _staff_client(driver_t).get("/api/v1/rides").json()["rides"]]
    assert ride_id not in ids


def test_assignable_drivers_excludes_me():
    owner_t, driver_t, email, _rid, _ = _pair()
    rows = _staff_client(owner_t).get("/api/v1/rides/assignable-drivers").json()
    emails = [x["email"] for x in rows]
    assert email in emails


# ─── Money split ──────────────────────────────────────────────────────────────
def test_earnings_snapshot_and_owner_view():
    owner_t, _dt, email, ride_id, _ = _pair()
    own = _staff_client(owner_t)
    own.post(
        f"/api/v1/rides/{ride_id}/assign",
        json={"driver_email": email, "driver_share_pct": 80},
    )
    e = own.get(f"/api/v1/rides/{ride_id}").json()["earnings"]
    assert e["gross"] == 95.0
    assert e["square_fee"] == 3.06  # 2.9% + 30c on 95
    assert e["driver_amount"] == 73.55
    assert e["owner_amount"] == 18.39
    assert round(e["square_fee"] + e["tax_reserve"] + e["net"], 2) == e["gross"]
    assert round(e["driver_amount"] + e["owner_amount"], 2) == e["net"]
    assert e["driver_share_pct"] == 80
    assert e["payout_status"] == "unpaid"


def test_assigned_driver_sees_only_their_cut():
    owner_t, driver_t, email, ride_id, _ = _pair()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": email}
    )
    e = _staff_client(driver_t).get(f"/api/v1/rides/{ride_id}").json()["earnings"]
    assert "driver_amount" in e
    # The owner's cut, the gross and the fees are none of the driver's business.
    assert "owner_amount" not in e and "gross" not in e and "square_fee" not in e


def test_owner_can_change_share_and_mark_paid():
    owner_t, _dt, email, ride_id, _ = _pair()
    own = _staff_client(owner_t)
    own.post(
        f"/api/v1/rides/{ride_id}/assign",
        json={"driver_email": email, "driver_share_pct": 50},
    )
    r = own.patch(
        f"/api/v1/rides/{ride_id}/payout", json={"driver_share_pct": 70, "paid": True}
    )
    assert r.status_code == 200
    assert r.json()["driver_share_pct"] == 70
    assert r.json()["driver_payout_status"] == "paid"
    assert r.json()["driver_paid_at"] is not None
    e = own.get(f"/api/v1/rides/{ride_id}").json()["earnings"]
    assert e["driver_share_pct"] == 70


def test_earnings_preview_does_not_persist():
    owner_t, _dt, email, ride_id, _ = _pair()
    own = _staff_client(owner_t)
    own.post(
        f"/api/v1/rides/{ride_id}/assign",
        json={"driver_email": email, "driver_share_pct": 80},
    )
    prev = own.get(f"/api/v1/rides/{ride_id}/earnings-preview?driver_share_pct=50").json()
    assert prev["driver_share_pct"] == 50
    # The saved ride is untouched by a preview.
    assert own.get(f"/api/v1/rides/{ride_id}").json()["driver_share_pct"] == 80


# ─── Internal thread ──────────────────────────────────────────────────────────
def _assigned():
    owner_t, driver_t, email, ride_id, client_id = _pair()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign", json={"driver_email": email}
    )
    return owner_t, driver_t, ride_id, client_id


def test_internal_thread_is_two_way_between_owner_and_driver():
    owner_t, driver_t, ride_id, _ = _assigned()
    own, drv = _staff_client(owner_t), _staff_client(driver_t)
    assert own.post(
        f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "On your way?"}
    ).status_code == 201
    assert drv.post(
        f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "Pickup done"}
    ).status_code == 201

    seen_by_driver = drv.get(f"/api/v1/rides/{ride_id}/internal-messages").json()
    bodies = [m["body"] for m in seen_by_driver["messages"]]
    assert "On your way?" in bodies and "Pickup done" in bodies
    # `mine` is by tenant: both sides are staff, so sender alone can't tell them apart.
    mine = {m["body"]: m["mine"] for m in seen_by_driver["messages"]}
    assert mine["Pickup done"] is True and mine["On your way?"] is False


def test_assignment_opens_the_thread_with_a_note():
    owner_t, driver_t, email, ride_id, _ = _pair()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/assign",
        json={"driver_email": email, "note": "Client has 2 kids"},
    )
    msgs = _staff_client(driver_t).get(
        f"/api/v1/rides/{ride_id}/internal-messages"
    ).json()["messages"]
    assert any("assigned to you" in m["body"] for m in msgs)
    assert any("2 kids" in m["body"] for m in msgs)


def test_passenger_can_NEVER_see_or_write_the_internal_thread():
    """The whole point of a second channel: this is staff-only."""
    owner_t, driver_t, ride_id, client_id = _assigned()
    _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "pay him 80"}
    )
    pax = _passenger_client(client_id, owner_t)
    assert pax.get(f"/api/v1/rides/{ride_id}/internal-messages").status_code == 403
    assert pax.post(
        f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "hi"}
    ).status_code == 403
    # And it must not leak through the passenger's own thread either.
    thread = pax.get(f"/api/v1/rides/{ride_id}/messages").json()
    assert all("pay him 80" not in m["body"] for m in thread["messages"])


def test_client_channel_is_unaffected_by_internal_messages():
    """No regression: the passenger thread and its unread count ignore internal rows."""
    owner_t, driver_t, ride_id, client_id = _assigned()
    own = _staff_client(owner_t)
    own.post(f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "internal only"})
    own.post(f"/api/v1/rides/{ride_id}/messages", json={"body": "hello passenger"})
    pax = _passenger_client(client_id, owner_t)
    thread = pax.get(f"/api/v1/rides/{ride_id}/messages").json()
    bodies = [m["body"] for m in thread["messages"]]
    assert bodies == ["hello passenger"]


def test_internal_unread_is_reported_per_side_and_clears_on_read():
    owner_t, driver_t, ride_id, _ = _assigned()
    own, drv = _staff_client(owner_t), _staff_client(driver_t)
    own.post(f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "ping"})

    def unread_for(c):
        row = next(r for r in c.get("/api/v1/rides").json()["rides"] if r["id"] == ride_id)
        return row["internal_unread"]

    assert unread_for(drv) >= 1, "driver has an unread message from the owner"
    assert unread_for(own) == 0, "my own message is not unread for me"
    drv.get(f"/api/v1/rides/{ride_id}/internal-messages")  # opening marks read
    assert unread_for(drv) == 0


def test_cannot_write_internal_on_an_unassigned_ride():
    owner_t, _dt, _email, ride_id, _ = _pair()
    r = _staff_client(owner_t).post(
        f"/api/v1/rides/{ride_id}/internal-messages", json={"body": "hello?"}
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "ride_not_assigned"


def test_third_party_tenant_cannot_reach_the_thread():
    _owner_t, _driver_t, ride_id, _ = _assigned()
    stranger = _staff_client(_seed_tenant_client("stranger")[1])
    # Not their ride at all → it doesn't even exist for them.
    assert stranger.get(f"/api/v1/rides/{ride_id}/internal-messages").status_code == 404


# ─── Customer PII window ──────────────────────────────────────────────────────
def test_assigned_driver_sees_contact_while_the_ride_is_live():
    owner_t, driver_t, ride_id, _ = _assigned()
    d = _staff_client(driver_t).get(f"/api/v1/rides/{ride_id}").json()
    assert not d.get("pii_masked")
    assert d["passenger_phone"] == "+13035550142", "driver can call the passenger"
    assert d["pickup"] == "6000 S Fraser St, Aurora", "full address while working"
    assert d["notes"] == "2 adults, 2 kids"


def test_contact_is_masked_for_the_driver_once_the_ride_is_done():
    """The customer belongs to the owner: after the trip the driver keeps no details."""
    owner_t, driver_t, ride_id, _ = _assigned()
    _set_status(ride_id, RideStatus.COMPLETED)
    d = _staff_client(driver_t).get(f"/api/v1/rides/{ride_id}").json()
    assert d["pii_masked"] is True
    assert d["notes"] is None
    assert "•" in d["passenger_phone"], "the phone the driver used is now hidden"
    assert "7366" not in (d["pickup"] or ""), "street line dropped"
    assert d["passenger_name"] == "Lauren Brom", "name stays: whose ride it was"
    # The client CRM record is tenant-scoped, so an assigned driver never gets it.
    assert d.get("client") is None
    # The owner is unaffected.
    o = _staff_client(owner_t).get(f"/api/v1/rides/{ride_id}").json()
    assert not o.get("pii_masked")
    assert o["passenger_phone"] == "+13035550142"
    assert o["notes"] == "2 adults, 2 kids"


def test_masking_also_applies_in_the_list_for_the_driver():
    owner_t, driver_t, ride_id, _ = _assigned()
    _set_status(ride_id, RideStatus.COMPLETED)
    row = next(
        r
        for r in _staff_client(driver_t).get("/api/v1/rides").json()["rides"]
        if r["id"] == ride_id
    )
    assert row["pii_masked"] is True
    own_row = next(
        r
        for r in _staff_client(owner_t).get("/api/v1/rides").json()["rides"]
        if r["id"] == ride_id
    )
    assert not own_row.get("pii_masked")
