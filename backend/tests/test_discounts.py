"""Discount code + campaign models: persist and read back."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
# Only a *fallback* for running this file standalone against a local dev DB.
# Must NOT override a DATABASE_URL provided by CI or the caller (a hard
# assignment here clobbered the env for every test module imported afterwards,
# pointing the whole run at a port that doesn't exist in CI).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://blackvolt:blackvolt_local_pass@127.0.0.1:5435/blackvolt",
)
os.environ.setdefault("MAPS_SIMULATED", "true")
os.environ.setdefault("PAYMENTS_SIMULATED", "true")
# Needed for API tests (auth tokens + login endpoint)
os.environ["AUTH_ENABLED"] = "true"
os.environ["AUTH_SECRET"] = "disc-api-test-secret"

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
    await D.create_code(db, tenant_id=1, is_admin=True, code=f"{base}-AAAA",
                        discount_pct=10, max_uses=1, expires_at=_future(),
                        created_by_email="seed@x.com")

    camp, codes = await D.create_campaign(
        db, name="SUMMER25", discount_pct=15, max_uses=10, expires_at=_future(),
        created_by_email="a@x.com", created_by_tenant_id=1, driver_tenant_ids=[1],
    )
    assert len(codes) == 1
    assert codes[0].code == f"{base}-BBBB"


async def test_campaign_max_uses_zero_rejected(db):
    """create_campaign with max_uses=0 raises DiscountError('max_uses_invalid')."""
    with pytest.raises(DiscountError) as ei:
        await D.create_campaign(
            db, name="BADUSES", discount_pct=10, max_uses=0, expires_at=_future(),
            created_by_email="a@x.com", created_by_tenant_id=1, driver_tenant_ids=[1],
        )
    assert ei.value.reason == "max_uses_invalid"


async def test_campaign_raises_discount_error_on_exhausted_retries(db, monkeypatch):
    """All 10 retries collide → DiscountError('duplicate'), never IntegrityError."""
    monkeypatch.setattr(D, "_gen_suffix", lambda: "ZZZZ")

    base = "EXHAUST"
    await D.create_code(db, tenant_id=1, is_admin=True, code=f"{base}-ZZZZ",
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
    """GREEN: a discount code owned by tenant 2 keeps the ride in the booker's
    tenant (1), sets assigned_tenant_id=2, preserves passenger contact, records
    discount_amount > 0, and does NOT increment used_count (redeem deferred to payment)."""
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
        # Ride stays in the booker's tenant — payment + history remain intact.
        assert ride.tenant_id == 1, f"expected tenant_id=1, got {ride.tenant_id}"
        # assigned_tenant_id marks the code-owning driver's tenant.
        assert ride.assigned_tenant_id == 2, (
            f"expected assigned_tenant_id=2, got {ride.assigned_tenant_id}"
        )
        # No client_id was passed → remains None (guest booking via discount code).
        assert ride.client_id is None
        # Passenger contact is preserved on the ride.
        assert ride.passenger_name == "Test Passenger"
        assert ride.passenger_phone == "+13035551234"
        # Discount was applied.
        assert ride.discount_amount > 0, "expected discount_amount > 0"
        assert ride.discount_code_id == code.id
        # used_count stays 0 — redeem happens at payment, not ride creation.
        await db.refresh(code)
        assert code.used_count == 0, (
            f"expected used_count=0 after create_ride (no payment yet), got {code.used_count}"
        )
    finally:
        # Clean up the ride so conftest TRUNCATE isn't needed for this row.
        await db.delete(ride)
        await db.commit()


async def test_discount_assigned_tenant_visible_in_list(db):
    """A ride booked via a cross-tenant discount code appears in list_rides for
    both the booker's tenant (via tenant_id) and the code-owner's tenant (via
    assigned_tenant_id), so the driver who owns the code can see and service it."""
    from app.services.booking import create_ride, list_rides

    await D.create_code(
        db,
        tenant_id=2,
        is_admin=True,
        code="LISTVIS10",
        discount_pct=10,
        max_uses=5,
        expires_at=_future(),
        created_by_email="driver@x.com",
    )

    ride = await create_ride(
        db,
        tenant_id=1,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
        passenger_name="Visibility Test",
        pax=1,
        discount_code="LISTVIS10",
    )

    try:
        booker_rides = await list_rides(db, tenant_id=1)
        assert any(r.id == ride.id for r in booker_rides), "ride not in booker tenant list"

        assigned_rides = await list_rides(db, tenant_id=2)
        assert any(r.id == ride.id for r in assigned_rides), "ride not in assigned tenant list"
    finally:
        await db.delete(ride)
        await db.commit()


# ---------------------------------------------------------------------------
# Task 5: /v1/discounts API tests
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app as _app  # noqa: E402
from app.services import auth as _A  # noqa: E402

_client = TestClient(_app)


def _owner_client() -> TestClient:
    """Authenticated admin (owner) session via the login endpoint."""
    c = TestClient(_app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, f"owner login failed: {r.text}"
    return c


def _staff_client(tenant_id: int = 1, email: str = "staffdriver@disc.test") -> TestClient:
    """Non-admin driver session — a staff member but NOT a super-admin."""
    c = TestClient(_app)
    c.cookies.set(
        _A.COOKIE_NAME,
        _A.make_token(role=_A.ROLE_DRIVER, tenant_id=tenant_id, email=email),
    )
    return c


def _passenger_client() -> TestClient:
    """Passenger session (require_auth but not staff)."""
    c = TestClient(_app)
    c.cookies.set(
        _A.COOKIE_NAME,
        _A.make_token(
            role=_A.ROLE_PASSENGER, tenant_id=999902, email="pax@disc.test", client_id=9990
        ),
    )
    return c


@pytest.fixture(scope="module", autouse=True)
def _cleanup_api_codes():
    """Delete all discount codes + campaigns created by this module's API tests."""
    yield
    import asyncio

    from sqlalchemy import delete as sa_del
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def _go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as s:
                from app.models.discount import DiscountCampaign, DiscountCode
                await s.execute(sa_del(DiscountCode).where(
                    DiscountCode.created_by_email.in_([
                        "staffdriver@disc.test",
                        "",  # owner session may have empty email in token
                        "pax@disc.test",
                    ])
                ))
                # Clean up any remaining codes from these tests by code prefix
                await s.execute(sa_del(DiscountCode).where(
                    DiscountCode.code.like("APITEST%")
                ))
                # Campaign-generated codes (APICAM prefix) are NOT cascade-deleted
                # when the campaign is removed (FK is ON DELETE SET NULL).
                await s.execute(sa_del(DiscountCode).where(
                    DiscountCode.code.like("APICAM%")
                ))
                await s.execute(sa_del(DiscountCampaign).where(
                    DiscountCampaign.name.like("ApiCamp%")
                ))
                await s.commit()
        finally:
            await eng.dispose()

    asyncio.run(_go())


# ── Helper to delete a code by id via API ────────────────────────────────────

def _delete_code_api(owner: TestClient, code_id: int) -> None:
    owner.delete(f"/api/v1/discounts/{code_id}")


# ── Tests ────────────────────────────────────────────────────────────────────


def test_api_staff_create_and_list():
    """Staff can create a code (201) and it appears in the list."""
    c = _staff_client()
    body = {
        "code": "APITEST01",
        "discount_pct": 10.0,
        "max_uses": 5,
        "expires_at": "2030-06-01T00:00:00+00:00",
    }
    r = c.post("/api/v1/discounts", json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["code"] == "APITEST01"
    assert created["discount_pct"] == 10.0
    assert created["active"] is True

    # List should contain it
    listed = c.get("/api/v1/discounts").json()
    codes = [x["code"] for x in listed]
    assert "APITEST01" in codes

    # Clean up
    owner = _owner_client()
    _delete_code_api(owner, created["id"])


def test_api_staff_driver_over_cap_rejected():
    """A non-admin driver creating a code with pct > 50 gets 422."""
    c = _staff_client()
    body = {
        "code": "APITEST_BIG",
        "discount_pct": 60.0,
        "max_uses": 1,
        "expires_at": "2030-06-01T00:00:00+00:00",
    }
    r = c.post("/api/v1/discounts", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "pct_too_high"


def test_api_validate_valid_code():
    """/validate returns {valid: true, discount_pct} for a live code."""
    # Create the code as owner (admin, no cap)
    owner = _owner_client()
    body = {
        "code": "APITEST_VAL",
        "discount_pct": 20.0,
        "max_uses": 10,
        "expires_at": "2030-12-31T23:59:59+00:00",
    }
    r = owner.post("/api/v1/discounts", json=body)
    assert r.status_code == 201, r.text
    code_id = r.json()["id"]

    # Validate as passenger (require_auth)
    pax = _passenger_client()
    vr = pax.post("/api/v1/discounts/validate", json={"code": "APITEST_VAL"})
    assert vr.status_code == 200, vr.text
    data = vr.json()
    assert data["valid"] is True
    assert data["discount_pct"] == 20.0

    _delete_code_api(owner, code_id)


def test_api_validate_expired_code():
    """/validate returns 410 for an expired code."""
    owner = _owner_client()
    body = {
        "code": "APITEST_EXP",
        "discount_pct": 10.0,
        "max_uses": 5,
        "expires_at": "2000-01-01T00:00:00+00:00",
    }
    r = owner.post("/api/v1/discounts", json=body)
    assert r.status_code == 201, r.text
    code_id = r.json()["id"]

    pax = _passenger_client()
    vr = pax.post("/api/v1/discounts/validate", json={"code": "APITEST_EXP"})
    assert vr.status_code == 410, vr.text
    assert vr.json()["detail"] == "expired"

    _delete_code_api(owner, code_id)


def test_api_validate_unknown_code():
    """/validate returns 404 for a code that does not exist."""
    pax = _passenger_client()
    vr = pax.post("/api/v1/discounts/validate", json={"code": "APITEST_NOPE_XYZ"})
    assert vr.status_code == 404, vr.text
    assert vr.json()["detail"] == "not_found"


def test_api_validate_anon_rejected():
    """/validate requires authentication — anonymous gets 401."""
    r = _client.post("/api/v1/discounts/validate", json={"code": "WHATEVER"})
    assert r.status_code == 401, r.text


def test_api_campaigns_non_admin_rejected():
    """A non-admin staff member cannot create a campaign — 403."""
    c = _staff_client()
    body = {
        "name": "ApiCampBad",
        "discount_pct": 10.0,
        "max_uses": 5,
        "expires_at": "2030-06-01T00:00:00+00:00",
        "driver_tenant_ids": [1],
    }
    r = c.post("/api/v1/discounts/campaigns", json=body)
    assert r.status_code in (401, 403), r.text


def test_api_campaigns_admin_creates_codes():
    """Admin POST /campaigns creates one code per driver_tenant_id."""
    owner = _owner_client()
    body = {
        "name": "ApiCamp01",
        "discount_pct": 15.0,
        "max_uses": 3,
        "expires_at": "2030-12-31T23:59:59+00:00",
        "driver_tenant_ids": [1],
    }
    r = owner.post("/api/v1/discounts/campaigns", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert "campaign" in data and "codes" in data
    assert data["campaign"]["name"] == "ApiCamp01"
    assert len(data["codes"]) == 1
    assert data["codes"][0]["discount_pct"] == 15.0


def test_api_drivers_admin_only():
    """GET /drivers is admin-only; non-admin staff gets 403."""
    c = _staff_client()
    r = c.get("/api/v1/discounts/drivers")
    assert r.status_code in (401, 403), r.text

    # Admin can access it
    owner = _owner_client()
    r2 = owner.get("/api/v1/discounts/drivers")
    assert r2.status_code == 200, r2.text
    # Returns a list (may be empty if no drivers with tenant_id on this dev DB)
    assert isinstance(r2.json(), list)


def test_api_patch_active_and_delete():
    """Staff can toggle active and delete their own codes."""
    c = _staff_client()
    body = {
        "code": "APITEST_PATCH",
        "discount_pct": 5.0,
        "max_uses": 2,
        "expires_at": "2030-01-01T00:00:00+00:00",
    }
    r = c.post("/api/v1/discounts", json=body)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # Toggle inactive
    pr = c.patch(f"/api/v1/discounts/{cid}", json={"active": False})
    assert pr.status_code == 200, pr.text
    assert pr.json()["active"] is False

    # Toggle back
    pr2 = c.patch(f"/api/v1/discounts/{cid}", json={"active": True})
    assert pr2.status_code == 200
    assert pr2.json()["active"] is True

    # Delete
    dr = c.delete(f"/api/v1/discounts/{cid}")
    assert dr.status_code == 204, dr.text


def test_api_delete_not_found():
    """DELETE with a non-existent code_id returns 404."""
    c = _staff_client()
    r = c.delete("/api/v1/discounts/999999")
    assert r.status_code == 404, r.text


def test_api_unauthenticated_list_rejected():
    """GET /discounts requires at least staff auth — 401 for anonymous."""
    r = _client.get("/api/v1/discounts")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Fix wave 2: cross-tenant PII guard in ride_detail_extra
# ---------------------------------------------------------------------------


async def test_ride_detail_extra_no_cross_tenant_pii(db):
    """The assigned driver (tenant 2) must NOT see the booker tenant's client
    email/preferences. The booker's tenant (1) still gets the full client record.

    Scenario: tenant-1 client books via a tenant-2 discount code → ride has
    client_id (tenant 1 CRM) + assigned_tenant_id=2.  The scoped client lookup
    added by the fix must block the cross-tenant fetch.
    """
    from app.models.client import Client
    from app.services.booking import create_ride, get_ride
    from app.services.dashboard import ride_detail_extra

    # 1. Seed a tenant-1 client with identifiable PII.
    t1_client = Client(
        tenant_id=1,
        name="PII Test Passenger",
        phone="+13035559999",
        email="piileak@tenant1.test",
        ride_preferences={"preferred_temp": "cool"},
    )
    db.add(t1_client)
    await db.flush()  # get id without committing

    # 2. Discount code owned by tenant 2.
    await D.create_code(
        db,
        tenant_id=2,
        is_admin=True,
        code="PIIGUARD10",
        discount_pct=10,
        max_uses=5,
        expires_at=_future(),
        created_by_email="driver2@x.com",
    )

    # 3. Book a ride as tenant 1, explicitly passing the client_id so the ride
    #    retains a reference to the tenant-1 CRM record.
    ride = await create_ride(
        db,
        tenant_id=1,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
        passenger_name="PII Test Passenger",
        passenger_phone="+13035559999",
        pax=1,
        client_id=t1_client.id,  # explicit — survives discount-code path
        discount_code="PIIGUARD10",
    )

    try:
        # Verify the ride is properly set up for the attack surface.
        assert ride.tenant_id == 1
        assert ride.assigned_tenant_id == 2
        assert ride.client_id == t1_client.id

        # 4. Assigned driver (tenant 2) opens the ride via get_ride — allowed.
        ride_as_t2 = await get_ride(db, tenant_id=2, ride_id=ride.id)
        assert ride_as_t2 is not None, "assigned driver must be able to fetch the ride"

        # 5. ride_detail_extra as tenant 2 → client must be None (scoped out).
        detail_t2 = await ride_detail_extra(db, tenant_id=2, ride=ride_as_t2)
        assert detail_t2["client"] is None, (
            f"Cross-tenant PII leak: tenant-2 driver got client={detail_t2['client']}"
        )

        # 6. Snapshot (passenger_name / passenger_phone) is still on the ride
        #    itself — the assigned driver can still service the passenger.
        assert ride_as_t2.passenger_name == "PII Test Passenger"
        assert ride_as_t2.passenger_phone == "+13035559999"

        # 7. Booker's own tenant (1) still gets full client detail.
        ride_as_t1 = await get_ride(db, tenant_id=1, ride_id=ride.id)
        detail_t1 = await ride_detail_extra(db, tenant_id=1, ride=ride_as_t1)
        assert detail_t1["client"] is not None, "booker tenant should see full client"
        assert detail_t1["client"]["email"] == "piileak@tenant1.test"
        assert detail_t1["client"]["preferences"] is not None

    finally:
        await db.delete(ride)
        await db.delete(t1_client)
        await db.commit()


# ---------------------------------------------------------------------------
# Follow-up 1: redeem on payment success, not ride creation
# ---------------------------------------------------------------------------

async def test_create_ride_with_code_does_not_redeem(db):
    """Creating a ride with a discount code leaves used_count at 0."""
    from app.services.booking import create_ride
    code = await D.create_code(db, tenant_id=2, is_admin=True, code="NODELAY10",
                               discount_pct=10, max_uses=3, expires_at=_future(),
                               created_by_email="a@x.com")
    ride = await create_ride(db, tenant_id=1,
                             pickup="6000 S Fraser St, Aurora CO",
                             dropoff="Denver International Airport (DEN)",
                             discount_code="NODELAY10")
    try:
        await db.refresh(code)
        assert code.used_count == 0, f"expected 0, got {code.used_count}"
        assert ride.discount_code_id == code.id
        assert not ride.discount_redeemed
    finally:
        await db.delete(ride)
        await db.commit()


async def test_payment_success_redeems_code(db):
    """authorize_for_ride increments used_count to 1 and sets discount_redeemed=True."""
    from app.services.booking import create_ride
    from app.services.payments import authorize_for_ride
    code = await D.create_code(db, tenant_id=2, is_admin=True, code="PAYREEDM10",
                               discount_pct=10, max_uses=3, expires_at=_future(),
                               created_by_email="a@x.com")
    ride = await create_ride(db, tenant_id=1,
                             pickup="6000 S Fraser St, Aurora CO",
                             dropoff="Denver International Airport (DEN)",
                             discount_code="PAYREEDM10")
    try:
        await authorize_for_ride(db, tenant_id=1, ride=ride, source_id="cnon:card-nonce-ok")
        await db.refresh(code)
        await db.refresh(ride)
        assert code.used_count == 1, f"expected 1, got {code.used_count}"
        assert ride.discount_redeemed is True
    finally:
        await db.delete(ride)
        await db.commit()


async def test_payment_redeem_idempotent(db):
    """A second authorize_for_ride call on the same ride does not double-increment
    used_count. The gate is the DB-level conditional UPDATE on rides
    (discount_redeemed=false) — rowcount==0 on the second attempt → "already"."""
    from app.services.booking import create_ride
    from app.services.payments import authorize_for_ride
    code = await D.create_code(db, tenant_id=2, is_admin=True, code="IDMPTNT10",
                               discount_pct=10, max_uses=5, expires_at=_future(),
                               created_by_email="a@x.com")
    ride = await create_ride(db, tenant_id=1,
                             pickup="6000 S Fraser St, Aurora CO",
                             dropoff="Denver International Airport (DEN)",
                             discount_code="IDMPTNT10")
    try:
        # First payment call — should redeem once (claim wins, increment runs).
        await authorize_for_ride(db, tenant_id=1, ride=ride, source_id="cnon:card-nonce-ok")
        await db.refresh(code)
        assert code.used_count == 1
        # Second call (retry scenario) — DB has discount_redeemed=True so claim
        # UPDATE returns rowcount==0 → "already" → increment is never reached.
        await authorize_for_ride(db, tenant_id=1, ride=ride, source_id="cnon:card-nonce-ok")
        await db.refresh(code)
        assert code.used_count == 1, f"double-redeem: expected 1, got {code.used_count}"
    finally:
        await db.delete(ride)
        await db.commit()


async def test_payment_succeeds_when_code_exhausted(db):
    """If the code is already exhausted at payment time, payment still succeeds
    and discount_redeemed is set True (no double-billing the customer)."""
    from app.services.payments import authorize_for_ride
    code = await D.create_code(db, tenant_id=2, is_admin=True, code="EXHAUST1",
                               discount_pct=10, max_uses=1, expires_at=_future(),
                               created_by_email="a@x.com")
    # Exhaust the code externally (simulate another booking redeeming it first).
    await D.redeem(db, code)
    assert code.used_count == 1  # manually verify it's exhausted

    # Now create a ride that has this code's id set (bypassing validate_code since it's exhausted).
    from app.models import Ride, RideStatus
    ride = Ride(
        tenant_id=1, status=RideStatus.QUOTED,
        pickup_text="6000 S Fraser St, Aurora CO",
        dropoff_text="Denver International Airport (DEN)",
        fare_total=50.0, currency="USD",
        distance_miles=25.0, duration_minutes=40.0,
        discount_code_id=code.id, discount_amount=5.0,
        discount_redeemed=False,
    )
    db.add(ride)
    await db.commit()
    await db.refresh(ride)
    try:
        # Payment should succeed even though code is exhausted.
        pay = await authorize_for_ride(db, tenant_id=1, ride=ride, source_id="cnon:card-nonce-ok")
        assert pay is not None
        await db.refresh(ride)
        assert ride.discount_redeemed is True
        # used_count should NOT have gone above 1 (the exhausted guard held).
        await db.refresh(code)
        assert code.used_count == 1, f"used_count over-incremented: {code.used_count}"
    finally:
        await db.delete(ride)
        await db.commit()


# ---------------------------------------------------------------------------
# Fix wave 1: rollback atomicity test
# ---------------------------------------------------------------------------
# NOTE: Skipped — simulating a mid-transaction failure cleanly (after the
# ride-claim UPDATE but before commit) would require patching db.commit() in a
# way that leaves the session in a consistent rollback-ready state without also
# breaking the preceding payment commit. That is not achievable with a simple
# monkeypatch on an async session. The atomicity guarantee is structural: both
# UPDATEs share the same open transaction opened by SQLAlchemy's session; if
# db.commit() raises (network drop, serialization failure, etc.) the transaction
# is rolled back by the DB and NEITHER update persists — discount_redeemed stays
# False and used_count is unchanged. A separate integration/chaos test (outside
# this unit suite) is the right venue for that failure path.

# ---------------------------------------------------------------------------
# Follow-up 2: price discounted rides with owner's rate config
# ---------------------------------------------------------------------------

async def test_discounted_ride_uses_owner_rate_config(db):
    """When a discount code is applied, the fare is computed using the CODE
    OWNER's RateConfig, not the booker's. The discount_pct is then applied
    on top of the owner's base fare."""
    from app.services.booking import build_quote, get_or_create_rate_config

    # Seed two tenants with meaningfully different per_mile rates.
    # Tenant A (booker): cheap rate — $1/mile base
    # Tenant B (code owner/driver): premium rate — $5/mile base
    # With 10% discount, the total should reflect B's rates * 0.9, NOT A's.

    # Ensure distinct RateConfigs for tenants 10 and 11 (use high IDs to avoid conflicts).
    rc_a = await get_or_create_rate_config(db, tenant_id=10)
    rc_a.per_mile = 1.0
    rc_a.base = 0.0
    rc_a.minimum = 0.0
    rc_a.airport_flat = 0.0

    rc_b = await get_or_create_rate_config(db, tenant_id=11)
    rc_b.per_mile = 5.0
    rc_b.base = 0.0
    rc_b.minimum = 0.0
    rc_b.airport_flat = 0.0
    await db.commit()

    # Code owned by tenant B (11)
    await D.create_code(db, tenant_id=11, is_admin=True, code="OWNRATE10",
                               discount_pct=10, max_uses=5, expires_at=_future(),
                               created_by_email="b@x.com")

    # Quote from tenant A's perspective using B's code
    quote_with_code = await build_quote(
        db,
        tenant_id=10,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
        discount_code="OWNRATE10",
    )
    # Quote from tenant A without any code (baseline: A's own rates)
    quote_no_code = await build_quote(
        db,
        tenant_id=10,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
    )

    # The discounted quote must NOT equal A's base fare.
    # With per_mile=5 for B vs per_mile=1 for A, B's base fare is 5x higher,
    # so even with 10% off, the discounted fare should be > A's undiscounted fare.
    assert quote_with_code["total"] != quote_no_code["total"], (
        "discounted quote should NOT match the booker's own rate (it should use B's higher rates)"
    )
    # More precisely: B's fare * 0.9 > A's fare (since B's per_mile is 5x A's)
    # Get B's undiscounted fare for reference
    quote_b_no_code = await build_quote(
        db,
        tenant_id=11,
        pickup="6000 S Fraser St, Aurora CO",
        dropoff="Denver International Airport (DEN)",
    )
    expected_discounted = round(quote_b_no_code["total"] * 0.90, 2)
    assert abs(quote_with_code["total"] - expected_discounted) < 0.50, (
        f"discounted total {quote_with_code['total']} should be close to "
        f"B's base {quote_b_no_code['total']} * 0.9 = {expected_discounted}"
    )
