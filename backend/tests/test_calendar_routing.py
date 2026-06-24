"""Per-tenant calendar routing: admin → shared calendar, member → own calendar,
unconnected member → skipped."""
import asyncio
import os
import types

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")
os.environ.setdefault("MAPS_SIMULATED", "true")

from datetime import UTC, datetime, timedelta  # noqa: E402

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.models import AllowedUser, CalendarCredential, RideStatus  # noqa: E402
from app.models.allowed_user import ROLE_ADMIN, ROLE_DRIVER  # noqa: E402
from app.services import booking  # noqa: E402
from app.services.tenancy import create_tenant_for, get_default_tenant  # noqa: E402


def _session_maker():
    eng = create_async_engine(os.environ["DATABASE_URL"])
    return eng, async_sessionmaker(eng, expire_on_commit=False)


def _ride(tenant_id: int):
    """A minimal ride stand-in — routing only reads tenant_id; the skip-path of
    sync also reads scheduled_at/status."""
    return types.SimpleNamespace(
        tenant_id=tenant_id,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        status=RideStatus.CONFIRMED,
        google_event_id=None,
        id=0,
    )


async def _mk_driver_tenant(db, *, role=ROLE_DRIVER, email="route-drv@bv.test"):
    t = await create_tenant_for(db, name="Route Test Driver")
    db.add(AllowedUser(email=email, role=role, active=True, tenant_id=t.id))
    await db.commit()
    return t


async def _cleanup(db, tenant_ids, emails):
    await db.execute(
        delete(CalendarCredential).where(CalendarCredential.tenant_id.in_(tenant_ids))
    )
    await db.execute(delete(AllowedUser).where(AllowedUser.email.in_(emails)))
    from app.models import Tenant

    await db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    await db.commit()


def test_default_tenant_routes_to_shared_calendar():
    async def go():
        eng, Sf = _session_maker()
        try:
            async with Sf() as db:
                default = await get_default_tenant(db)
                assert await booking._tenant_is_admin(db, default.id) is True
                route = await booking._calendar_route(db, _ride(default.id))
                assert route is not None
                svc, cal, attendees = route
                # Shared route: global service (None here) + GOOGLE_CALENDAR_ID.
                assert svc is None
                assert cal == get_settings().GOOGLE_CALENDAR_ID
        finally:
            await eng.dispose()

    asyncio.run(go())


def test_admin_owned_tenant_routes_to_shared_calendar():
    async def go():
        eng, Sf = _session_maker()
        email = "route-admin@bv.test"
        tids = []
        try:
            async with Sf() as db:
                t = await _mk_driver_tenant(db, role=ROLE_ADMIN, email=email)
                tids.append(t.id)
                assert await booking._tenant_is_admin(db, t.id) is True
                route = await booking._calendar_route(db, _ride(t.id))
                assert route is not None
                assert route[1] == get_settings().GOOGLE_CALENDAR_ID
                await _cleanup(db, tids, [email])
        finally:
            await eng.dispose()

    asyncio.run(go())


def test_unconnected_member_is_skipped():
    async def go():
        eng, Sf = _session_maker()
        email = "route-unconn@bv.test"
        tids = []
        try:
            async with Sf() as db:
                t = await _mk_driver_tenant(db, role=ROLE_DRIVER, email=email)
                tids.append(t.id)
                assert await booking._tenant_is_admin(db, t.id) is False
                # No CalendarCredential → skip (None).
                assert await booking._calendar_route(db, _ride(t.id)) is None
                await _cleanup(db, tids, [email])
        finally:
            await eng.dispose()

    asyncio.run(go())


def test_tenant_admin_classification_is_deterministic():
    """Routing must not depend on row order: any ACTIVE admin owner ⇒ shared
    calendar; an inactive admin row is ignored."""

    async def go():
        eng, Sf = _session_maker()
        emails = ["det-drv@bv.test", "det-adm@bv.test", "det-inact@bv.test"]
        tids = []
        try:
            async with Sf() as db:
                # Tenant with BOTH a driver and an active admin owner → admin/shared.
                t = await create_tenant_for(db, name="Route Test Det")
                tids.append(t.id)
                db.add(AllowedUser(email=emails[0], role=ROLE_DRIVER, active=True, tenant_id=t.id))
                db.add(AllowedUser(email=emails[1], role=ROLE_ADMIN, active=True, tenant_id=t.id))
                await db.commit()
                assert await booking._tenant_is_admin(db, t.id) is True

                # Tenant whose only admin row is INACTIVE → NOT admin (own calendar).
                t2 = await create_tenant_for(db, name="Route Test Det2")
                tids.append(t2.id)
                db.add(
                    AllowedUser(email=emails[2], role=ROLE_ADMIN, active=False, tenant_id=t2.id)
                )
                await db.commit()
                assert await booking._tenant_is_admin(db, t2.id) is False

                await _cleanup(db, tids, emails)
        finally:
            await eng.dispose()

    asyncio.run(go())


def test_connected_member_routes_to_own_calendar():
    async def go():
        eng, Sf = _session_maker()
        email = "route-conn@bv.test"
        tids = []
        try:
            async with Sf() as db:
                t = await _mk_driver_tenant(db, role=ROLE_DRIVER, email=email)
                tids.append(t.id)
                db.add(
                    CalendarCredential(
                        tenant_id=t.id,
                        refresh_token_enc="enc-placeholder",
                        google_email=email,
                        calendar_id="member-cal@gmail.com",
                    )
                )
                await db.commit()
                route = await booking._calendar_route(db, _ride(t.id))
                assert route is not None
                svc, cal, attendees = route
                # Simulated mode: no real Google service, but the target calendar
                # is the MEMBER's own — not the shared one.
                assert cal == "member-cal@gmail.com"
                assert cal != get_settings().GOOGLE_CALENDAR_ID
                assert attendees is None  # no global invitees on a member calendar
                await _cleanup(db, tids, [email])
        finally:
            await eng.dispose()

    asyncio.run(go())


def test_sync_skips_unconnected_member(monkeypatch):
    """sync_ride_to_calendar must NOT call upsert for an unconnected member."""

    async def go():
        eng, Sf = _session_maker()
        email = "route-skip@bv.test"
        tids = []
        called = {"upsert": 0}

        from app.services import calendar as cal_mod

        def _spy(*a, **k):
            called["upsert"] += 1
            return "SIM-EVT-should-not-happen"

        monkeypatch.setattr(cal_mod, "upsert_event", _spy)
        try:
            async with Sf() as db:
                t = await _mk_driver_tenant(db, role=ROLE_DRIVER, email=email)
                tids.append(t.id)
                await booking.sync_ride_to_calendar(db, _ride(t.id))
                assert called["upsert"] == 0
                await _cleanup(db, tids, [email])
        finally:
            await eng.dispose()

    asyncio.run(go())
