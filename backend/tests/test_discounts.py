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
