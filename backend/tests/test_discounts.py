"""Discount code + campaign models: persist and read back."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://blackvolt:blackvolt_local_pass@127.0.0.1:5435/blackvolt"
)

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
    codes = await D.list_codes(db, 1)
    assert any(c.code == "LIST1" for c in codes)


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
