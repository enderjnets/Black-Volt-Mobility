"""Recording how a FINISHED ride was paid marks it paid.

Two real rides were driven, collected by Venmo, had their method AND their tip method
recorded — and still read "Unpaid", because picking the method and flipping the paid
flag were separate taps. On a ride that hasn't happened yet, picking a method is
planning, not collecting, so the rule is deliberately narrow.

Isolated blackvolt_test DB only.
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Ride, RideStatus  # noqa: E402
from tests.test_ride_messages_api import (  # noqa: E402
    _make_ride,
    _seed_client_in,
    _seed_tenant_client,
    _session_factory,
    _staff_client,
)


def _ride(status=RideStatus.COMPLETED, *, paid: bool = False):
    _cid, tenant = _seed_tenant_client("payflag")
    client_id = _seed_client_in(tenant)
    rid = _make_ride(tenant, client_id=client_id, status=status)
    if paid:

        async def go():
            eng, Sf = _session_factory()
            try:
                async with Sf() as db:
                    r = await db.get(Ride, rid)
                    r.paid = True
                    await db.commit()
            finally:
                await eng.dispose()

        asyncio.run(go())
    return tenant, rid


def test_method_on_a_completed_ride_marks_it_paid():
    """THE fix: tapping "Venmo" on a finished ride is recording that you got paid."""
    tenant, rid = _ride(RideStatus.COMPLETED)
    c = _staff_client(tenant)
    body = c.patch(f"/api/v1/rides/{rid}", json={"payment_method": "venmo"}).json()
    assert body["paid"] is True
    assert body["paid_at"] is not None
    assert body["payment_method"] == "venmo"


def test_method_on_a_future_ride_does_not_mark_it_paid():
    """Picking how they WILL pay is planning — the money hasn't moved."""
    tenant, rid = _ride(RideStatus.CONFIRMED)
    c = _staff_client(tenant)
    body = c.patch(f"/api/v1/rides/{rid}", json={"payment_method": "venmo"}).json()
    assert body["paid"] is False
    assert body["paid_at"] is None


def test_explicit_unpaid_in_the_same_request_wins():
    """"I'm recording the method but they still owe me" must stay possible."""
    tenant, rid = _ride(RideStatus.COMPLETED)
    c = _staff_client(tenant)
    body = c.patch(
        f"/api/v1/rides/{rid}", json={"payment_method": "venmo", "paid": False}
    ).json()
    assert body["paid"] is False


def test_marking_unpaid_afterwards_still_works():
    """The flag stays a toggle: the auto-mark is undoable in one tap."""
    tenant, rid = _ride(RideStatus.COMPLETED)
    c = _staff_client(tenant)
    assert c.patch(f"/api/v1/rides/{rid}", json={"payment_method": "cash"}).json()["paid"]
    body = c.patch(f"/api/v1/rides/{rid}", json={"paid": False}).json()
    assert body["paid"] is False
    assert body["paid_at"] is None


def test_already_paid_keeps_its_original_paid_at():
    """Changing the method on a settled ride must not rewrite when it was paid."""
    tenant, rid = _ride(RideStatus.COMPLETED, paid=True)
    c = _staff_client(tenant)
    first = c.patch(f"/api/v1/rides/{rid}", json={"paid": True}).json()["paid_at"]
    body = c.patch(f"/api/v1/rides/{rid}", json={"payment_method": "zelle"}).json()
    assert body["paid"] is True
    assert body["paid_at"] == first


def test_completing_and_recording_the_method_in_one_request_marks_paid():
    """Finishing the ride and recording payment together is the common real flow."""
    tenant, rid = _ride(RideStatus.EN_ROUTE)
    c = _staff_client(tenant)
    body = c.patch(
        f"/api/v1/rides/{rid}", json={"status": "completed", "payment_method": "cash"}
    ).json()
    assert body["paid"] is True


def test_tip_alone_does_not_mark_a_ride_paid():
    """A tip can be recorded before the fare is settled — that is not collection."""
    tenant, rid = _ride(RideStatus.COMPLETED)
    c = _staff_client(tenant)
    body = c.patch(f"/api/v1/rides/{rid}", json={"tip": 20}).json()
    assert body["paid"] is False
