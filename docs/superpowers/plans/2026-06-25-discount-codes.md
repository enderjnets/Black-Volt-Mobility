# Discount Codes + Reservation-Only Booking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/book` reservation-only (remove "Now") and add driver/admin-managed discount codes that lower the fare and hand the ride off to the code's owning driver.

**Architecture:** A new `discount_codes` table (tenant-scoped to the owning driver) plus a `discount_campaigns` table (admin, groups per-driver codes). A global `validate` endpoint backs the public booking field; `create_ride` applies the discount via the existing pricing line-item pattern and reassigns `ride.tenant_id` to the code's tenant (handoff). Driver/admin management lives in a new dashboard module that mirrors `Rates.tsx`/`Team.tsx`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Postgres 16, Pydantic v2, pytest, ruff (line 100); Next.js 14 App Router, TypeScript, client-side i18n; Playwright for E2E.

## Global Constraints

- Backend Python, `ruff check app` must pass (line length 100).
- Every new table/row is tenant-scoped except the **global** `validate` lookup; driver CRUD scoped via `resolve_tenant_id` (`backend/app/api/deps.py:90`).
- Discount `%`: **drivers 1–50**, **admins 1–100** — enforced **server-side**.
- Codes stored **UPPERCASE**, **globally unique**; lookup case-insensitive.
- **No stacking:** when a discount code applies, the loyalty discount is skipped.
- Migration naming: `NNNN_snake_name.py`, `down_revision = "0026_ride_preferences_snapshot"`; new models re-exported from `backend/app/models/__init__.py`; str-enums wrapped with `pg_enum()` from `app/db/base.py`.
- Both dashboard navs must be updated (`DashShell.tsx` desktop + `DriverTabBar.tsx` mobile).
- Version → `0.45.0` (`frontend/lib/version.ts`) + `CHANGELOG.md`.
- Local test DB is the published prod-style port `127.0.0.1:5435` (compose dev) — do NOT run tests against production. Commit with the standard Co-Authored-By/Claude-Session trailer. Branch: `feat-discount-codes`.

---

## File Structure

**Backend**
- `backend/app/models/discount.py` (new) — `DiscountCode`, `DiscountCampaign`.
- `backend/app/models/ride.py` (modify) — add `discount_code_id`, `discount_amount`.
- `backend/app/models/__init__.py` (modify) — re-export new models.
- `backend/migrations/versions/0027_discount_codes.py` (new).
- `backend/app/services/discounts.py` (new) — create/list/toggle/delete/validate/campaign.
- `backend/app/services/pricing.py` (modify) — discount-code line item + no-stacking.
- `backend/app/services/booking.py` (modify) — thread code through quote + create_ride handoff.
- `backend/app/api/v1/discounts.py` (new) — staff CRUD + `validate` + admin campaigns.
- `backend/app/api/v1/rides.py` (modify) — `discount_code` on `QuoteRequest`/`RideCreate`.
- `backend/app/main.py` (modify) — mount the discounts router.
- Tests: `backend/tests/test_discounts.py` (new), additions to `backend/tests/test_booking*.py`.

**Frontend**
- `frontend/components/bv/web/Booking.tsx` (modify) — remove Now; discount field.
- `frontend/lib/booking.ts` (modify) — `validateDiscount`, payload field, types.
- `frontend/components/bv/dash/Discounts.tsx` (new) — driver module + admin campaign section.
- `frontend/app/dashboard/discounts/page.tsx` (new) — route wrapper.
- `frontend/components/bv/dash/DashShell.tsx`, `frontend/components/bv/dash/DriverTabBar.tsx` (modify) — nav.
- `frontend/lib/i18n.tsx` (modify) — EN+ES keys.
- `frontend/lib/version.ts`, `CHANGELOG.md` (modify).

---

## Task 1: Models + migration (discount_codes, discount_campaigns, ride columns)

**Files:**
- Create: `backend/app/models/discount.py`
- Modify: `backend/app/models/ride.py`, `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/0027_discount_codes.py`
- Test: `backend/tests/test_discounts.py`

**Interfaces:**
- Produces: `DiscountCode(id, tenant_id, code, discount_pct, max_uses, used_count, expires_at, active, created_by_email, campaign_id, created_at)`; `DiscountCampaign(id, name, discount_pct, max_uses, expires_at, created_by_email, created_at)`; `Ride.discount_code_id`, `Ride.discount_amount`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_discounts.py`)

Mirror the async session fixture used by `backend/tests/test_booking*.py` (import the same `db`/`session` fixture). Then:

```python
import datetime as dt
from app.models.discount import DiscountCode, DiscountCampaign

async def test_can_persist_discount_code(db):
    row = DiscountCode(
        tenant_id=1, code="ENDER10", discount_pct=10.0, max_uses=5,
        expires_at=dt.datetime(2026, 12, 31, 23, 59), created_by_email="e@x.com",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    assert row.id is not None
    assert row.used_count == 0
    assert row.active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_discounts.py::test_can_persist_discount_code -v`
Expected: FAIL — `ModuleNotFoundError: app.models.discount`.

- [ ] **Step 3: Write the models** (`backend/app/models/discount.py`)

Follow the column style of `backend/app/models/rate_config.py` (Mapped types, `mapped_column`, server defaults, the project's `Base`/timestamp helpers — copy its imports).

```python
from __future__ import annotations
import datetime as dt
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DiscountCampaign(Base):
    __tablename__ = "discount_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DiscountCode(Base):
    __tablename__ = "discount_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    discount_pct: Mapped[float] = mapped_column(Float, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

> Confirm the tenants table name/PK by reading `backend/app/models/rate_config.py` (its `tenant_id` FK) and match it exactly.

- [ ] **Step 4: Add ride columns** (`backend/app/models/ride.py`)

Add alongside the existing fare columns:

```python
    discount_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_codes.id", ondelete="SET NULL"), nullable=True
    )
    discount_amount: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
```

- [ ] **Step 5: Re-export models** (`backend/app/models/__init__.py`)

Add: `from app.models.discount import DiscountCampaign, DiscountCode` and include both in `__all__` if one is present.

- [ ] **Step 6: Write the migration** (`backend/migrations/versions/0027_discount_codes.py`)

Copy the header shape from `0026_ride_preferences_snapshot.py`.

```python
"""discount codes + campaigns + ride discount columns"""
from alembic import op
import sqlalchemy as sa

revision = "0027_discount_codes"
down_revision = "0026_ride_preferences_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discount_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "discount_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_email", sa.String(length=255), nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("discount_campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_discount_codes_tenant_id", "discount_codes", ["tenant_id"])
    op.create_unique_constraint("uq_discount_codes_code", "discount_codes", ["code"])
    op.add_column("rides", sa.Column("discount_code_id", sa.Integer(), sa.ForeignKey("discount_codes.id", ondelete="SET NULL"), nullable=True))
    op.add_column("rides", sa.Column("discount_amount", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("rides", "discount_amount")
    op.drop_column("rides", "discount_code_id")
    op.drop_constraint("uq_discount_codes_code", "discount_codes", type_="unique")
    op.drop_index("ix_discount_codes_tenant_id", table_name="discount_codes")
    op.drop_table("discount_codes")
    op.drop_table("discount_campaigns")
```

- [ ] **Step 7: Apply migration + run test**

Run: `cd backend && alembic upgrade head && pytest tests/test_discounts.py::test_can_persist_discount_code -v`
Expected: migration applies; test PASSES.

- [ ] **Step 8: Verify reversibility**

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`
Expected: no errors both directions.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/discount.py backend/app/models/ride.py backend/app/models/__init__.py backend/migrations/versions/0027_discount_codes.py backend/tests/test_discounts.py
git commit -m "feat(discounts): models + migration 0027 (discount codes/campaigns + ride columns)"
```

---

## Task 2: Discount service (create / list / toggle / delete / validate / campaign)

**Files:**
- Create: `backend/app/services/discounts.py`
- Test: `backend/tests/test_discounts.py`

**Interfaces:**
- Consumes: `DiscountCode`, `DiscountCampaign` (Task 1).
- Produces:
  - `async def create_code(db, *, tenant_id, is_admin, code, discount_pct, max_uses, expires_at, created_by_email, campaign_id=None) -> DiscountCode`
  - `async def list_codes(db, tenant_id) -> list[DiscountCode]`
  - `async def set_active(db, tenant_id, code_id, active) -> DiscountCode`
  - `async def delete_code(db, tenant_id, code_id) -> None`
  - `async def validate_code(db, code) -> DiscountCode` (raises `DiscountError` with `.reason` in {`not_found`,`inactive`,`expired`,`exhausted`})
  - `async def redeem(db, code_row) -> None` (atomic `used_count += 1`)
  - `async def create_campaign(db, *, name, discount_pct, max_uses, expires_at, created_by_email, driver_tenant_ids) -> tuple[DiscountCampaign, list[DiscountCode]]`
  - `DRIVER_MAX_PCT = 50.0`; `class DiscountError(Exception)`; `def _gen_code() -> str`

- [ ] **Step 1: Write failing tests**

```python
import datetime as dt
import pytest
from app.services import discounts as D
from app.services.discounts import DiscountError

def _future():
    return dt.datetime(2030, 1, 1, 0, 0)

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

async def test_validate_rejects_expired_inactive_exhausted(db):
    expired = await D.create_code(db, tenant_id=1, is_admin=False, code="OLD",
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
                                          driver_tenant_ids=[1, 2])
    assert camp.id is not None
    assert len(codes) == 2
    assert all(c.campaign_id == camp.id for c in codes)
    assert len({c.code for c in codes}) == 2
```

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && pytest tests/test_discounts.py -v`
Expected: FAIL — `app.services.discounts` missing.

- [ ] **Step 3: Implement the service**

```python
from __future__ import annotations
import datetime as dt
import secrets
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.discount import DiscountCampaign, DiscountCode

DRIVER_MAX_PCT = 50.0
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class DiscountError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _gen_code() -> str:
    return "BV-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def create_code(db: AsyncSession, *, tenant_id: int, is_admin: bool, code: str,
                      discount_pct: float, max_uses: int, expires_at: dt.datetime,
                      created_by_email: str, campaign_id: int | None = None) -> DiscountCode:
    if discount_pct <= 0 or discount_pct > 100:
        raise DiscountError("pct_out_of_range")
    if not is_admin and discount_pct > DRIVER_MAX_PCT:
        raise DiscountError("pct_too_high")
    if max_uses < 1:
        raise DiscountError("max_uses_invalid")
    norm = (code or "").strip().upper() or _gen_code()
    existing = await db.scalar(select(DiscountCode).where(DiscountCode.code == norm))
    if existing is not None:
        raise DiscountError("duplicate")
    row = DiscountCode(tenant_id=tenant_id, code=norm, discount_pct=float(discount_pct),
                       max_uses=max_uses, expires_at=expires_at,
                       created_by_email=created_by_email, campaign_id=campaign_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_codes(db: AsyncSession, tenant_id: int) -> list[DiscountCode]:
    res = await db.scalars(
        select(DiscountCode).where(DiscountCode.tenant_id == tenant_id).order_by(DiscountCode.created_at.desc())
    )
    return list(res)


async def _get_owned(db: AsyncSession, tenant_id: int, code_id: int) -> DiscountCode:
    row = await db.scalar(
        select(DiscountCode).where(DiscountCode.id == code_id, DiscountCode.tenant_id == tenant_id)
    )
    if row is None:
        raise DiscountError("not_found")
    return row


async def set_active(db: AsyncSession, tenant_id: int, code_id: int, active: bool) -> DiscountCode:
    row = await _get_owned(db, tenant_id, code_id)
    row.active = active
    await db.commit()
    await db.refresh(row)
    return row


async def delete_code(db: AsyncSession, tenant_id: int, code_id: int) -> None:
    row = await _get_owned(db, tenant_id, code_id)
    await db.delete(row)
    await db.commit()


async def validate_code(db: AsyncSession, code: str) -> DiscountCode:
    norm = (code or "").strip().upper()
    row = await db.scalar(select(DiscountCode).where(DiscountCode.code == norm))
    if row is None:
        raise DiscountError("not_found")
    if not row.active:
        raise DiscountError("inactive")
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)
    if exp < _now():
        raise DiscountError("expired")
    if row.used_count >= row.max_uses:
        raise DiscountError("exhausted")
    return row


async def redeem(db: AsyncSession, code_row: DiscountCode) -> None:
    res = await db.execute(
        update(DiscountCode)
        .where(DiscountCode.id == code_row.id, DiscountCode.used_count < DiscountCode.max_uses)
        .values(used_count=DiscountCode.used_count + 1)
    )
    if res.rowcount == 0:
        raise DiscountError("exhausted")
    await db.commit()


async def create_campaign(db: AsyncSession, *, name: str, discount_pct: float, max_uses: int,
                          expires_at: dt.datetime, created_by_email: str,
                          driver_tenant_ids: list[int]) -> tuple[DiscountCampaign, list[DiscountCode]]:
    if discount_pct <= 0 or discount_pct > 100:
        raise DiscountError("pct_out_of_range")
    if not driver_tenant_ids:
        raise DiscountError("no_drivers")
    camp = DiscountCampaign(name=name.strip(), discount_pct=float(discount_pct),
                            max_uses=max_uses, expires_at=expires_at, created_by_email=created_by_email)
    db.add(camp)
    await db.flush()
    base = "".join(ch for ch in name.strip().upper() if ch.isalnum())[:12] or "PROMO"
    codes: list[DiscountCode] = []
    for tid in driver_tenant_ids:
        suffix = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        row = DiscountCode(tenant_id=tid, code=f"{base}-{suffix}", discount_pct=float(discount_pct),
                           max_uses=max_uses, expires_at=expires_at, created_by_email=created_by_email,
                           campaign_id=camp.id)
        db.add(row)
        codes.append(row)
    await db.commit()
    for c in codes:
        await db.refresh(c)
    await db.refresh(camp)
    return camp, codes
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && pytest tests/test_discounts.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/services/discounts.py
git add backend/app/services/discounts.py backend/tests/test_discounts.py
git commit -m "feat(discounts): code service (create/list/toggle/delete/validate/redeem/campaign)"
```

---

## Task 3: Pricing — discount-code line item + no stacking

**Files:**
- Modify: `backend/app/services/pricing.py` (the `loyalty_discount` block, ~lines 102-107)
- Test: `backend/tests/test_pricing*.py` (use the existing pricing test module; if none, add to `test_discounts.py`)

**Interfaces:**
- Consumes: existing `quote(rates, facts)`.
- Produces: `quote(...)` accepts an optional `discount_pct: float | None` (via `facts` or a new kwarg — match the existing signature style). When set (>0), appends `{"label": "discount_code", "amount": -amount, "pct": discount_pct}` and **skips** the loyalty line.

- [ ] **Step 1: Read `pricing.py:quote`** to learn the exact `facts`/`RouteFacts` shape and how `loyalty_discount` is gated, so the new param matches the existing pattern (prefer adding `discount_pct` to `RouteFacts` if loyalty is driven from there).

- [ ] **Step 2: Write failing test**

```python
from app.services import pricing

def test_discount_code_replaces_loyalty():
    rates = pricing.default_rates_for_test()   # use the helper the existing tests use
    facts = pricing.facts_for_test(miles=10, minutes=20, is_loyalty=True, discount_pct=20)
    q = pricing.quote(rates, facts)
    labels = [li["label"] for li in q["breakdown"]]
    assert "discount_code" in labels
    assert "loyalty_discount" not in labels
```

> Replace `default_rates_for_test`/`facts_for_test` with however the current pricing tests build inputs (read the test file first; do not invent helpers).

- [ ] **Step 3: Run to verify fail**

Run: `cd backend && pytest backend/tests -k discount_code_replaces_loyalty -v`
Expected: FAIL.

- [ ] **Step 4: Implement** — in `quote()`, before the loyalty block:

```python
    discount_pct = getattr(facts, "discount_pct", None)
    if discount_pct and discount_pct > 0:
        amount = round(subtotal * (discount_pct / 100.0), 2)
        breakdown.append({"label": "discount_code", "amount": -amount, "pct": discount_pct})
        total -= amount
    elif rates.loyalty_discount_pct and facts.is_loyalty:
        # existing loyalty block (unchanged)
        ...
```

> Use the same `subtotal`/`total` variables the existing block uses; keep loyalty as the `elif`.

- [ ] **Step 5: Run tests to verify pass** (and the full pricing suite)

Run: `cd backend && pytest backend/tests -k "pricing or discount" -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Lint + commit**

```bash
cd backend && ruff check app/services/pricing.py
git add backend/app/services/pricing.py backend/tests
git commit -m "feat(pricing): discount_code line item, replaces loyalty (no stacking)"
```

---

## Task 4: Booking integration — quote preview + create_ride handoff

**Files:**
- Modify: `backend/app/services/booking.py` (`build_quote`, `create_ride`)
- Test: `backend/tests/test_discounts.py` (handoff) + existing booking tests

**Interfaces:**
- Consumes: `validate_code`, `redeem` (Task 2); `quote` with `discount_pct` (Task 3).
- Produces: `build_quote(..., discount_code: str | None = None)` returns a breakdown reflecting the discount; `create_ride(..., discount_code: str | None = None)` applies it, sets `ride.tenant_id = code.tenant_id`, `client_id = None`, copies `passenger_name/phone`, sets `discount_code_id`/`discount_amount`, calls `redeem`.

- [ ] **Step 1: Write failing handoff test**

```python
async def test_create_ride_with_code_hands_off_to_owner_tenant(db):
    from app.services import discounts as D, booking
    await D.create_code(db, tenant_id=2, is_admin=False, code="ENDER10",
                        discount_pct=10, max_uses=5, expires_at=dt.datetime(2030,1,1),
                        created_by_email="e@x.com")
    ride = await booking.create_ride(
        db, tenant_id=1, pickup="DEN", dropoff="Aurora", pax=2,
        passenger_name="Joe", passenger_phone="+13035551234",
        discount_code="ender10",
    )  # match create_ride's real signature
    assert ride.tenant_id == 2          # handed off to the code's driver
    assert ride.client_id is None
    assert ride.discount_amount > 0
    refreshed = await D.validate_code  # used_count incremented
```

> Adapt the `create_ride` call to its real signature (read `booking.py:create_ride`). Drop the last stray line; instead assert `(await db.get(DiscountCode, code.id)).used_count == 1`.

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && pytest tests/test_discounts.py -k hands_off -v`
Expected: FAIL.

- [ ] **Step 3: Implement** in `create_ride` (after building the quote, before persisting):

```python
    code_row = None
    discount_amount = 0.0
    if discount_code:
        code_row = await discounts.validate_code(db, discount_code)  # raises DiscountError
        # quote already includes the discount line via build_quote(discount_pct=...)
        discount_amount = abs(next((li["amount"] for li in breakdown
                                    if li["label"] == "discount_code"), 0.0))
    ...
    ride = Ride(
        tenant_id=(code_row.tenant_id if code_row else tenant_id),
        client_id=(None if code_row else client_id),
        passenger_name=passenger_name, passenger_phone=passenger_phone,
        ...,
        discount_code_id=(code_row.id if code_row else None),
        discount_amount=discount_amount,
    )
    db.add(ride)
    await db.flush()
    if code_row:
        await discounts.redeem(db, code_row)
    await db.commit()
```

And in `build_quote`, thread `discount_code` → look up pct (`validate_code`) → pass `discount_pct` into the `facts`/`quote` call. Import `from app.services import discounts`. Map `DiscountError` to a 4xx at the API layer (Task 5).

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && pytest tests/test_discounts.py backend/tests/test_booking*.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check app/services/booking.py
git add backend/app/services/booking.py backend/tests/test_discounts.py
git commit -m "feat(booking): apply discount code, hand ride off to owning driver"
```

---

## Task 5: API router — staff CRUD + global validate + admin campaigns; wire into rides

**Files:**
- Create: `backend/app/api/v1/discounts.py`
- Modify: `backend/app/api/v1/rides.py` (add `discount_code` to `QuoteRequest`/`RideCreate`, thread to services; map `DiscountError`→422), `backend/app/main.py` (mount)
- Test: `backend/tests/test_discounts.py` (API-level via the test client used by `test_social_api.py`/`test_me_profile.py`)

**Interfaces:**
- Consumes: the service (Task 2), `require_staff`/`require_auth`/`require_admin`/`resolve_tenant_id`/`session_is_admin` from `backend/app/api/deps.py`.
- Produces routes (prefix `/discounts`, included under `/v1`):
  - `GET ""` (staff, own), `POST ""` (staff, create), `PATCH /{id}` (staff, `{active}`), `DELETE /{id}` (staff).
  - `POST /validate` (auth): body `{code}` → `{valid: true, discount_pct}` or 404/410.
  - `POST /campaigns` (admin): `{name, discount_pct, max_uses, expires_at, driver_tenant_ids}` → `{campaign, codes}`.
  - `GET /drivers` (admin): list `{tenant_id, email}` for the campaign picker (from `AllowedUser` where role=driver, active).

- [ ] **Step 1: Write failing API tests** (use the project's async httpx client fixture; copy from `backend/tests/test_social_api.py`):

```python
async def test_staff_creates_and_lists_code(client_staff):
    r = await client_staff.post("/v1/discounts", json={
        "code": "ENDER10", "discount_pct": 10, "max_uses": 5,
        "expires_at": "2030-01-01T00:00:00Z"})
    assert r.status_code == 201
    r2 = await client_staff.get("/v1/discounts")
    assert any(c["code"] == "ENDER10" for c in r2.json())

async def test_driver_over_cap_422(client_staff):
    r = await client_staff.post("/v1/discounts", json={
        "code": "BIG", "discount_pct": 60, "max_uses": 1,
        "expires_at": "2030-01-01T00:00:00Z"})
    assert r.status_code == 422

async def test_validate_endpoint(client_auth, seeded_code):
    r = await client_auth.post("/v1/discounts/validate", json={"code": seeded_code})
    assert r.status_code == 200 and r.json()["discount_pct"] > 0

async def test_campaign_admin_only(client_staff):
    r = await client_staff.post("/v1/discounts/campaigns", json={
        "name": "SUMMER25", "discount_pct": 15, "max_uses": 10,
        "expires_at": "2030-01-01T00:00:00Z", "driver_tenant_ids": [1]})
    assert r.status_code in (401, 403)
```

> Reuse whatever staff/admin/auth client fixtures exist; if only one exists, build the others by minting the right session cookie the way the existing tests do.

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && pytest tests/test_discounts.py -k "staff or validate or campaign" -v`
Expected: FAIL (404 routes).

- [ ] **Step 3: Implement the router** (`backend/app/api/v1/discounts.py`)

Mirror `backend/app/api/v1/team.py` for structure (router, Pydantic in/out, status codes). Pydantic models: `CodeIn(code: str = "", discount_pct: float, max_uses: int, expires_at: datetime)`, `CodeOut`, `CodePatch(active: bool)`, `ValidateIn(code: str)`, `CampaignIn(...)`. In each handler catch `DiscountError` and raise `HTTPException(422, detail=e.reason)` (use 404 for `not_found`, 410 for `expired`/`exhausted`/`inactive` in `/validate`). Determine admin via `session_is_admin(db, payload)`; pass `is_admin` into `create_code`. For `/campaigns` and `/drivers` depend on `require_admin`.

- [ ] **Step 4: Thread into rides** (`backend/app/api/v1/rides.py`): add `discount_code: str | None = None` to `QuoteRequest` (so `RideCreate` inherits it); pass to `build_quote`/`create_ride`; wrap calls so `DiscountError` → `HTTPException(422, detail=...)`.

- [ ] **Step 5: Mount** in `backend/app/main.py`:

```python
from app.api.v1 import discounts as discounts_api
app.include_router(discounts_api.router, prefix="/v1")
```

- [ ] **Step 6: Run tests to verify pass + full backend suite**

Run: `cd backend && pytest -q && ruff check app`
Expected: all PASS, lint clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/discounts.py backend/app/api/v1/rides.py backend/app/main.py backend/tests/test_discounts.py
git commit -m "feat(api): /v1/discounts CRUD + validate + admin campaigns; discount_code on rides/quote"
```

---

## Task 6: `/book` — remove "Now", reservation-only

**Files:**
- Modify: `frontend/components/bv/web/Booking.tsx` (~lines 254-281 toggle; date/time block ~314-342), `frontend/lib/i18n.tsx` (`book.now`)

- [ ] **Step 1: Default reservation mode.** In `Booking.tsx`, set the initial state `const [when] = useState("schedule")` (remove the setter usage tied to the toggle) and delete the Now/Schedule `<div>` button group (lines ~254-281).

- [ ] **Step 2: Always show date/time.** Change the `when === "schedule" && (...)` gate around the date/time block to render unconditionally. Make date required to advance: in the step-0 "continue" guard, block if `!date` and show the existing `schedErr` message.

- [ ] **Step 3: Remove dead i18n.** Delete `book.now` from EN (~line 160) and ES (~line 1012). Keep `book.when` (label) or relabel to `book.schedule`.

- [ ] **Step 4: Static check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 5: Playwright verify** (local) — load `/book`: no "Now" button; cannot proceed without a date.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/bv/web/Booking.tsx frontend/lib/i18n.tsx
git commit -m "feat(book): reservation-only (remove on-demand Now option)"
```

---

## Task 7: `/book` — discount code field + validate + re-quote

**Files:**
- Modify: `frontend/lib/booking.ts` (add `validateDiscount`, `discount_code` on `RideInput`/quote, types), `frontend/components/bv/web/Booking.tsx` (UI + state), `frontend/lib/i18n.tsx` (strings)

- [ ] **Step 1: API client** in `frontend/lib/booking.ts`:

```ts
export async function validateDiscount(code: string): Promise<{ valid: boolean; discount_pct: number }> {
  const res = await fetch(`${API}/v1/discounts/validate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    credentials: "include", body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}
```

Add `discount_code?: string` to `RideInput` (lines ~39-54) and to the quote request type/call.

- [ ] **Step 2: UI** — in the review/quote step add an input + "Aplicar" button bound to new state `code`, `codePct`, `codeErr`. On apply: `validateDiscount(code)` → on success set `codePct` and re-run `getQuote(... discount_code: code)` so the displayed total updates and shows the `-X%` line; on failure set `codeErr` (i18n message by status). Include `discount_code: code` in the `createRide` payload (only when applied).

- [ ] **Step 3: i18n** — add EN+ES: `book.discount.label`, `book.discount.apply`, `book.discount.applied`, `book.discount.invalid`, `book.discount.expired`.

- [ ] **Step 4: Static check**

Run: `cd frontend && npx tsc --noEmit && npx next lint`
Expected: 0 errors.

- [ ] **Step 5: Playwright verify** — applying a valid local code lowers the total; an invalid code shows the error.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/booking.ts frontend/components/bv/web/Booking.tsx frontend/lib/i18n.tsx
git commit -m "feat(book): discount code field with validate + re-quote"
```

---

## Task 8: Driver dashboard module — `/dashboard/discounts`

**Files:**
- Create: `frontend/components/bv/dash/Discounts.tsx`, `frontend/app/dashboard/discounts/page.tsx`
- Modify: `frontend/components/bv/dash/DashShell.tsx` (`NAV`), `frontend/components/bv/dash/DriverTabBar.tsx` (`MORE`), `frontend/lib/i18n.tsx`

- [ ] **Step 1: Route wrapper** (`page.tsx`) mirroring `frontend/app/dashboard/rates/page.tsx`:

```tsx
import Discounts from "@/components/bv/dash/Discounts";
export default function Page() { return <Discounts />; }
```

- [ ] **Step 2: Component** (`Discounts.tsx`) mirroring `Rates.tsx`/`Team.tsx`: fetch `GET /v1/discounts`; render a list (code, %, used/max, expiry, active toggle, delete); a create form with a **code** input + **Generar** button (client-side random fill, server still authoritative), `%`, max uses, expiry date. Calls: `POST /v1/discounts`, `PATCH /v1/discounts/{id}` `{active}`, `DELETE /v1/discounts/{id}`. Show the driver cap hint (≤50%).

- [ ] **Step 3: Nav (both)** — `DashShell.tsx` `NAV` (add `{ seg: "discounts", href: "/dashboard/discounts", icon: <ticket icon>, key: "dash.nav.discounts" }`) and `DriverTabBar.tsx` `MORE`. Add `dash.title.discounts` + `dash.nav.discounts` to i18n EN+ES.

- [ ] **Step 4: Static check**

Run: `cd frontend && npx tsc --noEmit && npx next lint`
Expected: 0 errors.

- [ ] **Step 5: Playwright verify** (driver token, 3 viewports 390/820/1200): module reachable from sidebar + tab bar; create custom + generated code; %>50 shows server error; toggle/delete work.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/bv/dash/Discounts.tsx frontend/app/dashboard/discounts/page.tsx frontend/components/bv/dash/DashShell.tsx frontend/components/bv/dash/DriverTabBar.tsx frontend/lib/i18n.tsx
git commit -m "feat(dashboard): driver discount-codes module"
```

---

## Task 9: Admin campaign section + version bump

**Files:**
- Modify: `frontend/components/bv/dash/Discounts.tsx` (admin section gated by `me.is_admin`), `frontend/lib/i18n.tsx`, `frontend/lib/version.ts`, `CHANGELOG.md`

- [ ] **Step 1: Driver picker data** — fetch `GET /v1/discounts/drivers` (admin) for the multi-select.

- [ ] **Step 2: Campaign form** (only when `me.is_admin`): name, % (no cap), max uses, expiry, driver multi-select (all / selected). Submit `POST /v1/discounts/campaigns`; render the generated per-driver codes.

- [ ] **Step 3: i18n** — `dash.discounts.campaign.*` EN+ES.

- [ ] **Step 4: Version** — `frontend/lib/version.ts` → `CURRENT_VERSION = "0.45.0"` + changelog entry object; prepend a `## 0.45.0` section to `CHANGELOG.md` (reservation-only + discount codes + admin campaigns).

- [ ] **Step 5: Static check**

Run: `cd frontend && npx tsc --noEmit && npx next lint`
Expected: 0 errors.

- [ ] **Step 6: Playwright verify** (admin token): campaign for selected drivers generates one code per driver.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/bv/dash/Discounts.tsx frontend/lib/i18n.tsx frontend/lib/version.ts CHANGELOG.md
git commit -m "feat(dashboard): admin discount campaigns + v0.45.0"
```

---

## Task 10: Security review + integration verification

- [ ] **Step 1: Run the security-review** skill over the full branch diff. Confirm: `%` cap server-side; driver CRUD scoped by `resolve_tenant_id`; `/validate` leaks only `{valid, discount_pct}`; campaigns `require_admin`; atomic `redeem`; handoff sets `client_id=null` (no cross-tenant client leak).

- [ ] **Step 2: Full backend suite + lint**

Run: `cd backend && pytest -q && ruff check app`
Expected: green.

- [ ] **Step 3: Frontend static**

Run: `cd frontend && npx tsc --noEmit && npx next lint`
Expected: green.

- [ ] **Step 4: E2E Playwright** end-to-end against a locally running stack: book a ride with a driver code → ride lands in that driver's dashboard; verify `/book` has no Now and date is required.

- [ ] **Step 5: Open PR** (do not deploy until the user approves):

```bash
git push -u origin feat-discount-codes
gh pr create --title "feat: reservation-only booking + discount codes (v0.45.0)" --body "..."
```

---

## Self-Review

- **Spec coverage:** remove Now (T6) ✓; discount field on /book (T7) ✓; per-driver codes scoped by tenant (T1/T2/T5) ✓; max uses + expiry + % (T1/T2) ✓; custom-or-generate (T2 `_gen_code`, T8 button) ✓; no stacking (T3) ✓; driver cap 50 / admin 100 (T2/T5) ✓; handoff (T4) ✓; admin multi-driver campaigns one-code-per-driver (T2/T5/T9) ✓; migration 0027 reversible (T1) ✓; security-review (T10) ✓.
- **Placeholders:** the `"..."` in T5/T9 PR body and the `RideInput` line refs point to real, named locations; pricing/booking test helpers are flagged "read the existing test file first" rather than invented — implementers must match real signatures.
- **Type consistency:** service signatures in Task 2 `Produces` are reused verbatim by Tasks 4 and 5; `DiscountError.reason` strings are the same set across validate/redeem/create.

## Notes
- Deploy (rebuild backend incl. migration 0027 + frontend, VPS flow) only after the user approves the PR and verification passes.
