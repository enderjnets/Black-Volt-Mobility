"""API tests for the "Where to wait" demand planner (import, log, week)."""
import os

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def test_settings_defaults():
    s = get_settings()
    assert s.DEMAND_ENABLED is True  # set by this module's env
    assert s.DEMAND_BRIDGE_FARE_DEFAULT == 35.0
    assert s.DEMAND_RECOMPUTE_MIN == 15
    assert s.DEN_LOT_RADIUS_M == 400


def test_me_exposes_demand_feature_flag():
    c = _owner()
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["features"] == {"demand": True}


import io  # noqa: E402
import zipfile  # noqa: E402

from tests.test_uber_import import (  # noqa: E402
    ONOFF_2021_HEADER,
    ONOFF_2021_ROWS,
    TRIPS_2025_HEADER,
    TRIPS_2025_ROW,
)


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def _export_zip() -> bytes:
    return _zip({
        "driver_lifetime_trips-0.csv": TRIPS_2025_HEADER + "\n" + TRIPS_2025_ROW + "\n",
        "Driver Online Offline.csv": ONOFF_2021_HEADER + "\n" + "\n".join(ONOFF_2021_ROWS) + "\n",
    })


def test_import_requires_staff():
    assert client.post("/api/v1/demand/import").status_code == 401
    assert client.get("/api/v1/demand/import/status").status_code == 401


def test_import_status_before_any_import():
    c = _owner()
    r = c.get("/api/v1/demand/import/status")
    assert r.status_code == 200 and r.json() == {"never": True}


def test_import_twice_is_idempotent_and_reports_missing_files():
    c = _owner()
    r = c.post("/api/v1/demand/import",
               files=[("file", ("uber.zip", _export_zip(), "application/zip"))])
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["trips"]["inserted"] == 1 and s["segments"]["inserted"] == 2
    assert s["trips"]["by_product"] == {"black_suv": 1}
    assert s["trips"]["date_min"].startswith("2025-03-01")
    assert [m["kind"] for m in s["files_missing"]] == ["dispatches", "analytics"]
    r2 = c.post("/api/v1/demand/import",
                files=[("file", ("uber.zip", _export_zip(), "application/zip"))])
    assert r2.status_code == 201
    assert r2.json()["trips"]["inserted"] == 0 and r2.json()["trips"]["skipped"] == 1
    st = c.get("/api/v1/demand/import/status").json()
    assert st["trips"]["inserted"] == 0 and "at" in st


def test_import_rejects_bad_zip():
    c = _owner()
    r = c.post("/api/v1/demand/import", files=[("file", ("x.zip", b"nope", "application/zip"))])
    assert r.status_code == 400 and r.json()["detail"] == "not_a_zip"
    r = c.post("/api/v1/demand/import",
               files=[("file", ("x.zip", _zip({"a.txt": "hi"}), "application/zip"))])
    assert r.status_code == 400 and r.json()["detail"] == "no_csv"
