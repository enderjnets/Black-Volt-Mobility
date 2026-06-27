"""Driver referral links → "designated driver" attribution + the registration wall.

A passenger who signs in via a driver's public link (`/d/{slug}`) is attributed to
that driver permanently (first-touch): their Client lives under that driver's tenant
so their rides accrue to that driver. The registration wall makes /quote require a
session so every lead is captured + attributed before they see a price.
"""
import asyncio
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
# Pinned super-admins (union with the other auth modules; env is process-global).
os.environ["GOOGLE_ADMIN_EMAILS"] = "admin@bv.com,owner@bv.test"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

QUOTE = {"pickup": "Cherry Creek", "dropoff": "Union Station"}


def _admin() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"password": "test-pw"}).status_code == 200
    return c


def _google(email: str, *, name: str = "Rider", ref: str | None = None) -> tuple[TestClient, dict]:
    """Sign in with a (mocked) verified Google identity, optionally via a driver's
    referral slug. Returns (client_with_cookie, response_body)."""
    c = TestClient(app)
    info = {"email": email, "sub": f"sub-{email}", "name": name}
    body = {"id_token": "x"}
    if ref is not None:
        body["ref"] = ref
    with patch("app.services.auth.verify_google_id_token", return_value=info):
        r = c.post("/api/v1/auth/login/google", json=body)
    assert r.status_code == 200, r.text
    return c, r.json()


def _slug_of(c: TestClient) -> str | None:
    """The session's designated-driver slug, as the /me endpoint reports it."""
    return c.get("/api/v1/auth/me").json().get("tenant_slug")


def _reset(*emails: str) -> None:
    """Drop allow-list + client rows for these emails (and their `sub-<email>`
    google_sub) so first-touch is deterministic across reruns of a shared dev DB."""
    from sqlalchemy import delete, or_
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import AllowedUser, Client

    lowered = [e.lower() for e in emails]
    subs = [f"sub-{e}" for e in lowered]

    async def go() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                await db.execute(
                    delete(Client).where(
                        or_(Client.email.in_(lowered), Client.google_sub.in_(subs))
                    )
                )
                await db.execute(delete(AllowedUser).where(AllowedUser.email.in_(lowered)))
                await db.commit()
        finally:
            await eng.dispose()

    asyncio.run(go())


def _provision_driver(email: str, name: str) -> str:
    """Add a driver to the allow-list and sign them in once so their own tenant is
    auto-provisioned. Returns their tenant slug (the shareable referral slug)."""
    a = _admin()
    a.post("/api/v1/team", json={"email": email, "name": name})
    _, body = _google(email, name=name)
    assert body["role"] == "owner" and body["tenant"], body
    return body["tenant"]


def _count_clients(google_sub: str) -> int:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Client

    async def go() -> int:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Sf = async_sessionmaker(eng, expire_on_commit=False)
            async with Sf() as db:
                return int(
                    (
                        await db.execute(
                            select(func.count(Client.id)).where(Client.google_sub == google_sub)
                        )
                    ).scalar_one()
                )
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_passenger_attributed_to_referral_driver():
    _reset("margie@drv.test", "pax1@rider.test")
    margie_slug = _provision_driver("margie@drv.test", "Margie")

    pax, body = _google("pax1@rider.test", ref=margie_slug)
    assert body["role"] == "passenger"
    # Their designated driver is Margie, not the default Black Volt tenant.
    assert _slug_of(pax) == margie_slug


def test_passenger_without_ref_defaults_to_owner():
    _reset("pax2@rider.test")
    pax, body = _google("pax2@rider.test")
    assert body["role"] == "passenger"
    assert _slug_of(pax) == "ender-ocando"


def test_invalid_ref_falls_back_to_default():
    _reset("pax3@rider.test")
    pax, _ = _google("pax3@rider.test", ref="no-such-driver-9999")
    assert _slug_of(pax) == "ender-ocando"


def test_legacy_slug_alias_still_attributes():
    # The default tenant was renamed black-volt -> ender-ocando; its deprecated
    # slug must keep attributing leads (printed QRs / shared links / ref cookies).
    _reset("pax-alias@rider.test")
    pax, _ = _google("pax-alias@rider.test", ref="black-volt")
    assert _slug_of(pax) == "ender-ocando"


def test_first_touch_is_permanent():
    _reset("margie2@drv.test", "efsun@drv.test", "pax4@rider.test")
    margie_slug = _provision_driver("margie2@drv.test", "Margie Two")
    efsun_slug = _provision_driver("efsun@drv.test", "Efsun")
    assert margie_slug != efsun_slug

    # First touch: registers via Margie's link.
    pax_a, _ = _google("pax4@rider.test", ref=margie_slug)
    assert _slug_of(pax_a) == margie_slug

    # Later signs in via Efsun's link → still Margie (first-touch is permanent),
    # and no duplicate Client is spawned under Efsun's tenant.
    pax_b, _ = _google("pax4@rider.test", ref=efsun_slug)
    assert _slug_of(pax_b) == margie_slug
    assert _count_clients("sub-pax4@rider.test") == 1


def test_quote_requires_auth_when_wall_on():
    # Anonymous → blocked by the registration wall.
    assert TestClient(app).post("/api/v1/quote", json=QUOTE).status_code == 401
    # Signed-in passenger → priced.
    _reset("pax5@rider.test")
    pax, _ = _google("pax5@rider.test")
    r = pax.post("/api/v1/quote", json=QUOTE)
    assert r.status_code == 200, r.text
    assert r.json()["total"] > 0
