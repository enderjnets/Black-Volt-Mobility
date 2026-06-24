"""Passenger self-service profile: GET/PATCH /api/v1/me/profile + onboarding gate.

The profile gate on /book needs: a passenger can read their own profile, complete
the data Google can't give us (phone, names, address, SMS consent), the phone is
normalized to E.164 server-side, and `profile_complete` flips true once first/last
name + phone are present. Scoping is by the session's client_id — never the body.
"""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import auth as authsvc  # noqa: E402

# Each seeded passenger gets its OWN throwaway tenant so these tests never touch
# the default/owner tenant that other suites query (client search/list). Created
# rows are torn down at module end to keep the shared dev DB clean.
_CREATED: list[tuple[int, int]] = []


def _seed_passenger(
    *, name=None, first_name=None, last_name=None, phone=None, sms_consent=False
) -> tuple[int, int]:
    """Insert a passenger Client in a fresh isolated tenant; return (client_id, tenant_id)."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client
    from app.services.tenancy import create_tenant_for

    async def go() -> tuple[int, int]:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                tenant = await create_tenant_for(db, name=f"pgtest-{os.urandom(4).hex()}")
                c = Client(
                    tenant_id=tenant.id, name=name, first_name=first_name,
                    last_name=last_name, phone=phone, sms_consent=sms_consent,
                    google_sub=f"sub-{os.urandom(6).hex()}",
                    email=f"pax-{os.urandom(4).hex()}@pgtest.local",
                )
                db.add(c)
                await db.commit()
                await db.refresh(c)
                _CREATED.append((c.id, tenant.id))
                return c.id, tenant.id
        finally:
            await eng.dispose()

    return asyncio.run(go())


@pytest.fixture(scope="module", autouse=True)
def _cleanup_seeded():
    """Delete the clients + throwaway tenants these tests create."""
    yield
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client, Tenant

    async def go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                for cid, tid in _CREATED:
                    await db.execute(delete(Client).where(Client.id == cid))
                    await db.execute(delete(Tenant).where(Tenant.id == tid))
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _passenger_client(client_id: int, tenant_id: int) -> TestClient:
    token = authsvc.make_token(
        role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id,
        email="pax@example.com", client_id=client_id,
    )
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    return c


# ─── model round-trip ────────────────────────────────────────────────────────
def test_sms_consent_defaults_false_and_names_persist():
    cid, tid = _seed_passenger(first_name="Ada", last_name="Lovelace")
    c = _passenger_client(cid, tid)
    r = c.get("/api/v1/me/profile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["sms_consent"] is False


# ─── auth ────────────────────────────────────────────────────────────────────
def test_profile_requires_auth():
    r = TestClient(app).get("/api/v1/me/profile")
    assert r.status_code in (401, 403)


def test_staff_token_cannot_use_passenger_profile():
    # An owner/dashboard token has no client_id → must be rejected.
    token = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=1, email="o@e.com")
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    assert c.get("/api/v1/me/profile").status_code in (401, 403)


# ─── read ────────────────────────────────────────────────────────────────────
def test_get_profile_shape_and_incomplete():
    cid, tid = _seed_passenger(first_name="No", last_name="Phone")  # no phone
    body = _passenger_client(cid, tid).get("/api/v1/me/profile").json()
    for key in ("first_name", "last_name", "name", "email", "phone",
                "home_address", "sms_consent", "profile_complete"):
        assert key in body
    assert body["profile_complete"] is False  # missing phone


# ─── update ──────────────────────────────────────────────────────────────────
def test_patch_completes_profile_and_recomputes_name():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    r = c.patch("/api/v1/me/profile", json={
        "first_name": "Grace", "last_name": "Hopper",
        "phone": "(303) 555-0142", "sms_consent": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first_name"] == "Grace"
    assert body["last_name"] == "Hopper"
    assert body["name"] == "Grace Hopper"          # recomputed
    assert body["phone"] == "+13035550142"          # normalized E.164
    assert body["sms_consent"] is True
    assert body["profile_complete"] is True


def test_patch_invalid_phone_returns_422():
    cid, tid = _seed_passenger(first_name="A", last_name="B")
    c = _passenger_client(cid, tid)
    r = c.patch("/api/v1/me/profile", json={"phone": "call-me"})
    assert r.status_code == 422, r.text


def test_patch_only_touches_own_client():
    other_cid, tid = _seed_passenger(first_name="Other", last_name="Person")
    mine_cid, _ = _seed_passenger(first_name="Me", last_name="Self")
    c = _passenger_client(mine_cid, tid)
    c.patch("/api/v1/me/profile", json={"first_name": "Changed"})
    # The other passenger's record is untouched.
    other = _passenger_client(other_cid, tid).get("/api/v1/me/profile").json()
    assert other["first_name"] == "Other"


def test_patch_home_address_persists_and_empty_clears():
    cid, tid = _seed_passenger(first_name="A", last_name="B", phone="+13035550142")
    c = _passenger_client(cid, tid)
    c.patch("/api/v1/me/profile", json={"home_address": "6000 S Fraser St, Aurora, CO"})
    assert c.get("/api/v1/me/profile").json()["home_address"] == "6000 S Fraser St, Aurora, CO"
    c.patch("/api/v1/me/profile", json={"home_address": ""})
    assert c.get("/api/v1/me/profile").json()["home_address"] is None


# ─── session reflects completeness ───────────────────────────────────────────
def test_me_endpoint_reports_profile_complete():
    cid, tid = _seed_passenger(first_name="A", last_name="B", phone="+13035550142")
    body = _passenger_client(cid, tid).get("/api/v1/auth/me").json()
    assert body.get("profile_complete") is True

    cid2, tid2 = _seed_passenger(first_name="C")  # no last name / phone
    body2 = _passenger_client(cid2, tid2).get("/api/v1/auth/me").json()
    assert body2.get("profile_complete") is False
