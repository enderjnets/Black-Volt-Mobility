"""Discount code + campaign models: persist and read back."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://blackvolt:blackvolt_local_pass@127.0.0.1:5435/blackvolt"
)
os.environ.setdefault("MAPS_SIMULATED", "true")
os.environ.setdefault("PAYMENTS_SIMULATED", "true")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import datetime as dt  # noqa: E402

from app.models.discount import DiscountCampaign, DiscountCode  # noqa: E402


async def test_can_persist_discount_code():
    from app.db.base import dispose_engine, get_session_factory

    async with get_session_factory()() as db:
        row = DiscountCode(
            tenant_id=1,
            code="ENDER10",
            discount_pct=10.0,
            max_uses=5,
            expires_at=dt.datetime(2026, 12, 31, 23, 59),
            created_by_email="e@x.com",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        try:
            assert row.id is not None
            assert row.used_count == 0
            assert row.active is True
            # Validator must uppercase code
            assert row.code == "ENDER10"
        finally:
            # Clean up so the unique constraint on 'code' doesn't affect future runs.
            await db.delete(row)
            await db.commit()

    await dispose_engine()


async def test_can_persist_discount_campaign():
    from app.db.base import dispose_engine, get_session_factory

    async with get_session_factory()() as db:
        row = DiscountCampaign(
            tenant_id=1,
            name="Summer 2026",
            discount_pct=15.0,
            max_uses=100,
            expires_at=dt.datetime(2026, 8, 31, 23, 59),
            created_by_email="e@x.com",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        try:
            assert row.id is not None
            assert row.tenant_id == 1
        finally:
            # Clean up.
            await db.delete(row)
            await db.commit()

    await dispose_engine()


# ---------------------------------------------------------------------------
# Task 2: discount service tests
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from app.services import discounts as D  # noqa: E402
from app.services.discounts import DiscountError  # noqa: E402


def _future():
    return dt.datetime(2030, 1, 1, 0, 0)


@pytest.fixture
async def db():
    from sqlalchemy import delete as sa_delete

    from app.db.base import get_session_factory
    from app.models.discount import DiscountCampaign, DiscountCode

    async with get_session_factory()() as session:
        yield session
        await session.execute(sa_delete(DiscountCode))
        await session.execute(sa_delete(DiscountCampaign))
        await session.commit()


async def test_create_code_uppercases_and_defaults(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="ender10",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    assert c.code == "ENDER10"
    assert c.used_count == 0 and c.active is True


async def test_create_code_generates_when_blank(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    assert len(c.code) >= 6


async def test_driver_pct_cap_enforced(db):
    with pytest.raises(DiscountError) as ei:
        await D.create_code(db, tenant_id=1, is_admin=False, code="BIG",
                            discount_pct=60, max_uses=1, expires_at=_future(),
                            created_by_email="e@x.com")
    assert ei.value.reason == "pct_too_high"


async def test_admin_pct_uncapped(db):
    c = await D.create_code(db, tenant_id=1, is_admin=True, code="FREE",
                            discount_pct=100, max_uses=1, expires_at=_future(),
                            created_by_email="a@x.com")
    assert c.discount_pct == 100


async def test_duplicate_code_rejected(db):
    await D.create_code(db, tenant_id=1, is_admin=False, code="DUP",
                        discount_pct=10, max_uses=1, expires_at=_future(),
                        created_by_email="e@x.com")
    with pytest.raises(DiscountError) as ei:
        await D.create_code(db, tenant_id=1, is_admin=False, code="dup",
                            discount_pct=10, max_uses=1, expires_at=_future(),
                            created_by_email="e@x.com")
    assert ei.value.reason == "duplicate"


async def test_validate_rejects_expired_and_not_found(db):
    await D.create_code(db, tenant_id=1, is_admin=False, code="OLD",
                        discount_pct=10, max_uses=5,
                        expires_at=dt.datetime(2000, 1, 1), created_by_email="e@x.com")
    with pytest.raises(DiscountError) as ei:
        await D.validate_code(db, "OLD")
    assert ei.value.reason == "expired"

    with pytest.raises(DiscountError) as ei:
        await D.validate_code(db, "NOPE")
    assert ei.value.reason == "not_found"


async def test_validate_lookup_is_case_insensitive(db):
    await D.create_code(db, tenant_id=1, is_admin=False, code="MiX",
                        discount_pct=10, max_uses=5, expires_at=_future(),
                        created_by_email="e@x.com")
    row = await D.validate_code(db, "mix")
    assert row.code == "MIX"


async def test_redeem_increments_and_blocks_at_max(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="ONE",
                            discount_pct=10, max_uses=1, expires_at=_future(),
                            created_by_email="e@x.com")
    await D.redeem(db, c)
    with pytest.raises(DiscountError) as ei:
        await D.validate_code(db, "ONE")
    assert ei.value.reason == "exhausted"


async def test_campaign_generates_one_code_per_driver(db):
    camp, codes = await D.create_campaign(db, name="SUMMER25", discount_pct=15,
                                          max_uses=10, expires_at=_future(),
                                          created_by_email="a@x.com",
                                          created_by_tenant_id=1,
                                          driver_tenant_ids=[1, 2])
    assert camp.id is not None
    assert len(codes) == 2
    assert all(c.campaign_id == camp.id for c in codes)
    assert len({c.code for c in codes}) == 2


async def test_campaign_sets_tenant_id(db):
    camp, _ = await D.create_campaign(db, name="TENANTTEST", discount_pct=10,
                                      max_uses=5, expires_at=_future(),
                                      created_by_email="a@x.com",
                                      created_by_tenant_id=1,
                                      driver_tenant_ids=[1])
    assert camp.tenant_id == 1


async def test_list_codes_returns_for_tenant(db):
    await D.create_code(db, tenant_id=1, is_admin=False, code="LIST1",
                        discount_pct=10, max_uses=5, expires_at=_future(),
                        created_by_email="e@x.com")
    await D.create_code(db, tenant_id=2, is_admin=False, code="LIST2",
                        discount_pct=10, max_uses=5, expires_at=_future(),
                        created_by_email="e@x.com")
    codes = await D.list_codes(db, 1)
    code_strs = {c.code for c in codes}
    assert "LIST1" in code_strs
    assert "LIST2" not in code_strs


async def test_set_active_toggles_inactive(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="TOGGLE",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    toggled = await D.set_active(db, 1, c.id, False)
    assert toggled.active is False
    with pytest.raises(DiscountError) as ei:
        await D.validate_code(db, "TOGGLE")
    assert ei.value.reason == "inactive"


async def test_delete_code_removes_it(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="GONE",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    await D.delete_code(db, 1, c.id)
    with pytest.raises(DiscountError) as ei:
        await D.validate_code(db, "GONE")
    assert ei.value.reason == "not_found"


# ---------------------------------------------------------------------------
# FIX 2: percentage lower bound (< 1 raises pct_out_of_range)
# ---------------------------------------------------------------------------

async def test_pct_fractional_rejected(db):
    with pytest.raises(DiscountError) as ei:
        await D.create_code(db, tenant_id=1, is_admin=True, code="HALF",
                            discount_pct=0.5, max_uses=1, expires_at=_future(),
                            created_by_email="a@x.com")
    assert ei.value.reason == "pct_out_of_range"


# ---------------------------------------------------------------------------
# FIX 1: collision-safe campaign code generation
# ---------------------------------------------------------------------------

async def test_campaign_collision_safe_retries(db, monkeypatch):
    """Suffix collision against an existing DB row triggers a retry; no IntegrityError."""
    call_count = 0

    def controlled_suffix():
        nonlocal call_count
        call_count += 1
        return "AAAA" if call_count == 1 else "BBBB"

    monkeypatch.setattr(D, "_gen_suffix", controlled_suffix)

    base = "SUMMER25"
    await D.create_code(db, tenant_id=99, is_admin=True, code=f"{base}-AAAA",
                        discount_pct=10, max_uses=1, expires_at=_future(),
                        created_by_email="seed@x.com")

    camp, codes = await D.create_campaign(
        db, name="SUMMER25", discount_pct=15, max_uses=10, expires_at=_future(),
        created_by_email="a@x.com", created_by_tenant_id=1, driver_tenant_ids=[1],
    )
    assert len(codes) == 1
    assert codes[0].code == f"{base}-BBBB"


async def test_campaign_raises_discount_error_on_exhausted_retries(db, monkeypatch):
    """All 10 retries collide → DiscountError('duplicate'), never IntegrityError."""
    monkeypatch.setattr(D, "_gen_suffix", lambda: "ZZZZ")

    base = "EXHAUST"
    await D.create_code(db, tenant_id=99, is_admin=True, code=f"{base}-ZZZZ",
                        discount_pct=10, max_uses=1, expires_at=_future(),
                        created_by_email="seed@x.com")

    with pytest.raises(DiscountError) as ei:
        await D.create_campaign(
            db, name="EXHAUST", discount_pct=15, max_uses=10, expires_at=_future(),
            created_by_email="a@x.com", created_by_tenant_id=1, driver_tenant_ids=[1],
        )
    assert ei.value.reason == "duplicate"


# ---------------------------------------------------------------------------
# FIX 3: cross-tenant isolation for set_active and delete_code
# ---------------------------------------------------------------------------

async def test_set_active_cross_tenant_rejected(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="T1TOGGLE",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    with pytest.raises(DiscountError) as ei:
        await D.set_active(db, tenant_id=2, code_id=c.id, active=False)
    assert ei.value.reason == "not_found"


async def test_delete_code_cross_tenant_rejected(db):
    c = await D.create_code(db, tenant_id=1, is_admin=False, code="T1DEL",
                            discount_pct=10, max_uses=5, expires_at=_future(),
                            created_by_email="e@x.com")
    with pytest.raises(DiscountError) as ei:
        await D.delete_code(db, tenant_id=2, code_id=c.id)
    assert ei.value.reason == "not_found"


# ---------------------------------------------------------------------------
# Task 4: discount handoff — ride is assigned to the code-owning driver tenant
# ---------------------------------------------------------------------------

async def test_discount_handoff_ride_to_driver_tenant(db):
    """RED→GREEN: a discount code owned by tenant 2 causes create_ride to
    hand the ride off to tenant 2, clear client_id, record discount_amount > 0,
    and increment used_count exactly once."""
    from sqlalchemy import delete as sa_delete

    from app.models import Ride
    from app.models.discount import DiscountCode
    from app.services.booking import create_ride

    # Create a code under the non-default tenant (tenant 2).
    code = await D.create_code(
        db,
        tenant_id=2,
        is_admin=True,
        code="HANDOFF10",
        discount_pct=10,
        max_uses=5,
        expires_at=_future(),
        created_by_email="driver@x.com",
    )
    assert code.tenant_id == 2

    # Call create_ride as if it came from tenant 1's booking flow.
    # No scheduled_at → calendar sync is skipped (best-effort guard).
    ride = await create_ride(
        db,
        tenant_id=1,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
        passenger_name="Test Passenger",
        passenger_phone="+13035551234",
        pax=2,
        discount_code="HANDOFF10",
    )

    try:
        # Handoff: ride must belong to tenant 2 (the code owner).
        assert ride.tenant_id == 2, f"expected tenant 2, got {ride.tenant_id}"
        # No CRM client link — passenger travels as guest on the driver's calendar.
        assert ride.client_id is None
        # Passenger contact must still be snapshotted on the ride.
        assert ride.passenger_name == "Test Passenger"
        assert ride.passenger_phone == "+13035551234"
        # Discount was applied.
        assert ride.discount_amount > 0, "expected discount_amount > 0"
        assert ride.discount_code_id == code.id
        # used_count must have incremented to 1.
        await db.refresh(code)
        assert code.used_count == 1, f"expected used_count=1, got {code.used_count}"
    finally:
        # Clean up the ride so conftest TRUNCATE isn't needed for this row.
        await db.delete(ride)
        await db.commit()
