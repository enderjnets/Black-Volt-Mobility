"""Tenant settings API: GET/PUT /tenant/settings, logo/photo upload, and the
public GET /tenants/{slug} feed."""
import base64
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "tenant-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# A real 1×1 PNG (valid magic bytes) — the upload sniffs bytes, not the filename.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA"
    "60e6kgAAAABJRU5ErkJggg=="
)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _seed_completed_ride() -> str:
    """Add a completed ride to the default tenant; return its slug."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Ride, RideStatus
    from app.services.tenancy import get_default_tenant

    async def go() -> str:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            sf = async_sessionmaker(eng, expire_on_commit=False)
            async with sf() as db:
                tenant = await get_default_tenant(db)
                db.add(
                    Ride(
                        tenant_id=tenant.id, status=RideStatus.COMPLETED,
                        pickup_text="Aurora", dropoff_text="DEN", fare_total=120.0, paid=True,
                    )
                )
                await db.commit()
                return tenant.slug
        finally:
            await eng.dispose()

    return asyncio.run(go())


def test_get_settings_returns_profile_and_status():
    c = _owner()
    r = c.get("/api/v1/tenant/settings")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["slug"] == "black-volt"
    assert "name" in d
    # Integration status is read-only and present.
    assert set(d["payments"].keys()) == {"connected", "live", "env"}
    assert d["notifications"]["available"] is False


def test_put_settings_updates_and_normalizes_brand_color():
    c = _owner()
    r = c.put(
        "/api/v1/tenant/settings",
        json={
            "tagline": "  Silent Power.  ",
            "bio": "Premium electric chauffeur.",
            "brand_color": "00e5ff",
            "rating": 4.97,
            "since_year": 2021,
            "website": "blackvoltmobility.com",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tagline"] == "Silent Power."      # trimmed
    assert d["brand_color"] == "#00E5FF"        # normalized (# prefix + upper)
    assert d["rating"] == 4.97 and d["since_year"] == 2021
    # Persisted across a fresh GET.
    assert c.get("/api/v1/tenant/settings").json()["bio"] == "Premium electric chauffeur."


def test_put_settings_rejects_bad_input():
    c = _owner()
    assert c.put("/api/v1/tenant/settings", json={"brand_color": "nothex"}).status_code == 422
    assert c.put("/api/v1/tenant/settings", json={"rating": 9}).status_code == 422
    assert c.put("/api/v1/tenant/settings", json={"since_year": 1800}).status_code == 422
    assert c.put("/api/v1/tenant/settings", json={"name": ""}).status_code == 422


def test_put_settings_blank_name_does_not_clear():
    c = _owner()
    before = c.get("/api/v1/tenant/settings").json()["name"]
    # Explicit null is accepted but ignored (name is NOT NULL).
    r = c.put("/api/v1/tenant/settings", json={"name": None, "city": "Denver / Aurora, CO"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == before


def test_logo_upload_accepts_image_and_sets_url():
    c = _owner()
    r = c.post("/api/v1/tenant/logo", files={"file": ("logo.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["logo_url"]
    assert url and url.startswith("/media/tenants/")


def test_upload_rejects_non_image_and_oversize():
    c = _owner()
    # Not an image (fails the magic-byte sniff).
    bad = c.post("/api/v1/tenant/logo", files={"file": ("x.png", b"hello world", "image/png")})
    assert bad.status_code == 400
    # Over the 5 MB cap (size is checked before sniffing).
    big = c.post(
        "/api/v1/tenant/photo",
        files={"file": ("big.png", b"0" * (6 * 1024 * 1024), "image/png")},
    )
    assert big.status_code == 413


def test_public_profile_is_safe_and_computes_stats():
    slug = _seed_completed_ride()
    c = TestClient(app)  # no session — public endpoint
    r = c.get(f"/api/v1/tenants/{slug}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["slug"] == slug
    assert isinstance(d["rides_total"], int) and d["rides_total"] >= 1
    # No secrets / internal fields leak to the public feed.
    for k in ("payments", "notifications", "email", "id"):
        assert k not in d


def test_public_profile_unknown_slug_404():
    c = TestClient(app)
    assert c.get("/api/v1/tenants/no-such-driver").status_code == 404


def test_settings_roundtrips_phone():
    c = _owner()
    r = c.put("/api/v1/tenant/settings", json={"phone": "  +1 303 555 1234  "})
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+1 303 555 1234"          # trimmed
    assert c.get("/api/v1/tenant/settings").json()["phone"] == "+1 303 555 1234"
    # Blank clears it back to null (it's an optional field).
    assert c.put("/api/v1/tenant/settings", json={"phone": "   "}).json()["phone"] is None


def test_public_profile_phone_gated_by_session():
    slug = _seed_completed_ride()
    # Owner sets a direct line.
    owner = _owner()
    resp = owner.put("/api/v1/tenant/settings", json={"phone": "+1 303 555 9000"})
    assert resp.status_code == 200

    # Anonymous viewer: profile loads but the phone is NOT exposed.
    anon = TestClient(app)
    d_anon = anon.get(f"/api/v1/tenants/{slug}").json()
    assert "phone" not in d_anon

    # Registered/signed-in viewer: the phone is included.
    d_auth = owner.get(f"/api/v1/tenants/{slug}").json()
    assert d_auth.get("phone") == "+1 303 555 9000"


def test_settings_requires_staff():
    c = TestClient(app)  # no session
    assert c.get("/api/v1/tenant/settings").status_code == 401
    assert c.put("/api/v1/tenant/settings", json={"tagline": "x"}).status_code == 401
    assert c.post(
        "/api/v1/tenant/logo", files={"file": ("logo.png", _PNG, "image/png")}
    ).status_code == 401
