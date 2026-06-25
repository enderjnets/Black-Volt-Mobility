"""Passenger saved-address book: CRUD under /api/v1/me/addresses.

A signed-in passenger manages multiple labeled addresses, exactly one marked
default. Scoping is by the session's client_id + tenant_id — never the body —
so a passenger can only ever see or mutate their own addresses; anything else
returns 404. The first address auto-becomes default; deleting the default
promotes the oldest remaining.
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
# the default/owner tenant other suites query. Rows are torn down at module end.
_CREATED: list[tuple[int, int]] = []


def _seed_passenger() -> tuple[int, int]:
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
                tenant = await create_tenant_for(db, name=f"addrtest-{os.urandom(4).hex()}")
                c = Client(
                    tenant_id=tenant.id,
                    first_name="Addr",
                    last_name="Book",
                    phone="+13035550142",
                    google_sub=f"sub-{os.urandom(6).hex()}",
                    email=f"pax-{os.urandom(4).hex()}@addrtest.local",
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
    """Delete the addresses, clients + throwaway tenants these tests create."""
    yield
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client, ClientAddress, Tenant

    async def go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                for cid, tid in _CREATED:
                    await db.execute(
                        delete(ClientAddress).where(ClientAddress.client_id == cid)
                    )
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


def _add(c: TestClient, address: str, label=None, is_default=None) -> dict:
    body: dict = {"address": address}
    if label is not None:
        body["label"] = label
    if is_default is not None:
        body["is_default"] = is_default
    r = c.post("/api/v1/me/addresses", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ─── auth ────────────────────────────────────────────────────────────────────
def test_addresses_require_passenger():
    assert TestClient(app).get("/api/v1/me/addresses").status_code in (401, 403)
    token = authsvc.make_token(role=authsvc.ROLE_OWNER, tenant_id=1, email="o@e.com")
    c = TestClient(app)
    c.cookies.set(authsvc.COOKIE_NAME, token)
    assert c.get("/api/v1/me/addresses").status_code in (401, 403)


# ─── create ──────────────────────────────────────────────────────────────────
def test_create_first_address_is_default():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    a = _add(c, "1450 Larimer St, Denver, CO", label="Home")
    assert a["address"] == "1450 Larimer St, Denver, CO"
    assert a["label"] == "Home"
    assert a["is_default"] is True  # first one auto-default
    for key in ("id", "label", "address", "is_default", "created_at"):
        assert key in a


def test_blank_address_is_422():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    assert c.post("/api/v1/me/addresses", json={"address": ""}).status_code == 422
    assert c.post("/api/v1/me/addresses", json={"address": "   "}).status_code == 422


# ─── list (scoped) ───────────────────────────────────────────────────────────
def test_list_scoped_to_own_client():
    cid_a, tid = _seed_passenger()
    ca = _passenger_client(cid_a, tid)
    _add(ca, "A St")
    _add(ca, "B St")

    cid_b, tid_b = _seed_passenger()
    cb = _passenger_client(cid_b, tid_b)
    _add(cb, "C St")

    a_list = ca.get("/api/v1/me/addresses").json()["addresses"]
    b_list = cb.get("/api/v1/me/addresses").json()["addresses"]
    assert {x["address"] for x in a_list} == {"A St", "B St"}
    assert {x["address"] for x in b_list} == {"C St"}


# ─── default uniqueness ──────────────────────────────────────────────────────
def test_default_uniqueness_on_create():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    _add(c, "first")
    _add(c, "second", is_default=True)
    _add(c, "third", is_default=True)
    rows = c.get("/api/v1/me/addresses").json()["addresses"]
    defaults = [x for x in rows if x["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["address"] == "third"


def test_set_default_endpoint_moves_default():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    first = _add(c, "one")          # default
    second = _add(c, "two")         # not default
    r = c.post(f"/api/v1/me/addresses/{second['id']}/default")
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True
    rows = {x["id"]: x for x in c.get("/api/v1/me/addresses").json()["addresses"]}
    assert rows[first["id"]]["is_default"] is False
    assert rows[second["id"]]["is_default"] is True


# ─── update ──────────────────────────────────────────────────────────────────
def test_update_address_fields():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    a = _add(c, "old addr", label="Work")
    r = c.patch(f"/api/v1/me/addresses/{a['id']}", json={"address": "new addr"})
    assert r.status_code == 200, r.text
    assert r.json()["address"] == "new addr"
    assert r.json()["label"] == "Work"  # untouched (exclude_unset)


def test_update_can_promote_to_default():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    _add(c, "one")                 # default
    two = _add(c, "two")
    r = c.patch(f"/api/v1/me/addresses/{two['id']}", json={"is_default": True})
    assert r.status_code == 200
    defaults = [x for x in c.get("/api/v1/me/addresses").json()["addresses"] if x["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == two["id"]


# ─── delete ──────────────────────────────────────────────────────────────────
def test_delete_address():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    a = _add(c, "one")
    b = _add(c, "two")
    r = c.delete(f"/api/v1/me/addresses/{b['id']}")
    assert r.status_code == 204
    ids = {x["id"] for x in c.get("/api/v1/me/addresses").json()["addresses"]}
    assert b["id"] not in ids and a["id"] in ids


def test_delete_default_promotes_oldest_remaining():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    first = _add(c, "first")       # default
    second = _add(c, "second")
    third = _add(c, "third")
    # delete the current default
    assert c.delete(f"/api/v1/me/addresses/{first['id']}").status_code == 204
    rows = {x["id"]: x for x in c.get("/api/v1/me/addresses").json()["addresses"]}
    assert rows[second["id"]]["is_default"] is True   # oldest remaining promoted
    assert rows[third["id"]]["is_default"] is False


# ─── isolation ───────────────────────────────────────────────────────────────
def test_cross_client_access_is_404():
    cid_a, tid = _seed_passenger()
    ca = _passenger_client(cid_a, tid)
    a = _add(ca, "A private")

    cid_b, tid_b = _seed_passenger()
    cb = _passenger_client(cid_b, tid_b)
    # B cannot read/update/delete/default A's address.
    assert cb.patch(f"/api/v1/me/addresses/{a['id']}", json={"address": "hax"}).status_code == 404
    assert cb.delete(f"/api/v1/me/addresses/{a['id']}").status_code == 404
    assert cb.post(f"/api/v1/me/addresses/{a['id']}/default").status_code == 404
    # And A's address is unchanged.
    assert ca.get("/api/v1/me/addresses").json()["addresses"][0]["address"] == "A private"


def test_update_missing_address_is_404():
    cid, tid = _seed_passenger()
    c = _passenger_client(cid, tid)
    assert c.patch("/api/v1/me/addresses/99999999", json={"address": "x"}).status_code == 404
    assert c.delete("/api/v1/me/addresses/99999999").status_code == 404
