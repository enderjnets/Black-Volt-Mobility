"""Reviews API: public submit/list, admin moderation, and review-request invites.

Runs against the dev database (conftest truncates reviews/review_invites + rides per
session). Tests use unique bodies and assert membership, not absolute counts.
"""
import asyncio
import datetime as dt
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["EMAIL_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Client,
    Review,
    ReviewInvite,
    ReviewStatus,
    Ride,
    RideStatus,
    Tenant,
)
from app.services import auth as authsvc  # noqa: E402
from app.services import reviews as reviews_svc  # noqa: E402
from app.services.tenancy import get_default_tenant  # noqa: E402


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _passenger(client_id: int, tenant_id: int) -> TestClient:
    c = TestClient(app)
    tok = authsvc.make_token(
        role=authsvc.ROLE_PASSENGER, tenant_id=tenant_id, client_id=client_id
    )
    c.cookies.set(authsvc.COOKIE_NAME, tok)
    return c


def _run(coro):
    return asyncio.run(coro)


async def _default_tenant_id() -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            t = await get_default_tenant(db)
            return t.id
    finally:
        await eng.dispose()


async def _seed_completed_ride(*, tenant_id: int, client_id: int | None = None) -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            ride = Ride(
                tenant_id=tenant_id,
                client_id=client_id,
                status=RideStatus.COMPLETED,
                pickup_text="Aurora, CO",
                dropoff_text="Denver Intl (DEN)",
                fare_total=110.0,
                duration_minutes=22.0,
                passenger_name="Ada Lovelace",
                passenger_phone="+13035550100",
                scheduled_at=dt.datetime(2030, 1, 1, 12, 0, tzinfo=dt.UTC),
            )
            db.add(ride)
            await db.commit()
            await db.refresh(ride)
            return ride.id
    finally:
        await eng.dispose()


async def _other_tenant_id() -> int:
    """Get-or-create a second tenant for isolation tests (tenants aren't truncated)."""
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            slug = "reviews-iso-test"
            t = (
                await db.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
            if t is None:
                t = Tenant(slug=slug, name="Reviews Iso Test")
                db.add(t)
                await db.commit()
                await db.refresh(t)
            return t.id
    finally:
        await eng.dispose()


async def _insert_review(*, tenant_id: int, body: str, approved: bool, show_on_home: bool) -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            r = Review(
                tenant_id=tenant_id,
                author_name="Seed",
                rating=5,
                body=body,
                status=ReviewStatus.APPROVED if approved else ReviewStatus.PENDING,
                show_on_home=show_on_home,
            )
            db.add(r)
            await db.commit()
            await db.refresh(r)
            return r.id
    finally:
        await eng.dispose()


# ─── public submit + moderation ──────────────────────────────────────────────


def test_public_submit_is_pending_and_hidden():
    c = TestClient(app)
    marker = "PUBLIC-SUBMIT-MARKER body text"
    r = c.post(
        "/api/v1/reviews",
        json={"rating": 5, "body": marker, "author_name": "Jane Public"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["verified"] is False

    # not visible publicly until approved
    pub = c.get("/api/v1/reviews/public?surface=route").json()
    assert all(marker not in row["body"] for row in pub)


def test_submit_rejects_bad_rating():
    c = TestClient(app)
    r = c.post("/api/v1/reviews", json={"rating": 9, "body": "nope", "author_name": "X"})
    assert r.status_code == 422


def test_admin_approve_then_home_toggle():
    owner = _owner()
    marker = "APPROVE-FLOW unique body"
    rid = TestClient(app).post(
        "/api/v1/reviews",
        json={"rating": 4, "body": marker, "author_name": "Mod Test"},
    ).json()
    assert rid["status"] == "pending"

    # admin sees it pending
    listed = owner.get("/api/v1/reviews/admin").json()
    mine = [x for x in listed if x["body"] == marker]
    assert len(mine) == 1
    review_id = mine[0]["id"]
    assert mine[0]["status"] == "pending"

    # approve → visible on route surface, but NOT home (show_on_home false)
    patched = owner.patch(
        f"/api/v1/reviews/admin/{review_id}", json={"status": "approved"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "approved"

    route_pub = owner.get("/api/v1/reviews/public?surface=route").json()
    assert any(x["body"] == marker for x in route_pub)
    home_pub = owner.get("/api/v1/reviews/public?surface=home").json()
    assert all(x["body"] != marker for x in home_pub)

    # toggle show_on_home → now on home
    owner.patch(f"/api/v1/reviews/admin/{review_id}", json={"show_on_home": True})
    home_pub2 = owner.get("/api/v1/reviews/public?surface=home").json()
    assert any(x["body"] == marker for x in home_pub2)


def test_admin_requires_auth():
    anon = TestClient(app)
    assert anon.get("/api/v1/reviews/admin").status_code in (401, 403)
    assert anon.post("/api/v1/reviews/admin/invites", json={}).status_code in (401, 403)


def test_admin_delete_review():
    owner = _owner()
    marker = "DELETE-ME body"
    TestClient(app).post(
        "/api/v1/reviews", json={"rating": 3, "body": marker, "author_name": "Del"}
    )
    rid = [x for x in owner.get("/api/v1/reviews/admin").json() if x["body"] == marker][0]["id"]
    assert owner.delete(f"/api/v1/reviews/admin/{rid}").status_code == 204
    assert all(x["id"] != rid for x in owner.get("/api/v1/reviews/admin").json())


# ─── invite flow (verified) ──────────────────────────────────────────────────


def test_invite_flow_creates_verified_review():
    owner = _owner()
    tid = _run(_default_tenant_id())
    ride_id = _run(_seed_completed_ride(tenant_id=tid))

    created = owner.post(
        "/api/v1/reviews/admin/invites",
        json={
            "ride_id": ride_id,
            "to_email": "ada@example.com",
            "to_phone": "+13035550100",
            "author_name": "Ada",
            "channels": ["email"],
            "lang": "en",
        },
    )
    assert created.status_code == 201, created.text
    inv = created.json()
    assert inv["token"]
    assert inv["link"].endswith(f"/review/{inv['token']}")
    assert inv["sms_href"].startswith("sms:")
    assert inv["email_status"] == "simulated"  # EMAIL_SIMULATED=true

    # resolve invite (prefill)
    got = TestClient(app).get(f"/api/v1/reviews/invite/{inv['token']}")
    assert got.status_code == 200
    assert got.json()["used"] is False

    # submit via token → verified
    marker = "INVITE-VERIFIED body"
    sub = TestClient(app).post(
        "/api/v1/reviews",
        json={"token": inv["token"], "rating": 5, "body": marker, "author_name": "Ada"},
    )
    assert sub.status_code == 201, sub.text
    assert sub.json()["verified"] is True

    # invite now marked used
    assert TestClient(app).get(f"/api/v1/reviews/invite/{inv['token']}").json()["used"] is True

    # admin sees it verified
    row = [x for x in owner.get("/api/v1/reviews/admin").json() if x["body"] == marker][0]
    assert row["verified"] is True
    assert row["source"] == "invite"


def test_invalid_token_404():
    r = TestClient(app).post(
        "/api/v1/reviews",
        json={"token": "nope-not-real", "rating": 5, "body": "hello there", "author_name": "X"},
    )
    assert r.status_code == 404


# ─── passenger-owned ride (verified via session) ─────────────────────────────


def test_passenger_review_of_own_ride_is_verified():
    tid = _run(_default_tenant_id())
    client_id = 4242
    ride_id = _run(_seed_completed_ride(tenant_id=tid, client_id=client_id))
    pax = _passenger(client_id, tid)
    marker = "PASSENGER-OWNED body"
    r = pax.post(
        "/api/v1/reviews",
        json={"ride_id": ride_id, "rating": 5, "body": marker, "author_name": "Ada"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["verified"] is True


# ─── candidates + tenant isolation ───────────────────────────────────────────


def test_candidates_lists_completed_ride():
    owner = _owner()
    tid = _run(_default_tenant_id())
    ride_id = _run(_seed_completed_ride(tenant_id=tid))
    cands = owner.get("/api/v1/reviews/admin/candidates").json()
    assert any(c["ride_id"] == ride_id for c in cands)


# ─── automatic post-ride reminders ───────────────────────────────────────────


async def _seed_client(*, tenant_id: int, email: str | None) -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            c = Client(tenant_id=tenant_id, email=email, name="Rider One", ride_preferences={})
            db.add(c)
            await db.commit()
            await db.refresh(c)
            return c.id
    finally:
        await eng.dispose()


async def _seed_completed_ride_aged(*, tenant_id: int, client_id: int, hours_ago: float) -> int:
    """Insert a COMPLETED ride whose updated_at (the completion proxy) is in the past.
    The timestamp goes in the constructor so the INSERT keeps it (no later UPDATE)."""
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours_ago)
            ride = Ride(
                tenant_id=tenant_id,
                client_id=client_id,
                status=RideStatus.COMPLETED,
                pickup_text="Aurora, CO",
                dropoff_text="Denver Intl (DEN)",
                fare_total=110.0,
                duration_minutes=22.0,
                scheduled_at=past,
                updated_at=past,
            )
            db.add(ride)
            await db.commit()
            await db.refresh(ride)
            return ride.id
    finally:
        await eng.dispose()


async def _run_reminders() -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            return await reviews_svc.send_due_reminders(db)
    finally:
        await eng.dispose()


async def _invites_for_ride(ride_id: int) -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            rows = (
                await db.execute(select(ReviewInvite.id).where(ReviewInvite.ride_id == ride_id))
            ).all()
            return len(rows)
    finally:
        await eng.dispose()


async def _set_tenant_reminders(tenant_id: int, *, enabled: bool, hours: int = 3) -> None:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with sf() as db:
            t = await db.get(Tenant, tenant_id)
            t.review_reminders_enabled = enabled
            t.review_reminder_hours = hours
            await db.commit()
    finally:
        await eng.dispose()


def test_reminder_emails_due_ride_once():
    tid = _run(_default_tenant_id())
    _run(_set_tenant_reminders(tid, enabled=True, hours=3))
    cid = _run(_seed_client(tenant_id=tid, email="due-rider@example.com"))
    ride_id = _run(_seed_completed_ride_aged(tenant_id=tid, client_id=cid, hours_ago=4))

    _run(_run_reminders())
    assert _run(_invites_for_ride(ride_id)) == 1  # one request created (+ email simulated)

    # dedup: running again does not create a second invite
    _run(_run_reminders())
    assert _run(_invites_for_ride(ride_id)) == 1


def test_reminder_skips_recent_ride():
    tid = _run(_default_tenant_id())
    _run(_set_tenant_reminders(tid, enabled=True, hours=3))
    cid = _run(_seed_client(tenant_id=tid, email="recent-rider@example.com"))
    ride_id = _run(_seed_completed_ride_aged(tenant_id=tid, client_id=cid, hours_ago=1))
    _run(_run_reminders())
    assert _run(_invites_for_ride(ride_id)) == 0  # too recent (< 3h)


def test_reminder_skips_ride_without_email():
    tid = _run(_default_tenant_id())
    _run(_set_tenant_reminders(tid, enabled=True, hours=3))
    cid = _run(_seed_client(tenant_id=tid, email=None))
    ride_id = _run(_seed_completed_ride_aged(tenant_id=tid, client_id=cid, hours_ago=5))
    _run(_run_reminders())
    assert _run(_invites_for_ride(ride_id)) == 0  # no email → no reminder


def test_reminder_respects_tenant_off_toggle():
    tid = _run(_default_tenant_id())
    cid = _run(_seed_client(tenant_id=tid, email="toggle-rider@example.com"))
    ride_id = _run(_seed_completed_ride_aged(tenant_id=tid, client_id=cid, hours_ago=5))
    try:
        _run(_set_tenant_reminders(tid, enabled=False, hours=3))
        _run(_run_reminders())
        assert _run(_invites_for_ride(ride_id)) == 0  # disabled → nothing
        # turning it back on now reminds
        _run(_set_tenant_reminders(tid, enabled=True, hours=3))
        _run(_run_reminders())
        assert _run(_invites_for_ride(ride_id)) == 1
    finally:
        _run(_set_tenant_reminders(tid, enabled=True, hours=3))


def test_public_list_is_tenant_scoped():
    # a review approved + show_on_home for a DIFFERENT tenant must not leak.
    other_tenant = _run(_other_tenant_id())
    marker = "OTHER-TENANT body"
    _run(_insert_review(tenant_id=other_tenant, body=marker, approved=True, show_on_home=True))
    pub = TestClient(app).get("/api/v1/reviews/public?surface=home").json()
    assert all(row["body"] != marker for row in pub)
    # but explicitly querying that tenant returns it
    pub2 = TestClient(app).get(
        f"/api/v1/reviews/public?surface=home&tenant_id={other_tenant}"
    ).json()
    assert any(row["body"] == marker for row in pub2)
