# "Where to wait" — Phase 1 (planner + one-tap logging) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the owner a 7-day "best hours to work" planner for Uber Black / Black SUV, seeded by his Uber data export and corrected by one-tap shift logging, plus the import and logging screens that feed it. No map yet (Phase 2).

**Architecture:** New tenant-scoped tables (Uber trips, online/offline segments, offers, dispatch windows, import runs, static hex priors, DEN flight baseline, computed week scores). A pure-function model module (Gamma-Poisson shrinkage of the owner's offer rate toward a proxy prior) is orchestrated by a service that runs hourly inside the existing in-process APScheduler and caches to Redis. Three staff-only API groups (import, log, week) and one new dashboard route with three tabs (Log, Week, Import).

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Alembic + Postgres 16 + Redis; `h3==4.5.0`, `holidays==0.104`, `pyshp==3.1.6`; Next.js 14 app router, React 18, inline-style components from `components/bv/ui.tsx`, i18n EN+ES in `lib/i18n.tsx`.

**Spec:** `docs/superpowers/specs/2026-09-17-black-demand-heatmap-design.md` (read it first; this plan implements its Phase 1). Research: `docs/research/2026-09-17-black-demand-heatmap.md`.

**Execution order (amended 2026-09-17):** Tasks 1–8, then **Task 15** (spec Addendum A: the 30-day GPS file), then Tasks 9–14. Task 15's rules bind Task 9's loader, Task 11's Log tab and Task 12's Import tab; those sections carry an *Amendment* paragraph.

## Global Constraints

- Python 3.11, ruff `line-length = 100`, rules `E,F,I,UP,B` (`backend/pyproject.toml`). Run `ruff check .` from `backend/` before every commit.
- Every new table has `tenant_id` FK `tenants.id` `ondelete="CASCADE"`, indexed. Every query filters by `tenant_id` resolved with `resolve_tenant_id(db, payload)` from `app/api/deps.py`. Never trust a tenant id from the request body.
- Enum columns use `pg_enum(EnumCls, name="...")` from `app/db/base.py`, values lowercase.
- Migration id `0050_demand_phase1`, `down_revision = "0049_ride_assignment"`. `alembic upgrade head` must leave `alembic revision --autogenerate` with **no diff**.
- API tests follow `backend/tests/test_platform_stats.py`: set env vars at import (`DASHBOARD_PASSWORD="test-pw"`, `AUTH_SECRET`, `AUTH_ENABLED="true"`, simulated flags), `get_settings.cache_clear()`, `TestClient(app)`, owner login `POST /api/v1/auth/login {"password": "test-pw"}`. Tests run against the ephemeral local docker stack (`DATABASE_URL=postgresql+asyncpg://blackvolt:blackvolt_local_pass@localhost:5432/blackvolt`, see `.github/workflows/ci.yml`).
- Every new setting is declared in `backend/app/config.py` **and** in the backend `environment:` list of `docker-compose.yml` (the compose passes only listed vars).
- Every user-visible string goes in **both** `EN` and `ES` dictionaries in `frontend/lib/i18n.tsx` under `dash.demand.*`.
- Icons come only from the fixed registry in `frontend/components/bv/Icon.tsx` (`map-pin`, `plane`, `clock`, `upload`, `calendar`, `zap`, `alert-circle`, `circle-check`, `x` already exist).
- No Google Maps key in the browser. No Uber credentials anywhere. Coordinates stored rounded to 5 decimals.
- Time math: hour-of-week and day slots are computed in `America/Denver` from tz-aware datetimes; never add 24 fixed slots per day.
- Work on branch `feat/demand-phase1` off `main` (repo convention: one branch per phase, PR → merge → tag). Commit after every task with the message given, ending the body with the repo's line `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` (CLAUDE.md); do **not** push until Task 14. Version bump and CHANGELOG happen in Task 13 only.
- Code style per CLAUDE.md: no comments except the non-obvious *why*; module docstrings are the repo norm and stay.
- New Python dependencies are pinned in `backend/requirements.txt`; no new frontend dependency in Phase 1 (the backend computes the H3 cell).

## Deviations from the spec, decided while planning

- `uber_trips` gains nullable `begin_lat`/`begin_lng` because the 2022 export format carries pickup coordinates; the current format leaves them null.
- `driver_state_segments` gains `last_ping_at` so a 60-second ping extends the open segment instead of creating a row per ping.
- Flight multiplier is **relative** (hour's flights ÷ that day's mean), so BTS On-Time counts alone suffice for Phase 1; the T-100 seat scaling and the international constant from the spec are deferred to Phase 2.
- `h3-js` is not added to the frontend in Phase 1; the log endpoint receives lat/lng and the backend computes the cell.
- The NWS weather multiplier is deferred to Phase 2 (the setting `NWS_USER_AGENT` is declared now so the env list does not change twice); Phase 1 covariates are DEN flight banks, events and holidays.

## File structure

Backend (`backend/`):

- `app/models/demand.py` — all Phase 1 ORM classes + enums (one file: they change together).
- `migrations/versions/0050_demand_phase1.py`
- `app/services/demand_model.py` — pure math, no DB/network.
- `app/services/uber_import.py` — ZIP → parsed rows (pure) + upsert (DB).
- `app/services/shift_log.py` — one-tap events → segments/offers.
- `app/services/demand_places.py` — curated hotels/FBOs/generators/zones (code constant) + `data/demand_places.json` (geocoded once).
- `app/services/demand_prior.py` — Census + places → `hex_priors`.
- `app/services/flights_baseline.py` — BTS On-Time → `den_flight_baseline`.
- `app/services/demand.py` — orchestration: week recompute, Redis cache, payloads.
- `app/services/gps_import.py` — 30-day analytics pings → segments, pickup backfill, waits summary (Task 15).
- `migrations/versions/0051_segment_source_gps.py`
- `app/scripts/geocode_places.py`, `app/scripts/build_demand_priors.py`, `app/scripts/build_flight_baseline.py`
- `app/api/v1/demand.py` — router.
- `tests/test_demand_model.py`, `tests/test_uber_import.py`, `tests/test_demand_api.py`, `tests/test_shift_log.py`, `tests/test_demand_prior.py`, `tests/test_flights_baseline.py`, `tests/test_demand_jobs.py`, `tests/test_gps_import.py`

Frontend (`frontend/`):

- `lib/demand.ts` — types + API client.
- `components/bv/dash/demand/DemandPage.tsx` (tabs shell), `LogTab.tsx`, `WeekTab.tsx`, `ImportTab.tsx`
- `app/dashboard/demand/page.tsx`
- Edits: `lib/auth.ts` (Me.features), `lib/i18n.tsx`, `components/bv/dash/DriverTabBar.tsx`, `components/bv/dash/DashShell.tsx`, `lib/version.ts`, `CHANGELOG.md`

Docs: `docs/setup-demand.md`.

---

### Task 1: Dependencies, settings, feature flag

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py` (after the `PRICING_SCOUT_SECRET` line, ~432)
- Modify: `docker-compose.yml` (backend `environment:` block, next to `PRICING_SCOUT_URL`)
- Modify: `backend/app/api/v1/auth.py` (`/auth/me` response, the dict at ~line 170 that contains `"is_admin": await session_is_admin(db, payload)`)
- Modify: `frontend/lib/auth.ts` (`Me` interface)
- Test: `backend/tests/test_demand_api.py` (created here, extended in later tasks)

**Interfaces:**
- Produces: `get_settings().DEMAND_ENABLED: bool`, `.CENSUS_API_KEY: str`, `.DEN_LOT_LAT: float | None`, `.DEN_LOT_LNG: float | None`, `.DEN_LOT_RADIUS_M: int`, `.DEMAND_BRIDGE_FARE_DEFAULT: float`, `.DEMAND_RECOMPUTE_MIN: int`, `.NWS_USER_AGENT: str`; `/auth/me` JSON gains `"features": {"demand": bool}`; TS `Me.features?: { demand?: boolean }`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_demand_api.py`:

```python
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
    assert s.DEN_LOT_LAT is None and s.DEN_LOT_LNG is None


def test_me_exposes_demand_feature_flag():
    c = _owner()
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["features"] == {"demand": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `pytest tests/test_demand_api.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'DEMAND_ENABLED'` (pydantic ignores unknown env vars, so the settings test fails on the missing attribute; the `features` test fails with `KeyError`).

- [ ] **Step 3: Add dependencies and settings**

Append to `backend/requirements.txt` (keep alphabetical block at the end, before the test tools):

```
h3==4.5.0
holidays==0.104
pyshp==3.1.6
```

In `backend/app/config.py`, right after `PRICING_SCOUT_SECRET: str = ""` add:

```python
    # ── "Where to wait": Black demand planner (Phase 1). Spec:
    # docs/superpowers/specs/2026-09-17-black-demand-heatmap-design.md
    DEMAND_ENABLED: bool = False
    CENSUS_API_KEY: str = ""
    # DEN Commercial Hold Lot centre. Unset (None) → DEN-lot tagging is off until the
    # owner confirms the position on site (Owner TODO 3 in the spec).
    DEN_LOT_LAT: float | None = None
    DEN_LOT_LNG: float | None = None
    DEN_LOT_RADIUS_M: int = 400
    DEMAND_BRIDGE_FARE_DEFAULT: float = 35.0
    DEMAND_RECOMPUTE_MIN: int = 15
    # api.weather.gov requires an identifying User-Agent.
    NWS_USER_AGENT: str = "BlackVoltMobility/1.0 (blackvoltmobility@gmail.com)"

    @field_validator("DEN_LOT_LAT", "DEN_LOT_LNG", mode="before")
    @classmethod
    def _blank_lot_coord_to_none(cls, v):
        # docker-compose passes "" when unset; treat that as "not configured".
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
```

In `docker-compose.yml`, in the backend `environment:` block right after `PRICING_SCOUT_SECRET: ${PRICING_SCOUT_SECRET:-}` (line ~165) add:

```yaml
      DEMAND_ENABLED: ${DEMAND_ENABLED:-false}
      CENSUS_API_KEY: ${CENSUS_API_KEY:-}
      DEN_LOT_LAT: ${DEN_LOT_LAT:-}
      DEN_LOT_LNG: ${DEN_LOT_LNG:-}
      DEN_LOT_RADIUS_M: ${DEN_LOT_RADIUS_M:-400}
      DEMAND_BRIDGE_FARE_DEFAULT: ${DEMAND_BRIDGE_FARE_DEFAULT:-35}
      DEMAND_RECOMPUTE_MIN: ${DEMAND_RECOMPUTE_MIN:-15}
      NWS_USER_AGENT: ${NWS_USER_AGENT:-BlackVoltMobility/1.0 (blackvoltmobility@gmail.com)}
```

In `backend/app/api/v1/auth.py`, in the `/auth/me` handler's returned dict (the one containing `"is_admin": await session_is_admin(db, payload)`), add the key:

```python
            "features": {"demand": get_settings().DEMAND_ENABLED},
```

(`get_settings` is already imported in that module; if not, add `from app.config import get_settings`.)

In `frontend/lib/auth.ts`, add to `export interface Me { ... }`:

```ts
  features?: { demand?: boolean };
```

- [ ] **Step 4: Install and run the tests**

Run (from `backend/`): `pip install -r requirements.txt && pytest tests/test_demand_api.py -v && ruff check .`
Expected: 2 PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/config.py docker-compose.yml backend/app/api/v1/auth.py frontend/lib/auth.ts backend/tests/test_demand_api.py
git commit -m "feat(demand): settings, dependencies and feature flag for the demand planner"
```

---

### Task 2: ORM models and migration 0050

**Files:**
- Create: `backend/app/models/demand.py`
- Modify: `backend/app/models/__init__.py` (import + `__all__`)
- Modify: `backend/app/models/rate_config.py` (add `bridge_fare`)
- Create: `backend/migrations/versions/0050_demand_phase1.py`
- Modify: `backend/tests/conftest.py` (add new tables to the TRUNCATE list)
- Test: `backend/tests/test_demand_models.py`

**Interfaces:**
- Produces: enums `UberProduct` (`black_suv, black, comfort, x, xl, other`), `EarnerState` (`open, enroute, ontrip, offline`), `SegmentSource` (`export, live`); classes `UberTrip`, `DriverStateSegment`, `OfferEvent`, `DispatchWindow`, `DemandImport`, `HexPrior`, `DenFlightBaseline`, `WeekScore`, `HexScore`; `RateConfig.bridge_fare: float | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_demand_models.py`:

```python
"""The Phase 1 demand tables exist in metadata with the columns the services rely on."""
from app.db.base import Base
from app.models import (
    DemandImport,
    DenFlightBaseline,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    HexPrior,
    HexScore,
    OfferEvent,
    RateConfig,
    UberProduct,
    UberTrip,
    WeekScore,
)


def test_tables_registered():
    names = set(Base.metadata.tables)
    for t in (
        "uber_trips",
        "driver_state_segments",
        "offer_events",
        "dispatch_windows",
        "demand_imports",
        "hex_priors",
        "den_flight_baseline",
        "week_scores",
        "hex_scores",
    ):
        assert t in names, t


def test_enum_values_are_lowercase():
    assert [e.value for e in UberProduct] == ["black_suv", "black", "comfort", "x", "xl", "other"]
    assert [e.value for e in EarnerState] == ["open", "enroute", "ontrip", "offline"]


def test_key_columns():
    cols = {c.name for c in UberTrip.__table__.columns}
    assert {"tenant_id", "dedup_key", "product", "request_at", "is_airport", "begin_lat"} <= cols
    cols = {c.name for c in DriverStateSegment.__table__.columns}
    assert {"state", "begin_at", "end_at", "last_ping_at", "h3_r8", "source", "zone_key"} <= cols
    cols = {c.name for c in OfferEvent.__table__.columns}
    assert {"client_event_id", "product", "accepted", "h3_r8"} <= cols
    assert "bridge_fare" in {c.name for c in RateConfig.__table__.columns}
    for cls in (DispatchWindow, DemandImport, HexPrior, DenFlightBaseline, WeekScore, HexScore):
        assert cls.__table__ is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_demand_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'DemandImport' from 'app.models'`.

- [ ] **Step 3: Write the models**

Create `backend/app/models/demand.py`:

```python
"""'Where to wait' — the owner's Uber history, one-tap shift log, static priors and
computed scores. Everything the driver produces is tenant-scoped; `hex_priors` and
`den_flight_baseline` are geography/airport facts shared by all tenants.

Spec: docs/superpowers/specs/2026-09-17-black-demand-heatmap-design.md
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class UberProduct(str, enum.Enum):
    BLACK_SUV = "black_suv"
    BLACK = "black"
    COMFORT = "comfort"
    X = "x"
    XL = "xl"
    OTHER = "other"


class EarnerState(str, enum.Enum):
    OPEN = "open"          # online, waiting for a request → the exposure we measure
    ENROUTE = "enroute"    # accepted, driving to the pickup
    ONTRIP = "ontrip"
    OFFLINE = "offline"


class SegmentSource(str, enum.Enum):
    EXPORT = "export"
    LIVE = "live"


def _tenant_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class UberTrip(Base):
    """One trip from the Uber driver data export (`driver_lifetime_trips`)."""

    __tablename__ = "uber_trips"
    __table_args__ = (UniqueConstraint("tenant_id", "dedup_key", name="uq_uber_trips_dedup"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    # The export has no trip UUID: sha256 of request_at|begin_at|fare_total|distance_mi.
    dedup_key: Mapped[str] = mapped_column(String(64))
    product: Mapped[UberProduct] = mapped_column(pg_enum(UberProduct, name="uber_product"))
    product_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    begin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dropoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Only the 2022 export format carries pickup coordinates; null otherwise.
    begin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    begin_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_airport: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    fare_total: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    surge_multiplier: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    distance_mi: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DriverStateSegment(Base):
    """A stretch of time in one earner state, with where it began and ended."""

    __tablename__ = "driver_state_segments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedup_key", name="uq_driver_state_segments_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    dedup_key: Mapped[str] = mapped_column(String(80))
    state: Mapped[EarnerState] = mapped_column(pg_enum(EarnerState, name="earner_state"))
    begin_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Null while the live segment is still open; pings only move last_ping_at.
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    begin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    begin_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    h3_r8: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    zone_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[SegmentSource] = mapped_column(pg_enum(SegmentSource, name="segment_source"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OfferEvent(Base):
    """A ride offer the driver saw (live one-tap log only)."""

    __tablename__ = "offer_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_event_id", name="uq_offer_events_client_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    client_event_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    h3_r8: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    product: Mapped[UberProduct] = mapped_column(pg_enum(UberProduct, name="uber_product"))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    fare: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    dest_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DispatchWindow(Base):
    """Per-window offer counts from the export ("Dispatches Offered and Accepted")."""

    __tablename__ = "dispatch_windows"
    __table_args__ = (UniqueConstraint("tenant_id", "dedup_key", name="uq_dispatch_windows_dedup"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    dedup_key: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minutes_online: Mapped[float] = mapped_column(Float, default=0.0)
    minutes_active: Mapped[float] = mapped_column(Float, default=0.0)
    dispatches: Mapped[int] = mapped_column(Integer, default=0)
    rejections: Mapped[int] = mapped_column(Integer, default=0)
    accepts: Mapped[int] = mapped_column(Integer, default=0)
    expireds: Mapped[int] = mapped_column(Integer, default=0)
    completed_trips: Mapped[int] = mapped_column(Integer, default=0)


class DemandImport(Base):
    """One upload of the Uber export ZIP and what it contained."""

    __tablename__ = "demand_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    summary: Mapped[dict] = mapped_column(JSON)


class HexPrior(Base):
    """Static per-cell geography: affluence, luxury hotels, generators, DEN distance."""

    __tablename__ = "hex_priors"

    h3_r8: Mapped[str] = mapped_column(String(16), primary_key=True)
    affluence: Mapped[float] = mapped_column(Float, default=0.0)
    hotels: Mapped[int] = mapped_column(Integer, default=0)
    generators: Mapped[int] = mapped_column(Integer, default=0)
    den_distance_mi: Mapped[float] = mapped_column(Float, default=0.0)
    zone_key: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DenFlightBaseline(Base):
    """Typical DEN departures/arrivals per (month, dow, hour), from BTS On-Time."""

    __tablename__ = "den_flight_baseline"
    __table_args__ = (UniqueConstraint("month", "dow", "hour", name="uq_den_flight_baseline"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer)   # 1-12
    dow: Mapped[int] = mapped_column(Integer)     # 0=Monday … 6=Sunday
    hour: Mapped[int] = mapped_column(Integer)    # 0-23 local
    departures: Mapped[float] = mapped_column(Float, default=0.0)  # avg per day
    arrivals: Mapped[float] = mapped_column(Float, default=0.0)
    source_period: Mapped[str | None] = mapped_column(String(40), nullable=True)


class WeekScore(Base):
    """Latest 7×24 planner grid per tenant and zone."""

    __tablename__ = "week_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    zone_key: Mapped[str] = mapped_column(String(40), index=True)
    dow: Mapped[int] = mapped_column(Integer)
    hour: Mapped[int] = mapped_column(Integer)
    mean: Mapped[float] = mapped_column(Float)      # offers per minute
    lo: Mapped[float] = mapped_column(Float)
    hi: Mapped[float] = mapped_column(Float)
    own_share: Mapped[float] = mapped_column(Float)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class HexScore(Base):
    """Per-cell scores per 15-minute slot (filled in Phase 2; table created now)."""

    __tablename__ = "hex_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = _tenant_fk()
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    h3_r8: Mapped[str] = mapped_column(String(16))
    mean: Mapped[float] = mapped_column(Float)
    lo: Mapped[float] = mapped_column(Float)
    hi: Mapped[float] = mapped_column(Float)
    own_share: Mapped[float] = mapped_column(Float)
    reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

In `backend/app/models/rate_config.py`, after `default_driver_share_pct` add:

```python
    # "Where to wait": minimum Comfort fare worth taking toward a better zone.
    # Null → settings.DEMAND_BRIDGE_FARE_DEFAULT.
    bridge_fare: Mapped[float | None] = mapped_column(Float, nullable=True)
```

In `backend/app/models/__init__.py` add the import and the `__all__` entries:

```python
from app.models.demand import (  # noqa: F401
    DemandImport,
    DenFlightBaseline,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    HexPrior,
    HexScore,
    OfferEvent,
    SegmentSource,
    UberProduct,
    UberTrip,
    WeekScore,
)
```

and append to `__all__`: `"DemandImport", "DenFlightBaseline", "DispatchWindow", "DriverStateSegment", "EarnerState", "HexPrior", "HexScore", "OfferEvent", "SegmentSource", "UberProduct", "UberTrip", "WeekScore",`.

- [ ] **Step 4: Write the migration**

Create `backend/migrations/versions/0050_demand_phase1.py`:

```python
"""where-to-wait phase 1: uber export, shift log, priors, flight baseline, scores

Revision ID: 0050_demand_phase1
Revises: 0049_ride_assignment
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0050_demand_phase1"
down_revision = "0049_ride_assignment"
branch_labels = None
depends_on = None

_PRODUCT = ("black_suv", "black", "comfort", "x", "xl", "other")
_STATE = ("open", "enroute", "ontrip", "offline")
_SOURCE = ("export", "live")


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in (
        ("uber_product", _PRODUCT),
        ("earner_state", _STATE),
        ("segment_source", _SOURCE),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    tenant_fk = sa.ForeignKey("tenants.id", ondelete="CASCADE")

    op.create_table(
        "uber_trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("product", _enum("uber_product", _PRODUCT), nullable=False),
        sa.Column("product_raw", sa.String(80), nullable=True),
        sa.Column("request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dropoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_lat", sa.Float(), nullable=True),
        sa.Column("begin_lng", sa.Float(), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("is_airport", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_scheduled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("fare_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("surge_multiplier", sa.Numeric(5, 2), nullable=True),
        sa.Column("distance_mi", sa.Numeric(8, 2), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_uber_trips_dedup"),
    )
    op.create_index("ix_uber_trips_tenant_id", "uber_trips", ["tenant_id"])
    op.create_index("ix_uber_trips_begin_at", "uber_trips", ["begin_at"])

    op.create_table(
        "driver_state_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
        sa.Column("dedup_key", sa.String(80), nullable=False),
        sa.Column("state", _enum("earner_state", _STATE), nullable=False),
        sa.Column("begin_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("begin_lat", sa.Float(), nullable=True),
        sa.Column("begin_lng", sa.Float(), nullable=True),
        sa.Column("end_lat", sa.Float(), nullable=True),
        sa.Column("end_lng", sa.Float(), nullable=True),
        sa.Column("h3_r8", sa.String(16), nullable=True),
        sa.Column("zone_key", sa.String(40), nullable=True),
        sa.Column("source", _enum("segment_source", _SOURCE), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_driver_state_segments_dedup"),
    )
    op.create_index("ix_driver_state_segments_tenant_id", "driver_state_segments", ["tenant_id"])
    op.create_index("ix_driver_state_segments_begin_at", "driver_state_segments", ["begin_at"])
    op.create_index("ix_driver_state_segments_h3_r8", "driver_state_segments", ["h3_r8"])

    op.create_table(
        "offer_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
        sa.Column("client_event_id", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("h3_r8", sa.String(16), nullable=True),
        sa.Column("product", _enum("uber_product", _PRODUCT), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("dest_text", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "client_event_id", name="uq_offer_events_client_event"),
    )
    op.create_index("ix_offer_events_tenant_id", "offer_events", ["tenant_id"])
    op.create_index("ix_offer_events_at", "offer_events", ["at"])
    op.create_index("ix_offer_events_h3_r8", "offer_events", ["h3_r8"])

    op.create_table(
        "dispatch_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_online", sa.Float(), nullable=False, server_default="0"),
        sa.Column("minutes_active", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dispatches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expireds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_trips", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_dispatch_windows_dedup"),
    )
    op.create_index("ix_dispatch_windows_tenant_id", "dispatch_windows", ["tenant_id"])
    op.create_index("ix_dispatch_windows_window_start", "dispatch_windows", ["window_start"])

    op.create_table(
        "demand_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("summary", sa.JSON(), nullable=False),
    )
    op.create_index("ix_demand_imports_tenant_id", "demand_imports", ["tenant_id"])

    op.create_table(
        "hex_priors",
        sa.Column("h3_r8", sa.String(16), primary_key=True),
        sa.Column("affluence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hotels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generators", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("den_distance_mi", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone_key", sa.String(40), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_hex_priors_zone_key", "hex_priors", ["zone_key"])

    op.create_table(
        "den_flight_baseline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("dow", sa.Integer(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("departures", sa.Float(), nullable=False, server_default="0"),
        sa.Column("arrivals", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_period", sa.String(40), nullable=True),
        sa.UniqueConstraint("month", "dow", "hour", name="uq_den_flight_baseline"),
    )

    for name in ("week_scores", "hex_scores"):
        cols = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), tenant_fk, nullable=False),
            sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        ]
        if name == "week_scores":
            cols += [
                sa.Column("zone_key", sa.String(40), nullable=False),
                sa.Column("dow", sa.Integer(), nullable=False),
                sa.Column("hour", sa.Integer(), nullable=False),
            ]
        else:
            cols += [
                sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
                sa.Column("h3_r8", sa.String(16), nullable=False),
            ]
        cols += [
            sa.Column("mean", sa.Float(), nullable=False),
            sa.Column("lo", sa.Float(), nullable=False),
            sa.Column("hi", sa.Float(), nullable=False),
            sa.Column("own_share", sa.Float(), nullable=False),
            sa.Column("reasons", sa.JSON(), nullable=True),
        ]
        op.create_table(name, *cols)
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index("ix_week_scores_zone_key", "week_scores", ["zone_key"])
    op.create_index("ix_hex_scores_slot_start", "hex_scores", ["slot_start"])

    op.add_column("rate_configs", sa.Column("bridge_fare", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("rate_configs", "bridge_fare")
    for name in (
        "hex_scores",
        "week_scores",
        "den_flight_baseline",
        "hex_priors",
        "demand_imports",
        "dispatch_windows",
        "offer_events",
        "driver_state_segments",
        "uber_trips",
    ):
        op.drop_table(name)
    bind = op.get_bind()
    for name in ("segment_source", "earner_state", "uber_product"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
```

In `backend/tests/conftest.py`, add to the TRUNCATE statement, after `"client_notifications, push_subscriptions, clients "`:

```python
                "uber_trips, driver_state_segments, offer_events, dispatch_windows, "
                "demand_imports, week_scores, hex_scores, "
```

(keep `RESTART IDENTITY CASCADE` at the end; `hex_priors` and `den_flight_baseline` are not truncated — they are static).

- [ ] **Step 5: Migrate, check drift, run tests**

Run (from `backend/`, with the local docker stack up):

```bash
alembic upgrade head
alembic revision --autogenerate -m "drift-check" --rev-id drift_check
```

Expected: the generated `migrations/versions/drift_check_*.py` has empty `upgrade()`/`downgrade()` bodies (only `pass`). Delete it: `rm migrations/versions/drift_check_*.py`. If it is not empty, fix the model/migration mismatch it shows and repeat.

Then: `pytest tests/test_demand_models.py tests/test_demand_api.py -v && ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/demand.py backend/app/models/__init__.py backend/app/models/rate_config.py backend/migrations/versions/0050_demand_phase1.py backend/tests/conftest.py backend/tests/test_demand_models.py
git commit -m "feat(demand): phase 1 tables — uber trips, state segments, offers, priors, scores (migration 0050)"
```

---

### Task 3: The model — pure functions (`demand_model.py`)

**Files:**
- Create: `backend/app/services/demand_model.py`
- Test: `backend/tests/test_demand_model.py`

**Interfaces:**
- Produces (all pure, no DB/network):
  - `DENVER = ZoneInfo("America/Denver")`, `HOURS_PER_WEEK = 168`, `WINDOW_MIN = 15`, `PSEUDO_EXPOSURE_MIN = 600.0`, `DEFAULT_BASE_RATE = 0.03` (offers/min ≈ one per 33 min; tunable constant, documented).
  - `hour_of_week(at: datetime) -> int` — 0 = Monday 00:00 local Denver.
  - `local_hour_starts(day: date) -> list[datetime]` — the tz-aware start of every local hour of that day (23, 24 or 25 items).
  - `@dataclass(frozen=True) Estimate(mean: float, lo: float, hi: float, own_share: float, offers: float, exposure_min: float)`
  - `prior_rate(base: float, *, affluence: float, hotels: int, generators: int, flight_mult: float = 1.0, event_mult: float = 1.0, weather_mult: float = 1.0) -> float`
  - `posterior(prior: float, offers: float, exposure_min: float, pseudo_min: float = PSEUDO_EXPOSURE_MIN) -> Estimate`
  - `gamma_quantile(shape: float, rate: float, p: float) -> float` (Wilson–Hilferty; p ∈ {0.1, 0.5, 0.9})
  - `p_within(rate_per_min: float, minutes: int = WINDOW_MIN) -> float`
  - `pool_hours(values: list[tuple[float, float]]) -> list[tuple[float, float]]` — 168 `(offers, exposure)` pairs, ±1 hour circular, neighbour weight ½.
  - `@dataclass(frozen=True) Block(dow: int, start_hour: int, end_hour: int, expected_offers: float, mean: float)`
  - `top_blocks(grid: list[Estimate], *, threshold: float | None = None, min_hours: int = 2, limit: int = 5) -> list[Block]` — grid has 168 entries indexed by hour-of-week.
  - `bridge_worth_it(fare: float | None, bridge_fare: float, here_mean: float, dest_mean: float) -> bool`
  - `travel_penalty_fraction(grid_distance_cells: int, *, edge_m: float = 531.0, mph: float = 25.0, window_min: int = WINDOW_MIN) -> float`
  - `clamp(x: float, lo: float, hi: float) -> float`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_demand_model.py`:

```python
"""Pure-math tests for the 'Where to wait' model. No DB, no network."""
import math
from datetime import UTC, date, datetime

import pytest

from app.services import demand_model as dm


def test_hour_of_week_is_denver_local_monday_zero():
    # 2026-09-14 is a Monday. 06:00 UTC = 00:00 MDT.
    assert dm.hour_of_week(datetime(2026, 9, 14, 6, 0, tzinfo=UTC)) == 0
    # Sunday 23:00 MDT = Monday 05:00 UTC.
    assert dm.hour_of_week(datetime(2026, 9, 14, 5, 0, tzinfo=UTC)) == 167


def test_dst_days_have_23_and_25_hours():
    assert len(dm.local_hour_starts(date(2026, 3, 8))) == 23   # spring forward
    assert len(dm.local_hour_starts(date(2026, 11, 1))) == 25  # fall back
    assert len(dm.local_hour_starts(date(2026, 9, 17))) == 24


def test_prior_rate_bounds_and_direction():
    base = 0.03
    flat = dm.prior_rate(base, affluence=0.0, hotels=0, generators=0)
    assert flat == pytest.approx(base * 0.5)  # affluence 0 → ×0.5
    rich = dm.prior_rate(base, affluence=1.0, hotels=6, generators=20)
    assert rich > flat
    # Every multiplier is clamped: absurd inputs cannot explode the rate.
    crazy = dm.prior_rate(base, affluence=99, hotels=999, generators=999,
                          flight_mult=99, event_mult=99, weather_mult=99)
    assert crazy <= base * 2.5 * 2.5 * 2.0 * 3.0 * 3.0 * 1.5 + 1e-9


def test_posterior_with_no_data_is_the_prior():
    e = dm.posterior(prior=0.02, offers=0, exposure_min=0)
    assert e.mean == pytest.approx(0.02)
    assert e.own_share == 0.0
    assert e.lo <= e.mean <= e.hi


def test_posterior_converges_to_observed_rate():
    # 600 offers in 6,000 minutes = 0.1/min, far above a 0.02 prior.
    e = dm.posterior(prior=0.02, offers=600, exposure_min=6000)
    assert abs(e.mean - 0.1) < 0.01
    assert e.own_share > 0.9


def test_ten_minutes_barely_move_the_prior():
    e = dm.posterior(prior=0.02, offers=1, exposure_min=10)
    assert abs(e.mean - 0.02) / 0.02 < 0.05
    assert e.own_share < 0.02


def test_gamma_quantile_orders_and_median_near_mean():
    lo = dm.gamma_quantile(20, 1000, 0.1)
    mid = dm.gamma_quantile(20, 1000, 0.5)
    hi = dm.gamma_quantile(20, 1000, 0.9)
    assert lo < mid < hi
    assert abs(mid - 0.02) / 0.02 < 0.05


def test_p_within():
    assert dm.p_within(0.0) == 0.0
    assert dm.p_within(0.1, 15) == pytest.approx(1 - math.exp(-1.5))


def test_pool_hours_is_circular_and_half_weighted():
    vals = [(0.0, 0.0)] * 168
    vals[0] = (4.0, 100.0)
    pooled = dm.pool_hours(vals)
    assert pooled[0] == (4.0, 100.0)
    assert pooled[1] == (2.0, 50.0)
    assert pooled[167] == (2.0, 50.0)
    assert pooled[2] == (0.0, 0.0)


def _grid(hot: set[int], hot_rate: float = 0.1, cold_rate: float = 0.01) -> list[dm.Estimate]:
    return [
        dm.Estimate(mean=hot_rate if h in hot else cold_rate, lo=0, hi=1, own_share=0.5,
                    offers=0, exposure_min=0)
        for h in range(168)
    ]


def test_top_blocks_respects_min_hours_and_threshold():
    # Tuesday 04-07 (3h) and Friday 20-21 (1h) hot.
    hot = {24 + 4, 24 + 5, 24 + 6, 4 * 24 + 20}
    blocks = dm.top_blocks(_grid(hot), threshold=0.05, min_hours=2)
    assert len(blocks) == 1
    b = blocks[0]
    assert (b.dow, b.start_hour, b.end_hour) == (1, 4, 7)
    assert b.expected_offers == pytest.approx(0.1 * 60 * 3)


def test_top_blocks_default_threshold_is_top_quartile():
    hot = set(range(0, 42))  # 25% of the week hot
    blocks = dm.top_blocks(_grid(hot), min_hours=2, limit=10)
    assert blocks and all(b.mean >= 0.1 for b in blocks)


def test_bridge_rule():
    assert dm.bridge_worth_it(40, 35, here_mean=0.01, dest_mean=0.03)
    assert not dm.bridge_worth_it(30, 35, here_mean=0.01, dest_mean=0.03)  # too cheap
    assert not dm.bridge_worth_it(40, 35, here_mean=0.02, dest_mean=0.025)  # not 1.5× better
    assert not dm.bridge_worth_it(None, 35, here_mean=0.01, dest_mean=0.03)


def test_travel_penalty_fraction():
    assert dm.travel_penalty_fraction(0) == 0.0
    # 10 cells × 531 m = 5.31 km ≈ 3.3 mi at 25 mph ≈ 7.9 min of a 15-min window.
    f = dm.travel_penalty_fraction(10)
    assert 0.5 < f < 0.6
    assert dm.travel_penalty_fraction(100) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_demand_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'demand_model'`.

- [ ] **Step 3: Implement**

Create `backend/app/services/demand_model.py`:

```python
"""'Where to wait' — the math, and only the math. Pure functions, no DB/network,
so every rule here is unit-tested in isolation (same idea as zones.py/funnel_math.py).

The quantity we estimate is a RATE: Black + Black SUV offers per minute of `open`
(online-and-waiting) time in a cell/zone at an hour of the week. The probability the
UI shows is P(at least one offer within 15 min) = 1 - exp(-15·rate).

With almost no data of the owner's own, the rate is a PRIOR built from proxies. As
he logs shifts, each cell blends toward his observed rate with a Gamma-Poisson
(empirical-Bayes) update: posterior mean = (α + offers) / (β + minutes), where the
prior mean is α/β and β is "how many of his own minutes it takes to out-vote the
proxies". `own_share` = minutes / (minutes + β) is what the UI shows as "x% from
your data".

All the tunable numbers live in the constants block below, one comment each.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
HOURS_PER_WEEK = 168
WINDOW_MIN = 15

# ── Tunables ────────────────────────────────────────────────────────────────────
# Default offers/min before any data: one Black offer per ~33 minutes of waiting in
# an average cell. Replaced by the owner's global observed rate once he has logged
# ≥ 600 open minutes (see demand.py).
DEFAULT_BASE_RATE = 0.03
# Pseudo-exposure minutes of the prior: 10 hours of his own waiting in a cell make
# his data and the proxies count equally.
PSEUDO_EXPOSURE_MIN = 600.0
# Multiplier bounds (min, max). Affluence 0..1 maps linearly to 0.5..2.5.
AFFLUENCE_RANGE = (0.5, 2.5)
HOTEL_STEP, HOTEL_MAX = 0.25, 2.5        # +25% per luxury hotel within ~1 km, cap ×2.5
GENERATOR_STEP, GENERATOR_MAX = 0.10, 2.0  # +10% per generator within ~1.5 km, cap ×2
FLIGHT_RANGE = (0.5, 3.0)                # hour's DEN flights ÷ daily mean, clamped
EVENT_RANGE = (1.0, 3.0)                 # event windows only ever lift
WEATHER_RANGE = (0.7, 1.5)
# Wilson–Hilferty normal quantiles for the Gamma interval.
_Z = {0.1: -1.2815515655, 0.5: 0.0, 0.9: 1.2815515655}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ── Time ────────────────────────────────────────────────────────────────────────
def hour_of_week(at: datetime) -> int:
    """0 = Monday 00:00 in Denver … 167 = Sunday 23:00. `at` must be tz-aware."""
    local = at.astimezone(DENVER)
    return local.weekday() * 24 + local.hour


def local_hour_starts(day: date) -> list[datetime]:
    """Tz-aware start of every local hour of `day` in Denver. DST days yield 23 or 25
    entries; callers iterate these instead of assuming 24 slots."""
    start = datetime.combine(day, time(0), tzinfo=DENVER)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=DENVER)
    out: list[datetime] = []
    cur = start.astimezone(ZoneInfo("UTC"))
    end_utc = end.astimezone(ZoneInfo("UTC"))
    while cur < end_utc:
        out.append(cur.astimezone(DENVER))
        cur += timedelta(hours=1)
    return out


# ── Rate estimation ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Estimate:
    mean: float        # offers per minute
    lo: float          # 10th percentile
    hi: float          # 90th percentile
    own_share: float   # 0..1, share of the estimate that comes from the owner's data
    offers: float
    exposure_min: float


def prior_rate(
    base: float,
    *,
    affluence: float,
    hotels: int,
    generators: int,
    flight_mult: float = 1.0,
    event_mult: float = 1.0,
    weather_mult: float = 1.0,
) -> float:
    a_lo, a_hi = AFFLUENCE_RANGE
    m_aff = clamp(a_lo + clamp(affluence, 0.0, 1.0) * (a_hi - a_lo), a_lo, a_hi)
    m_hot = clamp(1.0 + HOTEL_STEP * max(0, hotels), 1.0, HOTEL_MAX)
    m_gen = clamp(1.0 + GENERATOR_STEP * max(0, generators), 1.0, GENERATOR_MAX)
    m_fl = clamp(flight_mult, *FLIGHT_RANGE)
    m_ev = clamp(event_mult, *EVENT_RANGE)
    m_we = clamp(weather_mult, *WEATHER_RANGE)
    return max(0.0, base) * m_aff * m_hot * m_gen * m_fl * m_ev * m_we


def gamma_quantile(shape: float, rate: float, p: float) -> float:
    """Approximate Gamma(shape, rate) quantile (Wilson–Hilferty). Good enough for a
    display interval; avoids a scipy dependency."""
    k = max(shape, 1e-9)
    z = _Z[p]
    c = 1.0 / (9.0 * k)
    x = k * (1.0 - c + z * math.sqrt(c)) ** 3
    return max(0.0, x) / max(rate, 1e-9)


def posterior(
    prior: float, offers: float, exposure_min: float, pseudo_min: float = PSEUDO_EXPOSURE_MIN
) -> Estimate:
    alpha = max(prior, 1e-9) * pseudo_min + max(0.0, offers)
    beta = pseudo_min + max(0.0, exposure_min)
    return Estimate(
        mean=alpha / beta,
        lo=gamma_quantile(alpha, beta, 0.1),
        hi=gamma_quantile(alpha, beta, 0.9),
        own_share=max(0.0, exposure_min) / beta,
        offers=offers,
        exposure_min=exposure_min,
    )


def p_within(rate_per_min: float, minutes: int = WINDOW_MIN) -> float:
    return 1.0 - math.exp(-max(0.0, rate_per_min) * minutes)


def pool_hours(values: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Borrow strength from the adjacent hours (weight ½ each), circular over the week."""
    n = len(values)
    out: list[tuple[float, float]] = []
    for i in range(n):
        o, e = values[i]
        for j in (i - 1, (i + 1) % n):
            oj, ej = values[j]
            o += 0.5 * oj
            e += 0.5 * ej
        out.append((o, e))
    return out


# ── Planner ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Block:
    dow: int          # 0 = Monday
    start_hour: int   # inclusive, local
    end_hour: int     # exclusive, local
    expected_offers: float
    mean: float       # average rate over the block


def top_blocks(
    grid: list[Estimate],
    *,
    threshold: float | None = None,
    min_hours: int = 2,
    limit: int = 5,
) -> list[Block]:
    """Contiguous runs (within a day) of hours whose mean ≥ threshold, ranked by
    expected offers. Default threshold = 75th percentile of the week's means."""
    if len(grid) != HOURS_PER_WEEK:
        raise ValueError("grid must have 168 entries")
    if threshold is None:
        means = sorted(e.mean for e in grid)
        threshold = means[int(0.75 * (len(means) - 1))]
    blocks: list[Block] = []
    for dow in range(7):
        h = 0
        while h < 24:
            if grid[dow * 24 + h].mean >= threshold:
                start = h
                while h < 24 and grid[dow * 24 + h].mean >= threshold:
                    h += 1
                if h - start >= min_hours:
                    hours = [grid[dow * 24 + x] for x in range(start, h)]
                    mean = sum(e.mean for e in hours) / len(hours)
                    blocks.append(
                        Block(dow, start, h, expected_offers=mean * 60 * len(hours), mean=mean)
                    )
            else:
                h += 1
    blocks.sort(key=lambda b: b.expected_offers, reverse=True)
    return blocks[:limit]


def bridge_worth_it(
    fare: float | None, bridge_fare: float, here_mean: float, dest_mean: float
) -> bool:
    """A Comfort ride is a 'bridge' when it pays enough AND lands somewhere clearly
    better (≥ 1.5× the current cell's rate)."""
    if fare is None or fare < bridge_fare:
        return False
    return dest_mean >= 1.5 * max(here_mean, 1e-9)


def travel_penalty_fraction(
    grid_distance_cells: int,
    *,
    edge_m: float = 531.0,
    mph: float = 25.0,
    window_min: int = WINDOW_MIN,
) -> float:
    """Fraction of the decision window spent driving to a cell (0 = here, 1 = out of
    reach). H3 res-8 edge ≈ 531 m; no Directions call, ever."""
    if grid_distance_cells <= 0:
        return 0.0
    miles = grid_distance_cells * edge_m / 1609.344
    minutes = miles / mph * 60.0
    return clamp(minutes / window_min, 0.0, 1.0)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_demand_model.py -v && ruff check .`
Expected: all PASS, ruff clean. If `test_gamma_quantile_orders_and_median_near_mean` fails on the 5% tolerance, the Wilson–Hilferty median for shape 20 is within 1.7% of the mean; check the argument order (`shape, rate`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demand_model.py backend/tests/test_demand_model.py
git commit -m "feat(demand): pure rate model — proxy prior, Gamma-Poisson update, week blocks"
```

---

### Task 4: Uber export parser (pure) — `uber_import.parse_zip`

**Files:**
- Create: `backend/app/services/uber_import.py` (parsing half; the DB half is Task 5)
- Test: `backend/tests/test_uber_import.py`

**Interfaces:**
- Produces:
  - `normalize_product(raw: str | None) -> str` → one of `black_suv, black, comfort, x, xl, other`.
  - `@dataclass ParsedTrip(dedup_key, product, product_raw, request_at, begin_at, dropoff_at, begin_lat, begin_lng, city, is_airport, is_scheduled, status, is_completed, fare_total, surge_multiplier, distance_mi, duration_s)`
  - `@dataclass ParsedSegment(dedup_key, state, begin_at, end_at, begin_lat, begin_lng, end_lat, end_lng)`
  - `@dataclass ParsedWindow(dedup_key, window_start, window_end, minutes_online, minutes_active, dispatches, rejections, accepts, expireds, completed_trips)`
  - `@dataclass ParsedExport(trips: list[ParsedTrip], segments: list[ParsedSegment], windows: list[ParsedWindow], files_found: list[str], files_missing: list[dict], skipped_rows: int)`
  - `parse_zip(data: bytes) -> ParsedExport` — raises `ImportError_` (`class ImportError_(ValueError)`) with codes `not_a_zip`, `no_csv`.
  - `KNOWN_FILES: dict[str, str]` kind → human consequence when missing.
  - `MAX_ZIP_BYTES = 50 * 1024 * 1024`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_uber_import.py`. The fixtures reproduce the **real headers** seen in the three export formats (Paris 2021 `;`, US 2022 `,` with coordinates, US 2025 `,` without) with a handful of synthetic rows:

```python
"""Uber driver export parsing: three real header formats, dedup, missing files."""
import io
import zipfile
from datetime import UTC, datetime

import pytest

from app.services import uber_import as ui

TRIPS_2021_HEADER = (
    "city_id;currency_code;timezone;flow;source_tag;product_type_name;global_product_name;"
    "request_timestamp_local;request_timestamp_utc;begintrip_timestamp_local;"
    "begintrip_timestamp_utc;dropoff_timestamp_local;dropoff_timestamp_utc;eta;"
    "surge_multiplier;is_surged;has_destination;is_pool_matched;is_star_power;"
    "request_to_begin_distance_miles;request_to_begin_duration_seconds;trip_distance_miles;"
    "trip_duration_seconds;status;is_completed;is_flat_rate;is_cash_trip;"
    "is_wait_time_eligible;is_rewindtrip;rewind;original_fare_local"
)
TRIPS_2021_ROW = (
    "3;EUR;Europe/Paris;p2p;;uberX;UberX;2021-02-01T11:06:29;2021-02-01T10:06:29.000Z;"
    "2021-02-01T11:12:04;2021-02-01T10:12:04.000Z;2021-02-01T11:18:20;2021-02-01T10:18:20.000Z;"
    "335;1.0;false;true;false;false;0.8;335;2.1;376;completed;true;false;false;false;false;;12.5"
)
ONOFF_2021_HEADER = (
    "earner_state;city_id;begin_lat;begin_lng;end_lat;end_lng;begin_timestamp_utc;"
    "end_timestamp_utc;duration_ms;begin_timestamp_local;end_timestamp_local"
)
ONOFF_2021_ROWS = [
    "open;3;48.78113;2.45808;48.80605;2.47143;2021-02-01T09:40:46.000Z;2021-02-01T10:06:29.000Z;"
    "1542000;2021-02-01T10:40:46.000Z;2021-02-01T11:06:29.000Z",
    "enroute;3;48.80605;2.47143;48.81098;2.46934;2021-02-01T10:06:29.000Z;2021-02-01T10:12:04.000Z;"
    "335000;2021-02-01T11:06:29.000Z;2021-02-01T11:12:04.000Z",
]
DISPATCH_2021_HEADER = (
    "start_timestamp_utc;end_timestamp_utc;start_timestamp_local;end_timestamp_local;city_id;"
    "minutes_online;minutes_active;dispatches;rejections;accepts;expireds;driver_cancellations;"
    "rider_cancellations;completed_trips;trip_fares;driver_adjusted_fares;flow_type;"
    "minutes_on_break;minutes_on_trip"
)
DISPATCH_2021_ROW = (
    "2021-02-01T09:00:00.000Z;2021-02-01T10:00:00.000Z;2021-02-01T10:00:00;2021-02-01T11:00:00;3;"
    "55.0;40.0;4;1;3;0;0;0;3;41.2;38.0;p2p;0;25"
)
TRIPS_2022_HEADER = (
    "request_time,begintrip_time,begintrip_latitude,begintrip_longitude,dropoff_time,"
    "dropoff_latitude,dropoff_longitude,status,currency,fare_profile,fare,distance,duration,"
    "surge_multiplier"
)
TRIPS_2022_ROW = (
    "2022-05-03 06:12:10 +0000 UTC,2022-05-03 06:20:44 +0000 UTC,39.61720,-104.95080,"
    "2022-05-03 06:58:01 +0000 UTC,39.85610,-104.67370,completed,USD,UberBLACK,88.40,24.1,2237,1.0"
)
TRIPS_2025_HEADER = (
    "city_name,currency_code,timezone,flow_type,product_type_name,global_product_name,"
    "license_plate,driver_trip_number,vehicle_trip_number,request_timestamp_local,"
    "request_timestamp_utc,begintrip_timestamp_local,begintrip_timestamp_utc,"
    "dropoff_timestamp_local,dropoff_timestamp_utc,eta_seconds,surge_multiplier,"
    "driver_surge_multiplier,is_surged,has_destination,is_pool_matched,is_airport_trip,"
    "is_scheduled_trip,trip_distance_miles,trip_duration_seconds,status,is_completed,"
    "original_fare_usd,wait_duration_minutes"
)
TRIPS_2025_ROW = (
    "Denver,USD,America/Denver,p2p,Black SUV,Uber Black SUV,ABC123,1200,900,"
    "2025-03-01 05:40:12,2025-03-01T12:40:12.000Z,2025-03-01 05:52:00,2025-03-01T12:52:00.000Z,"
    "2025-03-01 06:30:10,2025-03-01T13:30:10.000Z,600,1.0,1.0,false,true,false,true,false,"
    "23.4,2290,completed,true,131.50,0"
)


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_normalize_product():
    assert ui.normalize_product("Black SUV") == "black_suv"
    assert ui.normalize_product("UberBLACK") == "black"
    assert ui.normalize_product("Premier") == "black"
    assert ui.normalize_product("Uber Comfort") == "comfort"
    assert ui.normalize_product("uberX") == "x"
    assert ui.normalize_product("GREEN") == "x"
    assert ui.normalize_product("UberXL") == "xl"
    assert ui.normalize_product("Connect") == "other"
    assert ui.normalize_product(None) == "other"


def test_parse_2021_paris_format_with_segments_and_windows():
    data = _zip({
        "FR-Paris/02 - Driver Lifetime Trips.csv": TRIPS_2021_HEADER + "\n" + TRIPS_2021_ROW + "\n",
        "FR-Paris/10 - Driver Online Offline.csv":
            ONOFF_2021_HEADER + "\n" + "\n".join(ONOFF_2021_ROWS) + "\n",
        "FR-Paris/14 - Driver Dispatches Offered and Accepted.csv":
            DISPATCH_2021_HEADER + "\n" + DISPATCH_2021_ROW + "\n",
    })
    p = ui.parse_zip(data)
    assert p.files_missing == []
    assert len(p.trips) == 1 and len(p.segments) == 2 and len(p.windows) == 1
    t = p.trips[0]
    assert t.product == "x" and t.product_raw == "uberX"
    assert t.request_at == datetime(2021, 2, 1, 10, 6, 29, tzinfo=UTC)
    assert t.distance_mi == pytest.approx(2.1) and t.duration_s == 376
    assert t.is_completed is True and t.begin_lat is None
    s = p.segments[0]
    assert s.state == "open" and s.begin_lat == pytest.approx(48.78113)
    assert s.end_at == datetime(2021, 2, 1, 10, 6, 29, tzinfo=UTC)
    w = p.windows[0]
    assert w.dispatches == 4 and w.minutes_online == pytest.approx(55.0)


def test_parse_2022_us_format_keeps_pickup_coordinates():
    data = _zip({"uber-driver-sample/Trip details (Driver).csv":
                 TRIPS_2022_HEADER + "\n" + TRIPS_2022_ROW + "\n"})
    p = ui.parse_zip(data)
    t = p.trips[0]
    assert t.product == "black" and t.begin_lat == pytest.approx(39.6172)
    assert t.fare_total == pytest.approx(88.40)
    assert t.begin_at == datetime(2022, 5, 3, 6, 20, 44, tzinfo=UTC)
    kinds = {m["kind"] for m in p.files_missing}
    assert {"online_offline", "dispatches"} <= kinds


def test_parse_2025_us_format_flags_airport_and_missing_segments():
    data = _zip({"driver_lifetime_trips-0.csv": TRIPS_2025_HEADER + "\n" + TRIPS_2025_ROW + "\n",
                 "driver_payments-0.csv": "a,b\n1,2\n"})
    p = ui.parse_zip(data)
    t = p.trips[0]
    assert t.product == "black_suv" and t.is_airport is True and t.is_scheduled is False
    assert t.city == "Denver" and t.fare_total == pytest.approx(131.50)
    missing = {m["kind"]: m["consequence"] for m in p.files_missing}
    assert "online_offline" in missing and "logs" in missing["online_offline"]


def test_dedup_key_is_stable_and_row_errors_are_counted():
    good = TRIPS_2025_HEADER + "\n" + TRIPS_2025_ROW + "\n"
    bad = good + "Denver,USD,America/Denver,p2p,Black,,,,,not-a-date,,,,,,,,,,,,,,,,,,,\n"
    p1 = ui.parse_zip(_zip({"driver_lifetime_trips-0.csv": good}))
    p2 = ui.parse_zip(_zip({"driver_lifetime_trips-0.csv": bad}))
    assert p1.trips[0].dedup_key == p2.trips[0].dedup_key
    assert p2.skipped_rows == 1


def test_rejects_non_zip_and_zip_without_csv():
    with pytest.raises(ui.ImportError_) as e:
        ui.parse_zip(b"not a zip")
    assert e.value.code == "not_a_zip"
    with pytest.raises(ui.ImportError_) as e:
        ui.parse_zip(_zip({"readme.txt": "hi", "photo.png": "\x89PNG"}))
    assert e.value.code == "no_csv"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_uber_import.py -v`
Expected: FAIL — `ImportError: cannot import name 'uber_import'`.

- [ ] **Step 3: Implement the parser**

Create `backend/app/services/uber_import.py`:

```python
"""Uber driver data export → our tables.

The ZIP the owner downloads from Uber ("Request your personal Uber data") has changed
format over the years. Three layouts were seen in real exports (research appendix A):

- 2021 (EU naming): `NN - Driver Lifetime Trips.csv`, `NN - Driver Online Offline.csv`,
  `NN - Driver Dispatches Offered and Accepted.csv`, `;`-delimited.
- 2022 (US): `Trip details (Driver).csv`, `,`-delimited, WITH pickup coordinates and a
  `fare_profile` product column.
- 2025 (US): `driver_lifetime_trips-0.csv`, `,`-delimited, 73 columns, product but NO
  coordinates. Whether `Driver Online Offline` ships in the US export is unknown until
  the owner's own ZIP arrives — hence `files_missing` with a consequence per file.

`parse_zip` is pure (bytes → dataclasses) and fully unit-tested; `import_export`
(Task 5) does the idempotent upsert. Nothing here executes or writes anything from the
archive: only `.csv` members are read, in memory, under a size cap.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger("blackvolt.demand.import")

MAX_ZIP_BYTES = 50 * 1024 * 1024

# kind → consequence shown to the owner when the file is absent.
KNOWN_FILES: dict[str, str] = {
    "trips": "No trips file: nothing to learn about your products, hours or airport runs.",
    "online_offline": (
        "Driver Online Offline.csv not present: waiting locations will come only from "
        "your logs and the 30-day GPS file; request a new export monthly."
    ),
    "dispatches": (
        "Dispatches file not present: the hour-of-week offer rate starts from your trips "
        "instead of real offer counts."
    ),
}

_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("online_offline", re.compile(r"driver online offline", re.I)),
    ("dispatches", re.compile(r"dispatches offered and accepted", re.I)),
    ("trips", re.compile(r"(driver lifetime trips|driver_lifetime_trips|trip details \(driver\))", re.I)),
]


class ImportError_(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


@dataclass
class ParsedTrip:
    dedup_key: str
    product: str
    product_raw: str | None
    request_at: datetime | None
    begin_at: datetime | None
    dropoff_at: datetime | None
    begin_lat: float | None
    begin_lng: float | None
    city: str | None
    is_airport: bool
    is_scheduled: bool
    status: str | None
    is_completed: bool
    fare_total: float | None
    surge_multiplier: float | None
    distance_mi: float | None
    duration_s: int | None


@dataclass
class ParsedSegment:
    dedup_key: str
    state: str
    begin_at: datetime
    end_at: datetime | None
    begin_lat: float | None
    begin_lng: float | None
    end_lat: float | None
    end_lng: float | None


@dataclass
class ParsedWindow:
    dedup_key: str
    window_start: datetime
    window_end: datetime
    minutes_online: float
    minutes_active: float
    dispatches: int
    rejections: int
    accepts: int
    expireds: int
    completed_trips: int


@dataclass
class ParsedExport:
    trips: list[ParsedTrip] = field(default_factory=list)
    segments: list[ParsedSegment] = field(default_factory=list)
    windows: list[ParsedWindow] = field(default_factory=list)
    files_found: list[str] = field(default_factory=list)
    files_missing: list[dict] = field(default_factory=list)
    skipped_rows: int = 0


# ── Field helpers ───────────────────────────────────────────────────────────────
def normalize_product(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "other"
    if "suv" in s:
        return "black_suv"
    if "black" in s or "premier" in s:
        return "black"
    if "comfort" in s:
        return "comfort"
    if "xl" in s:
        return "xl"
    if s in {"uberx", "x", "green", "uberx share", "uber x"} or s.startswith("uberx"):
        return "x"
    return "other"


_TS_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S %z UTC",
    "%Y-%m-%d %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_ts(value: str | None, tz_name: str | None = None) -> datetime | None:
    """ISO-ish timestamps from the export. 'Z'/offset → UTC; naive → `tz_name`
    (default America/Denver) then UTC."""
    v = (value or "").strip()
    if not v:
        return None
    for fmt in _TS_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if fmt.endswith("Z") or "%z" in fmt:
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        try:
            tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("America/Denver")
        except Exception:
            tz = ZoneInfo("America/Denver")
        return dt.replace(tzinfo=tz).astimezone(UTC)
    raise ValueError(f"bad timestamp: {v!r}")


def _f(row: dict, *keys: str) -> float | None:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def _i(row: dict, *keys: str) -> int | None:
    v = _f(row, *keys)
    return int(v) if v is not None else None


def _b(row: dict, *keys: str) -> bool:
    for k in keys:
        v = (row.get(k) or "").strip().lower()
        if v:
            return v in {"true", "1", "yes", "t"}
    return False


def _s(row: dict, *keys: str) -> str | None:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return None


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def _reader(text: str) -> csv.DictReader:
    head = text.split("\n", 1)[0]
    delim = ";" if head.count(";") > head.count(",") else ","
    return csv.DictReader(io.StringIO(text), delimiter=delim)


# ── Row parsers ─────────────────────────────────────────────────────────────────
def _trip(row: dict) -> ParsedTrip:
    tz = _s(row, "timezone")
    # 2021/2025 layouts carry *_utc; the 2022 layout has request_time etc. in UTC.
    request_at = _parse_ts(_s(row, "request_timestamp_utc", "request_time"), tz) or _parse_ts(
        _s(row, "request_timestamp_local"), tz
    )
    begin_at = _parse_ts(_s(row, "begintrip_timestamp_utc", "begintrip_time"), tz) or _parse_ts(
        _s(row, "begintrip_timestamp_local"), tz
    )
    dropoff_at = _parse_ts(_s(row, "dropoff_timestamp_utc", "dropoff_time"), tz) or _parse_ts(
        _s(row, "dropoff_timestamp_local"), tz
    )
    product_raw = _s(row, "product_type_name", "global_product_name", "fare_profile")
    fare = _f(row, "original_fare_usd", "original_fare_local", "fare")
    distance = _f(row, "trip_distance_miles", "distance")
    duration = _i(row, "trip_duration_seconds", "duration")
    status = _s(row, "status")
    completed_raw = _s(row, "is_completed")
    is_completed = _b(row, "is_completed") if completed_raw else (status or "").lower() == "completed"
    return ParsedTrip(
        dedup_key=_key(request_at, begin_at, fare, distance),
        product=normalize_product(product_raw),
        product_raw=product_raw[:80] if product_raw else None,
        request_at=request_at,
        begin_at=begin_at,
        dropoff_at=dropoff_at,
        begin_lat=_f(row, "begintrip_latitude"),
        begin_lng=_f(row, "begintrip_longitude"),
        city=(_s(row, "city_name") or None),
        is_airport=_b(row, "is_airport_trip"),
        is_scheduled=_b(row, "is_scheduled_trip"),
        status=status[:30] if status else None,
        is_completed=is_completed,
        fare_total=fare,
        surge_multiplier=_f(row, "surge_multiplier"),
        distance_mi=distance,
        duration_s=duration,
    )


def _segment(row: dict) -> ParsedSegment:
    state = (_s(row, "earner_state") or "").lower()
    if state not in {"open", "enroute", "ontrip", "offline"}:
        raise ValueError(f"unknown earner_state {state!r}")
    begin_at = _parse_ts(_s(row, "begin_timestamp_utc"))
    end_at = _parse_ts(_s(row, "end_timestamp_utc"))
    if begin_at is None:
        raise ValueError("segment without begin")
    return ParsedSegment(
        dedup_key=_key(state, begin_at, end_at),
        state=state,
        begin_at=begin_at,
        end_at=end_at,
        begin_lat=_f(row, "begin_lat"),
        begin_lng=_f(row, "begin_lng"),
        end_lat=_f(row, "end_lat"),
        end_lng=_f(row, "end_lng"),
    )


def _window(row: dict) -> ParsedWindow:
    start = _parse_ts(_s(row, "start_timestamp_utc"))
    end = _parse_ts(_s(row, "end_timestamp_utc"))
    if start is None or end is None:
        raise ValueError("window without bounds")
    return ParsedWindow(
        dedup_key=_key(start, end),
        window_start=start,
        window_end=end,
        minutes_online=_f(row, "minutes_online") or 0.0,
        minutes_active=_f(row, "minutes_active") or 0.0,
        dispatches=_i(row, "dispatches") or 0,
        rejections=_i(row, "rejections") or 0,
        accepts=_i(row, "accepts") or 0,
        expireds=_i(row, "expireds") or 0,
        completed_trips=_i(row, "completed_trips") or 0,
    )


def _kind_of(name: str) -> str | None:
    base = name.rsplit("/", 1)[-1]
    if base.startswith("._") or not base.lower().endswith(".csv"):
        return None
    for kind, pat in _KIND_PATTERNS:
        if pat.search(base):
            return kind
    return None


# ── Entry point ─────────────────────────────────────────────────────────────────
def parse_zip(data: bytes) -> ParsedExport:
    if len(data) > MAX_ZIP_BYTES:
        raise ImportError_("too_large")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportError_("not_a_zip") from e
    out = ParsedExport()
    seen_kinds: set[str] = set()
    any_csv = False
    with z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".csv"):
                any_csv = True
            kind = _kind_of(info.filename)
            if kind is None:
                continue
            out.files_found.append(info.filename.rsplit("/", 1)[-1])
            seen_kinds.add(kind)
            text = z.read(info).decode("utf-8-sig", errors="replace")
            parser = {"trips": _trip, "online_offline": _segment, "dispatches": _window}[kind]
            target = {"trips": out.trips, "online_offline": out.segments, "dispatches": out.windows}[kind]
            for row in _reader(text):
                try:
                    target.append(parser(row))
                except Exception:
                    out.skipped_rows += 1
    if not any_csv:
        raise ImportError_("no_csv")
    for kind, consequence in KNOWN_FILES.items():
        if kind not in seen_kinds:
            out.files_missing.append({"kind": kind, "consequence": consequence})
    return out
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_uber_import.py -v && ruff check .`
Expected: all PASS. If `test_parse_2022_us_format_keeps_pickup_coordinates` fails on `begin_at`, the 2022 timestamp `2022-05-03 06:20:44 +0000 UTC` must match `"%Y-%m-%d %H:%M:%S %z UTC"`; check the format tuple order.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/uber_import.py backend/tests/test_uber_import.py
git commit -m "feat(demand): parse the Uber driver export (three real layouts) into trips, segments and windows"
```

---

### Task 5: Import upsert + `/demand/import` API

**Files:**
- Modify: `backend/app/services/uber_import.py` (append the DB half)
- Create: `backend/app/api/v1/demand.py` (router; extended in Tasks 6 and 9)
- Modify: `backend/app/main.py` (import + `include_router`)
- Modify: `backend/tests/test_demand_api.py` (append import tests)

**Interfaces:**
- Consumes: `parse_zip`, `ParsedExport` (Task 4); models (Task 2); `require_staff`, `resolve_tenant_id`, `get_db`.
- Produces:
  - `async def import_export(db: AsyncSession, *, tenant_id: int, data: bytes) -> dict` — the summary dict, also persisted as a `DemandImport` row. Shape: `{"files_found": [...], "files_missing": [{"kind","consequence"}], "skipped_rows": int, "trips": {"inserted","skipped","date_min","date_max","by_product": {...}}, "segments": {"inserted","skipped"}, "windows": {"inserted","skipped"}}`.
  - `async def last_import(db, *, tenant_id) -> dict | None` → `{"at": iso, **summary}`.
  - Router `router = APIRouter(tags=["demand"])` with `POST /demand/import` (multipart `file`) → 201 summary; 400 `{"detail": "not_a_zip"|"no_csv"}`; 413 `{"detail": "too_large"}`; `GET /demand/import/status` → last summary or `{"never": true}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_demand_api.py`:

```python
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
    assert [m["kind"] for m in s["files_missing"]] == ["dispatches"]
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_demand_api.py -v`
Expected: the four new tests FAIL with 404 (route missing) / import error.

- [ ] **Step 3: Append the DB half to `uber_import.py`**

Append to `backend/app/services/uber_import.py`:

```python
# ── Persistence ─────────────────────────────────────────────────────────────────
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.models import (  # noqa: E402
    DemandImport,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    SegmentSource,
    UberProduct,
    UberTrip,
)


def _round5(v: float | None) -> float | None:
    return None if v is None else round(v, 5)


async def _upsert(db: AsyncSession, table, rows: list[dict], conflict: tuple[str, ...]) -> int:
    """INSERT … ON CONFLICT DO NOTHING in chunks; returns rows actually inserted."""
    inserted = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        if not chunk:
            continue
        stmt = pg_insert(table).values(chunk).on_conflict_do_nothing(index_elements=list(conflict))
        res = await db.execute(stmt)
        inserted += res.rowcount or 0
    return inserted


async def import_export(db: AsyncSession, *, tenant_id: int, data: bytes) -> dict:
    parsed = parse_zip(data)
    trip_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": t.dedup_key,
            "product": UberProduct(t.product),
            "product_raw": t.product_raw,
            "request_at": t.request_at,
            "begin_at": t.begin_at,
            "dropoff_at": t.dropoff_at,
            "begin_lat": _round5(t.begin_lat),
            "begin_lng": _round5(t.begin_lng),
            "city": t.city,
            "is_airport": t.is_airport,
            "is_scheduled": t.is_scheduled,
            "status": t.status,
            "is_completed": t.is_completed,
            "fare_total": t.fare_total,
            "surge_multiplier": t.surge_multiplier,
            "distance_mi": t.distance_mi,
            "duration_s": t.duration_s,
        }
        for t in parsed.trips
    ]
    seg_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": s.dedup_key,
            "state": EarnerState(s.state),
            "begin_at": s.begin_at,
            "end_at": s.end_at,
            "begin_lat": _round5(s.begin_lat),
            "begin_lng": _round5(s.begin_lng),
            "end_lat": _round5(s.end_lat),
            "end_lng": _round5(s.end_lng),
            "h3_r8": _cell(s.begin_lat, s.begin_lng),
            "source": SegmentSource.EXPORT,
        }
        for s in parsed.segments
    ]
    win_rows = [
        {
            "tenant_id": tenant_id,
            "dedup_key": w.dedup_key,
            "window_start": w.window_start,
            "window_end": w.window_end,
            "minutes_online": w.minutes_online,
            "minutes_active": w.minutes_active,
            "dispatches": w.dispatches,
            "rejections": w.rejections,
            "accepts": w.accepts,
            "expireds": w.expireds,
            "completed_trips": w.completed_trips,
        }
        for w in parsed.windows
    ]
    t_ins = await _upsert(db, UberTrip, trip_rows, ("tenant_id", "dedup_key"))
    s_ins = await _upsert(db, DriverStateSegment, seg_rows, ("tenant_id", "dedup_key"))
    w_ins = await _upsert(db, DispatchWindow, win_rows, ("tenant_id", "dedup_key"))

    dates = [t.begin_at or t.request_at for t in parsed.trips if (t.begin_at or t.request_at)]
    by_product: dict[str, int] = {}
    for t in parsed.trips:
        by_product[t.product] = by_product.get(t.product, 0) + 1
    summary = {
        "files_found": parsed.files_found,
        "files_missing": parsed.files_missing,
        "skipped_rows": parsed.skipped_rows,
        "trips": {
            "inserted": t_ins,
            "skipped": len(trip_rows) - t_ins,
            "date_min": min(dates).isoformat() if dates else None,
            "date_max": max(dates).isoformat() if dates else None,
            "by_product": by_product,
        },
        "segments": {"inserted": s_ins, "skipped": len(seg_rows) - s_ins},
        "windows": {"inserted": w_ins, "skipped": len(win_rows) - w_ins},
    }
    db.add(DemandImport(tenant_id=tenant_id, summary=summary))
    await db.commit()
    return summary


async def last_import(db: AsyncSession, *, tenant_id: int) -> dict | None:
    row = (
        await db.execute(
            select(DemandImport)
            .where(DemandImport.tenant_id == tenant_id)
            .order_by(DemandImport.at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {"at": row.at.isoformat(), **row.summary}


def _cell(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    try:
        import h3

        return h3.latlng_to_cell(lat, lng, 8)
    except Exception:
        return None
```

(Move the `from sqlalchemy…`/`from app.models…` imports to the top of the module and drop the `# noqa: E402` markers before committing — ruff's `I` rule wants them sorted with the others.)

- [ ] **Step 4: Create the router and register it**

Create `backend/app/api/v1/demand.py`:

```python
"""'Where to wait' API (staff-only, tenant-scoped).

POST /demand/import          → upload the Uber data export ZIP
GET  /demand/import/status   → last import summary
POST /demand/log             → one-tap shift/offer event            (Task 6)
GET  /demand/log/today       → today's events + current state       (Task 6)
GET  /demand/week            → 7×24 planner grid + top blocks       (Task 9)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff, resolve_tenant_id
from app.db.base import get_db
from app.services import uber_import

router = APIRouter(tags=["demand"])


@router.post("/demand/import", status_code=status.HTTP_201_CREATED)
async def post_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    data = await file.read(uber_import.MAX_ZIP_BYTES + 1)
    if len(data) > uber_import.MAX_ZIP_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="too_large")
    try:
        return await uber_import.import_export(db, tenant_id=tenant_id, data=data)
    except uber_import.ImportError_ as e:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if e.code == "too_large" else 400
        raise HTTPException(status_code=code, detail=e.code) from e


@router.get("/demand/import/status")
async def get_import_status(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    last = await uber_import.last_import(db, tenant_id=tenant_id)
    return last if last is not None else {"never": True}
```

In `backend/app/main.py`: add `from app.api.v1.demand import router as demand_router` with the other imports (alphabetical, after `dashboard`), and `app.include_router(demand_router, prefix="/api/v1")` next to the other `include_router` calls.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_demand_api.py tests/test_uber_import.py -v && ruff check .`
Expected: all PASS. If `rowcount` is `-1`, asyncpg did not report it: switch `_upsert` to `stmt.returning(table.id)` and count the returned rows.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/uber_import.py backend/app/api/v1/demand.py backend/app/main.py backend/tests/test_demand_api.py
git commit -m "feat(api): import the Uber export ZIP idempotently and report what it contained"
```

---

### Task 6: One-tap shift log — `shift_log.py` + `/demand/log`

**Files:**
- Create: `backend/app/services/shift_log.py`
- Modify: `backend/app/api/v1/demand.py` (add two routes)
- Test: `backend/tests/test_shift_log.py` (API-level, through `TestClient`, like the rest of the suite)

**Interfaces:**
- Consumes: models (Task 2), settings `DEN_LOT_*` (Task 1).
- Produces:
  - `KINDS = ("online", "here", "ping", "offer", "offline")`
  - `async def log_event(db, *, tenant_id: int, client_event_id: str, kind: str, at: datetime | None = None, lat: float | None = None, lng: float | None = None, product: str | None = None, accepted: bool | None = None, fare: float | None = None, dest_text: str | None = None) -> tuple[dict, bool]` — returns `(event_dict, created)`; `created=False` when `client_event_id` was seen before (the stored event is returned unchanged).
  - `async def today(db, *, tenant_id: int, now: datetime | None = None) -> dict` → `{"state": "open"|"enroute"|"offline", "open_since": iso|None, "events": [event_dict...]}` where events are today's (Denver local) offers and segment starts, newest first.
  - `def in_den_lot(lat: float | None, lng: float | None) -> bool`
  - `def cell_of(lat, lng) -> str | None` (H3 res 8)
  - Event dict: `{"id": int, "kind": str, "at": iso, "lat": float|None, "lng": float|None, "h3_r8": str|None, "product": str|None, "accepted": bool|None, "fare": float|None, "zone_key": str|None, "no_position": bool}`.
  - Routes: `POST /demand/log` body `LogBody` → 201 on create, **200** with the stored event when `client_event_id` repeats (the PWA retries on flaky networks; a repeat is success, not an error); 422 on bad kind/product. `GET /demand/log/today`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shift_log.py`:

```python
"""One-tap shift logging: segments open/close, offers, DEN lot, idempotent retries."""
import os
import uuid

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"
os.environ["DEN_LOT_LAT"] = "39.8000"
os.environ["DEN_LOT_LNG"] = "-104.7000"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import shift_log  # noqa: E402

client = TestClient(app)
CHERRY_CREEK = (39.7170, -104.9530)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _ev(c: TestClient, kind: str, at: str, **extra) -> dict:
    body = {"client_event_id": str(uuid.uuid4()), "kind": kind, "at": at, **extra}
    r = c.post("/api/v1/demand/log", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_log_requires_staff():
    assert client.post("/api/v1/demand/log", json={}).status_code == 401
    assert client.get("/api/v1/demand/log/today").status_code == 401


def test_in_den_lot_uses_configured_circle():
    assert shift_log.in_den_lot(39.8001, -104.7001)
    assert not shift_log.in_den_lot(*CHERRY_CREEK)
    assert not shift_log.in_den_lot(None, None)


def test_sequence_closes_segments_with_durations():
    c = _owner()
    lat, lng = CHERRY_CREEK
    _ev(c, "online", "2026-09-15T14:00:00Z", lat=lat, lng=lng)
    _ev(c, "ping", "2026-09-15T14:01:00Z", lat=lat, lng=lng)
    off = _ev(c, "offer", "2026-09-15T14:20:00Z", lat=lat, lng=lng, product="black", accepted=True)
    assert off["product"] == "black" and off["accepted"] is True and off["h3_r8"]
    _ev(c, "offline", "2026-09-15T14:45:00Z", lat=lat, lng=lng)
    t = c.get("/api/v1/demand/log/today", params={"date": "2026-09-15"}).json()
    kinds = [e["kind"] for e in t["events"]]
    assert kinds == ["offline", "offer", "online"]  # pings are not listed
    assert t["state"] == "offline" and t["open_since"] is None
    # The open segment ran 14:00→14:20 (20 min), then enroute 14:20→14:45.
    segs = t["segments"]
    assert [(s["state"], s["minutes"]) for s in segs] == [("open", 20.0), ("enroute", 25.0)]


def test_offer_without_position_is_stored_and_flagged():
    c = _owner()
    e = _ev(c, "offer", "2026-09-16T01:00:00Z", product="comfort", accepted=False)
    assert e["no_position"] is True and e["h3_r8"] is None


def test_duplicate_client_event_id_returns_same_row_with_200():
    c = _owner()
    body = {"client_event_id": str(uuid.uuid4()), "kind": "offer",
            "at": "2026-09-16T02:00:00Z", "product": "black_suv", "accepted": True}
    r1 = c.post("/api/v1/demand/log", json=body)
    r2 = c.post("/api/v1/demand/log", json=body)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_here_inside_den_lot_tags_zone():
    c = _owner()
    e = _ev(c, "here", "2026-09-16T03:00:00Z", lat=39.8001, lng=-104.7001)
    assert e["zone_key"] == "den_lot"


def test_bad_kind_and_product_are_422():
    c = _owner()
    r = c.post("/api/v1/demand/log",
               json={"client_event_id": "x", "kind": "teleport", "at": "2026-09-16T04:00:00Z"})
    assert r.status_code == 422
    r = c.post("/api/v1/demand/log",
               json={"client_event_id": "y", "kind": "offer", "product": "helicopter"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_shift_log.py -v`
Expected: FAIL — `ImportError: cannot import name 'shift_log'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/shift_log.py`:

```python
"""One-tap shift log: the owner's four buttons become state segments and offers.

The model (demand_model.py) needs two things the Uber export cannot give: minutes
spent waiting in each cell (exposure) and the offers that arrived there, by product.
Every tap carries a client-generated id so a retried POST from a flaky connection is
a no-op, never a double count. Pings only extend the open segment's `last_ping_at`.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import DriverStateSegment, EarnerState, OfferEvent, SegmentSource, UberProduct
from app.services.demand_model import DENVER

KINDS = ("online", "here", "ping", "offer", "offline")
PRODUCTS = tuple(p.value for p in UberProduct)


def cell_of(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    import h3

    return h3.latlng_to_cell(lat, lng, 8)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def in_den_lot(lat: float | None, lng: float | None) -> bool:
    s = get_settings()
    if lat is None or lng is None or s.DEN_LOT_LAT is None or s.DEN_LOT_LNG is None:
        return False
    return _haversine_m(lat, lng, s.DEN_LOT_LAT, s.DEN_LOT_LNG) <= s.DEN_LOT_RADIUS_M


def _r5(v: float | None) -> float | None:
    return None if v is None else round(v, 5)


async def _open_segment(db: AsyncSession, tenant_id: int) -> DriverStateSegment | None:
    return (
        await db.execute(
            select(DriverStateSegment)
            .where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.source == SegmentSource.LIVE,
                DriverStateSegment.end_at.is_(None),
            )
            .order_by(DriverStateSegment.begin_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _close(seg: DriverStateSegment, at: datetime, lat: float | None, lng: float | None) -> None:
    seg.end_at = at
    seg.end_lat = _r5(lat) if lat is not None else seg.end_lat
    seg.end_lng = _r5(lng) if lng is not None else seg.end_lng


def _new_segment(
    tenant_id: int, key: str, state: EarnerState, at: datetime, lat, lng
) -> DriverStateSegment:
    return DriverStateSegment(
        tenant_id=tenant_id,
        dedup_key=key,
        state=state,
        begin_at=at,
        begin_lat=_r5(lat),
        begin_lng=_r5(lng),
        h3_r8=cell_of(lat, lng),
        zone_key="den_lot" if in_den_lot(lat, lng) else None,
        source=SegmentSource.LIVE,
    )


def _seg_dict(seg: DriverStateSegment, kind: str) -> dict:
    return {
        "id": seg.id,
        "kind": kind,
        "at": seg.begin_at.isoformat(),
        "lat": seg.begin_lat,
        "lng": seg.begin_lng,
        "h3_r8": seg.h3_r8,
        "product": None,
        "accepted": None,
        "fare": None,
        "zone_key": seg.zone_key,
        "no_position": seg.begin_lat is None,
    }


def _offer_dict(o: OfferEvent) -> dict:
    return {
        "id": o.id,
        "kind": "offer",
        "at": o.at.isoformat(),
        "lat": o.lat,
        "lng": o.lng,
        "h3_r8": o.h3_r8,
        "product": o.product.value,
        "accepted": o.accepted,
        "fare": float(o.fare) if o.fare is not None else None,
        "zone_key": "den_lot" if in_den_lot(o.lat, o.lng) else None,
        "no_position": o.lat is None,
    }


async def log_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    client_event_id: str,
    kind: str,
    at: datetime | None = None,
    lat: float | None = None,
    lng: float | None = None,
    product: str | None = None,
    accepted: bool | None = None,
    fare: float | None = None,
    dest_text: str | None = None,
) -> tuple[dict, bool]:
    if kind not in KINDS:
        raise ValueError("bad_kind")
    if kind == "offer" and product not in PRODUCTS:
        raise ValueError("bad_product")
    now = (at or datetime.now(UTC)).astimezone(UTC)

    # Idempotency: the same tap id always returns the row it created.
    if kind == "offer":
        dup = (
            await db.execute(
                select(OfferEvent).where(
                    OfferEvent.tenant_id == tenant_id, OfferEvent.client_event_id == client_event_id
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return _offer_dict(dup), False
    else:
        dup = (
            await db.execute(
                select(DriverStateSegment).where(
                    DriverStateSegment.tenant_id == tenant_id,
                    DriverStateSegment.dedup_key == client_event_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return _seg_dict(dup, kind), False

    current = await _open_segment(db, tenant_id)

    if kind == "ping":
        if current is not None:
            current.last_ping_at = now
            current.end_lat = _r5(lat) if lat is not None else current.end_lat
            current.end_lng = _r5(lng) if lng is not None else current.end_lng
            await db.commit()
            return _seg_dict(current, "ping"), True
        # A ping with nothing open behaves like "online".
        kind = "online"

    if kind in ("online", "here"):
        if current is not None:
            _close(current, now, lat, lng)
        seg = _new_segment(tenant_id, client_event_id, EarnerState.OPEN, now, lat, lng)
        db.add(seg)
        await db.commit()
        await db.refresh(seg)
        return _seg_dict(seg, kind), True

    if kind == "offline":
        if current is not None:
            _close(current, now, lat, lng)
        seg = _new_segment(tenant_id, client_event_id, EarnerState.OFFLINE, now, lat, lng)
        seg.end_at = now
        db.add(seg)
        await db.commit()
        await db.refresh(seg)
        return _seg_dict(seg, "offline"), True

    # kind == "offer"
    offer = OfferEvent(
        tenant_id=tenant_id,
        client_event_id=client_event_id,
        at=now,
        lat=_r5(lat),
        lng=_r5(lng),
        h3_r8=cell_of(lat, lng),
        product=UberProduct(product),
        accepted=bool(accepted),
        fare=fare,
        dest_text=(dest_text or None),
    )
    db.add(offer)
    if accepted:
        if current is not None:
            _close(current, now, lat, lng)
        db.add(
            _new_segment(
                tenant_id, f"{client_event_id}:enroute", EarnerState.ENROUTE, now, lat, lng
            )
        )
    await db.commit()
    await db.refresh(offer)
    return _offer_dict(offer), True


async def today(db: AsyncSession, *, tenant_id: int, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).astimezone(DENVER)
    start = datetime.combine(now.date(), time(0), tzinfo=DENVER).astimezone(UTC)
    end = start + timedelta(days=2)  # generous; filtered below by local date
    segs = (
        await db.execute(
            select(DriverStateSegment)
            .where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.source == SegmentSource.LIVE,
                DriverStateSegment.begin_at >= start,
                DriverStateSegment.begin_at < end,
            )
            .order_by(DriverStateSegment.begin_at.asc())
        )
    ).scalars().all()
    segs = [s for s in segs if s.begin_at.astimezone(DENVER).date() == now.date()]
    offers = (
        await db.execute(
            select(OfferEvent)
            .where(OfferEvent.tenant_id == tenant_id, OfferEvent.at >= start, OfferEvent.at < end)
            .order_by(OfferEvent.at.asc())
        )
    ).scalars().all()
    offers = [o for o in offers if o.at.astimezone(DENVER).date() == now.date()]

    events: list[dict] = []
    for s in segs:
        if s.state == EarnerState.ENROUTE:
            continue  # represented by its accepted offer
        events.append(_seg_dict(s, "online" if s.state == EarnerState.OPEN else "offline"))
    events += [_offer_dict(o) for o in offers]
    events.sort(key=lambda e: e["at"], reverse=True)

    current = await _open_segment(db, tenant_id)
    state = current.state.value if current is not None else "offline"
    seg_out = []
    for s in segs:
        if s.state == EarnerState.OFFLINE:
            continue
        end_at = s.end_at or s.last_ping_at or s.begin_at
        seg_out.append(
            {
                "state": s.state.value,
                "begin_at": s.begin_at.isoformat(),
                "end_at": s.end_at.isoformat() if s.end_at else None,
                "minutes": round((end_at - s.begin_at).total_seconds() / 60.0, 1),
                "zone_key": s.zone_key,
                "h3_r8": s.h3_r8,
            }
        )
    return {
        "state": state,
        "open_since": current.begin_at.isoformat() if current is not None else None,
        "events": events,
        "segments": seg_out,
    }
```

- [ ] **Step 4: Add the routes**

In `backend/app/api/v1/demand.py` add the imports `from datetime import UTC, datetime`, `from pydantic import BaseModel, Field`, `from fastapi import Query, Response` (merge with the existing `fastapi` import), `from app.services import shift_log`, and:

```python
class LogBody(BaseModel):
    client_event_id: str = Field(min_length=1, max_length=64)
    kind: str
    at: datetime | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    product: str | None = None
    accepted: bool | None = None
    fare: float | None = Field(default=None, ge=0, le=10000)
    dest_text: str | None = Field(default=None, max_length=200)


@router.post("/demand/log", status_code=status.HTTP_201_CREATED)
async def post_log(
    body: LogBody,
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    try:
        event, created = await shift_log.log_event(
            db,
            tenant_id=tenant_id,
            client_event_id=body.client_event_id,
            kind=body.kind,
            at=body.at,
            lat=body.lat,
            lng=body.lng,
            product=body.product,
            accepted=body.accepted,
            fare=body.fare,
            dest_text=body.dest_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    if not created:
        response.status_code = status.HTTP_200_OK
    return event


@router.get("/demand/log/today")
async def get_log_today(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    now = None
    if date:
        y, m, d = (int(x) for x in date.split("-"))
        now = datetime(y, m, d, 12, 0, tzinfo=shift_log.DENVER).astimezone(UTC)
    return await shift_log.today(db, tenant_id=tenant_id, now=now)
```

(`date` is a test/debug convenience: the UI never sends it.)

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_shift_log.py tests/test_demand_api.py -v && ruff check .`
Expected: all PASS. If the sequence test's minutes are off, check that `_close` is called before the new segment is added and that `at` from the body is used (not `now()`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/shift_log.py backend/app/api/v1/demand.py backend/tests/test_shift_log.py
git commit -m "feat(api): one-tap shift log — open/enroute/offline segments, offers by product, idempotent taps"
```

---

### Task 7: Curated places, geocoding script, Census priors — `hex_priors`

**Files:**
- Create: `backend/app/services/demand_places.py`
- Create: `backend/app/scripts/geocode_places.py`
- Create: `backend/data/demand_places.json` (generated by the script, committed)
- Create: `backend/app/services/demand_prior.py`
- Create: `backend/app/scripts/build_demand_priors.py`
- Test: `backend/tests/test_demand_prior.py`

**Interfaces:**
- Consumes: `TARGET_ZONES` from `app/services/uber_research.py` (10 zones with `key, name, lat, lng, affluence`).
- Produces:
  - `demand_places.py`: `LUXURY_HOTELS: list[dict]` (`name, address`), `FBOS: list[dict]`, `GENERATORS: list[dict]`, `ZONES: list[dict]` (`key, name, lat, lng, radius_mi`), `DEN_TERMINAL = (39.8561, -104.6737)`, `METRO_BBOX = (39.50, -105.35, 40.10, -104.60)`, `load_geocoded() -> dict[str, tuple[float, float]]` (name → lat/lng from `data/demand_places.json`, `{}` if absent).
  - `demand_prior.py`: `affluence_score(median_income: float | None, share_200k: float | None) -> float` (0..1); `cells_for_polygon(rings: list[list[tuple[float, float]]]) -> set[str]` (lat/lng rings → res-8 cells); `zone_for(lat: float, lng: float) -> str | None`; `build_priors(*, tracts: list[dict], places: dict[str, tuple[float, float]]) -> dict[str, dict]` (pure: tract = `{"income", "share_200k", "rings"}`; returns `h3 → {affluence, hotels, generators, den_distance_mi, zone_key}`); `async def fetch_census(counties: list[str]) -> list[dict]` (network); `async def save_priors(db, rows: dict[str, dict]) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_demand_prior.py`:

```python
"""Static priors: affluence score, polygon → cells, zone lookup, prior assembly."""
import pytest

from app.services import demand_places as places
from app.services import demand_prior as dp


def test_affluence_score_bounds():
    assert dp.affluence_score(None, None) == 0.0
    assert dp.affluence_score(45000, 0.02) < 0.3
    assert dp.affluence_score(150000, 0.30) == pytest.approx(1.0)
    assert dp.affluence_score(400000, 0.9) == 1.0


def test_cells_for_polygon_covers_a_small_square():
    # ~1.5 km square around Cherry Creek → a handful of res-8 cells (≈0.74 km² each).
    ring = [(39.710, -104.960), (39.710, -104.945), (39.724, -104.945), (39.724, -104.960)]
    cells = dp.cells_for_polygon([ring])
    assert 1 <= len(cells) <= 6
    assert all(len(c) == 15 for c in cells)


def test_zone_for_uses_curated_zones_and_den():
    assert dp.zone_for(39.6425, -104.9550) == "cherry_hills"
    assert dp.zone_for(39.8561, -104.6737) == "den"
    assert dp.zone_for(40.60, -105.10) is None  # Fort Collins: outside every zone


def test_build_priors_counts_places_and_distance():
    ring = [(39.710, -104.960), (39.710, -104.945), (39.724, -104.945), (39.724, -104.960)]
    tracts = [{"income": 150000, "share_200k": 0.30, "rings": [ring]}]
    geocoded = {"Hotel Clio": (39.7176, -104.9532), "Signature APA-South": (39.5700, -104.8500)}
    rows = dp.build_priors(tracts=tracts, places=geocoded)
    assert rows
    cell = next(iter(rows))
    row = rows[cell]
    assert row["affluence"] == pytest.approx(1.0)
    assert row["hotels"] >= 1  # Clio is inside/near the square
    assert row["generators"] == 0  # the FBO is 15+ km away
    assert 15 < row["den_distance_mi"] < 25
    assert row["zone_key"] == "cherry_creek"


def test_curated_lists_have_names_and_addresses():
    for lst in (places.LUXURY_HOTELS, places.FBOS, places.GENERATORS):
        assert lst and all(p["name"] and p["address"] for p in lst)
    assert {z["key"] for z in places.ZONES} >= {"cherry_hills", "greenwood_dtc", "den", "downtown"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_demand_prior.py -v`
Expected: FAIL — `ImportError: cannot import name 'demand_places'`.

- [ ] **Step 3: Write the curated lists**

Create `backend/app/services/demand_places.py`. Names/addresses come from the research (AAA 4–5 Diamond + Forbes, FBO listings); coordinates are **never typed here** — the geocoding script fills `data/demand_places.json` from OpenStreetMap:

```python
"""Curated premium-demand generators for the Denver metro. Code constant like
venue_profiles.py: a short list the owner reviews, no per-request cost.

Coordinates come from `data/demand_places.json`, produced once by
`python -m app.scripts.geocode_places` (OpenStreetMap Nominatim, ODbL) — never from
Google Places, whose policy forbids storing anything but place_id.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.uber_research import TARGET_ZONES

DEN_TERMINAL = (39.8561, -104.6737)
METRO_BBOX = (39.50, -105.35, 40.10, -104.60)  # south, west, north, east
_DATA = Path(__file__).resolve().parents[2] / "data" / "demand_places.json"

LUXURY_HOTELS: list[dict] = [
    {"name": "Four Seasons Hotel Denver", "address": "1111 14th St, Denver, CO 80202"},
    {"name": "The Ritz-Carlton, Denver", "address": "1881 Curtis St, Denver, CO 80202"},
    {"name": "The Brown Palace Hotel", "address": "321 17th St, Denver, CO 80202"},
    {"name": "The Oxford Hotel", "address": "1600 17th St, Denver, CO 80202"},
    {"name": "The Crawford Hotel", "address": "1701 Wynkoop St, Denver, CO 80202"},
    {"name": "Limelight Hotel Denver", "address": "1600 Wewatta St, Denver, CO 80202"},
    {"name": "Thompson Denver", "address": "1616 Market St, Denver, CO 80202"},
    {"name": "Kimpton Hotel Monaco Denver", "address": "1717 Champa St, Denver, CO 80202"},
    {"name": "Le Méridien Denver Downtown", "address": "1475 California St, Denver, CO 80202"},
    {"name": "Populus", "address": "240 14th St, Denver, CO 80202"},
    {"name": "Hotel Clio", "address": "150 Clayton Ln, Denver, CO 80206"},
    {"name": "Halcyon, a hotel in Cherry Creek", "address": "245 Columbine St, Denver, CO 80206"},
    {"name": "Clayton Hotel & Members Club", "address": "233 Clayton St, Denver, CO 80206"},
    {"name": "Kimpton Claret Hotel", "address": "6985 E Chenango Ave, Denver, CO 80237"},
    {"name": "The Inverness Denver", "address": "200 Inverness Dr W, Englewood, CO 80112"},
    {"name": "Omni Interlocken Hotel", "address": "500 Interlocken Blvd, Broomfield, CO 80021"},
    {"name": "Gaylord Rockies Resort", "address": "6700 N Gaylord Rockies Blvd, Aurora, CO 80019"},
    {"name": "St Julien Hotel & Spa", "address": "900 Walnut St, Boulder, CO 80302"},
]

FBOS: list[dict] = [
    {"name": "Signature APA-South", "address": "7625 S Peoria St, Englewood, CO 80112"},
    {"name": "Signature APA-North", "address": "7425 S Peoria Cir, Englewood, CO 80112"},
    {"name": "Modern Aviation Centennial", "address": "7800 S Peoria St, Englewood, CO 80112"},
    {"name": "Denver jetCenter", "address": "7850 S Peoria St, Englewood, CO 80112"},
    {"name": "Signature BJC", "address": "11755 Airport Way, Broomfield, CO 80021"},
    {"name": "Sheltair BJC", "address": "11705 Airport Way, Broomfield, CO 80021"},
    {"name": "Signature Aviation DEN", "address": "7850 N Peña Blvd, Denver, CO 80249"},
]

GENERATORS: list[dict] = [
    {"name": "Cherry Creek Shopping Center", "address": "3000 E 1st Ave, Denver, CO 80206"},
    {"name": "Denver Tech Center", "address": "Denver Tech Center, Greenwood Village, CO"},
    {"name": "Union Station Denver", "address": "1701 Wynkoop St, Denver, CO 80202"},
    {"name": "Colorado Convention Center", "address": "700 14th St, Denver, CO 80202"},
    {"name": "Anschutz Medical Campus", "address": "13001 E 17th Pl, Aurora, CO 80045"},
    {"name": "Cherry Hills Country Club", "address": "4125 S University Blvd, Cherry Hills Village, CO 80113"},
    {"name": "Denver Country Club", "address": "1700 E 1st Ave, Denver, CO 80218"},
    {"name": "Belleview Station", "address": "4900 S Newport St, Denver, CO 80237"},
    {"name": "Park Meadows", "address": "8401 Park Meadows Center Dr, Lone Tree, CO 80124"},
    {"name": "Empower Field at Mile High", "address": "1701 Bryant St, Denver, CO 80204"},
    {"name": "Ball Arena", "address": "1000 Chopper Cir, Denver, CO 80204"},
    {"name": "Coors Field", "address": "2001 Blake St, Denver, CO 80205"},
]

# Zones = the research's affluent origins (uber_research.TARGET_ZONES) + the two
# places the owner actually waits at. radius_mi decides which cells roll up to a zone.
ZONES: list[dict] = [
    {"key": z["key"], "name": z["name"], "lat": z["lat"], "lng": z["lng"], "radius_mi": 2.5}
    for z in TARGET_ZONES
] + [
    {"key": "den", "name": "DEN Airport", "lat": DEN_TERMINAL[0], "lng": DEN_TERMINAL[1],
     "radius_mi": 4.0},
    {"key": "downtown", "name": "Downtown Denver", "lat": 39.7392, "lng": -104.9903,
     "radius_mi": 1.5},
]


def load_geocoded() -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {k: (float(v["lat"]), float(v["lng"])) for k, v in raw.items()}
```

`TARGET_ZONES` already includes `lodo`; keep it (its 2.5-mile radius overlaps `downtown`; `zone_for` returns the **nearest** centre, so cells split cleanly).

- [ ] **Step 4: Write the geocoding script and run it once**

Create `backend/app/scripts/geocode_places.py`:

```python
"""Geocode the curated places once with OpenStreetMap Nominatim → data/demand_places.json.
Usage policy: 1 request/second, identifying User-Agent, results cached (this file).
Run locally:  cd backend && python -m app.scripts.geocode_places
Re-run only when demand_places.py changes; commit the JSON.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from app.services import demand_places as places

OUT = Path(__file__).resolve().parents[2] / "data" / "demand_places.json"
UA = "BlackVoltMobility/1.0 (blackvoltmobility@gmail.com)"


def main() -> None:
    existing: dict = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
    out = dict(existing)
    with httpx.Client(timeout=20.0, headers={"User-Agent": UA}) as http:
        for p in places.LUXURY_HOTELS + places.FBOS + places.GENERATORS:
            if p["name"] in out:
                continue
            r = http.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": p["address"], "format": "json", "limit": 1, "countrycodes": "us"},
            )
            r.raise_for_status()
            hits = r.json()
            if not hits:
                print(f"NOT FOUND: {p['name']} — {p['address']}")
            else:
                out[p["name"]] = {
                    "lat": round(float(hits[0]["lat"]), 5),
                    "lng": round(float(hits[0]["lon"]), 5),
                    "display": hits[0].get("display_name", ""),
                }
                print(f"{p['name']}: {out[p['name']]['lat']}, {out[p['name']]['lng']}")
            time.sleep(1.1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(out)} places)")


if __name__ == "__main__":
    main()
```

Run: `cd backend && python -m app.scripts.geocode_places`
Expected: one line per place with coordinates; any `NOT FOUND` line means the address needs a simpler form (e.g. drop the suite) — fix it in `demand_places.py` and re-run. Open `data/demand_places.json` and sanity-check that every latitude is 39.5–40.1 and longitude −105.4 to −104.6; a hit outside the metro is a wrong match — fix the address and re-run.

- [ ] **Step 5: Implement `demand_prior.py`**

Create `backend/app/services/demand_prior.py`:

```python
"""Static per-cell priors: where the money lives (Census ACS), where it sleeps
(luxury hotels), what generates premium trips (FBOs, offices, venues) and how far
DEN is. Rebuilt by `app.scripts.build_demand_priors`; read by demand.py.
"""
from __future__ import annotations

import logging
import math

import h3
import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import HexPrior
from app.services import demand_places as dpl

logger = logging.getLogger("blackvolt.demand.prior")

# Denver metro counties (FIPS): Adams, Arapahoe, Boulder, Broomfield, Denver, Douglas, Jefferson.
METRO_COUNTIES = ["001", "005", "013", "014", "031", "035", "059"]
_CENSUS = "https://api.census.gov/data/2024/acs/acs5"
_VARS = "NAME,B19013_001E,B19001_001E,B19001_017E"
_HOTEL_RING = 2      # res-8 k-ring 2 ≈ 1 km
_GENERATOR_RING = 3  # ≈ 1.5 km


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def affluence_score(median_income: float | None, share_200k: float | None) -> float:
    """0..1. Median income of $150k or a 30% share of $200k+ households each count as
    'fully affluent'; the two halves add."""
    inc = clamp01((median_income or 0.0) / 150000.0)
    share = clamp01((share_200k or 0.0) / 0.30)
    return clamp01(0.5 * inc + 0.5 * share)


def cells_for_polygon(rings: list[list[tuple[float, float]]]) -> set[str]:
    """Rings are lists of (lat, lng); first = outer, rest = holes."""
    outer, holes = rings[0], rings[1:]
    poly = h3.LatLngPoly(outer, *holes)
    return set(h3.polygon_to_cells(poly, 8))


def _miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def zone_for(lat: float, lng: float) -> str | None:
    best, best_d = None, 1e9
    for z in dpl.ZONES:
        d = _miles(lat, lng, z["lat"], z["lng"])
        if d <= z["radius_mi"] and d < best_d:
            best, best_d = z["key"], d
    return best


def build_priors(
    *, tracts: list[dict], places: dict[str, tuple[float, float]]
) -> dict[str, dict]:
    """Pure assembly. `tracts`: [{"income", "share_200k", "rings"}]. `places`: name → (lat, lng)."""
    rows: dict[str, dict] = {}
    for t in tracts:
        score = affluence_score(t.get("income"), t.get("share_200k"))
        for cell in cells_for_polygon(t["rings"]):
            rows[cell] = {"affluence": score, "hotels": 0, "generators": 0}
    hotel_names = {p["name"] for p in dpl.LUXURY_HOTELS}
    for name, (lat, lng) in places.items():
        centre = h3.latlng_to_cell(lat, lng, 8)
        is_hotel = name in hotel_names
        ring = _HOTEL_RING if is_hotel else _GENERATOR_RING
        for cell in h3.grid_disk(centre, ring):
            row = rows.setdefault(cell, {"affluence": 0.0, "hotels": 0, "generators": 0})
            row["hotels" if is_hotel else "generators"] += 1
    for cell, row in rows.items():
        lat, lng = h3.cell_to_latlng(cell)
        row["den_distance_mi"] = round(_miles(lat, lng, *dpl.DEN_TERMINAL), 2)
        row["zone_key"] = zone_for(lat, lng)
    return rows


async def fetch_census(counties: list[str] | None = None) -> list[dict]:
    """ACS 5-year 2020-2024 tract rows + TIGERweb tract polygons for the metro counties.
    Returns [{"geoid", "income", "share_200k", "rings"}]. Needs CENSUS_API_KEY."""
    key = get_settings().CENSUS_API_KEY
    if not key:
        raise RuntimeError("CENSUS_API_KEY is not set")
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0) as http:
        for county in counties or METRO_COUNTIES:
            r = await http.get(
                _CENSUS,
                params={"get": _VARS, "for": "tract:*", "in": f"state:08 county:{county}", "key": key},
            )
            r.raise_for_status()
            header, *data = r.json()
            idx = {h: i for i, h in enumerate(header)}
            stats: dict[str, tuple[float | None, float | None]] = {}
            for row in data:
                geoid = f"08{row[idx['county']]}{row[idx['tract']]}"
                inc = float(row[idx["B19013_001E"]]) if row[idx["B19013_001E"]] not in (None, "", "-666666666") else None
                total = float(row[idx["B19001_001E"]] or 0)
                rich = float(row[idx["B19001_017E"]] or 0)
                stats[geoid] = (inc, (rich / total) if total else None)
            g = await http.get(
                "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/8/query",
                params={
                    "where": f"STATE='08' AND COUNTY='{county}'",
                    "outFields": "GEOID",
                    "f": "geojson",
                    "outSR": "4326",
                },
            )
            g.raise_for_status()
            for feat in g.json().get("features", []):
                geoid = feat["properties"]["GEOID"]
                geom = feat["geometry"]
                polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
                inc, share = stats.get(geoid, (None, None))
                for poly in polys:
                    rings = [[(lat, lng) for lng, lat in ring] for ring in poly]
                    out.append({"geoid": geoid, "income": inc, "share_200k": share, "rings": rings})
    return out


async def save_priors(db: AsyncSession, rows: dict[str, dict]) -> int:
    await db.execute(delete(HexPrior))
    db.add_all(
        HexPrior(
            h3_r8=cell,
            affluence=r["affluence"],
            hotels=r["hotels"],
            generators=r["generators"],
            den_distance_mi=r["den_distance_mi"],
            zone_key=r["zone_key"],
        )
        for cell, r in rows.items()
    )
    await db.commit()
    return len(rows)
```

The TIGERweb layer id `8` is "Census Tracts" in the `Tracts_Blocks` service; if the query returns an error naming the layer, list the service (`…/MapServer?f=json`) and use the layer whose name is `Census Tracts`.

- [ ] **Step 6: Write the build script**

Create `backend/app/scripts/build_demand_priors.py`:

```python
"""Rebuild hex_priors from Census ACS + TIGERweb polygons + the geocoded places.
Run on the VPS after deploy and whenever demand_places.py changes:
  docker compose exec -T backend python -m app.scripts.build_demand_priors
Needs CENSUS_API_KEY in .env. Idempotent: truncates and rebuilds.
"""
from __future__ import annotations

import asyncio

from app.db.base import get_session_factory
from app.services import demand_places, demand_prior


async def main() -> None:
    tracts = await demand_prior.fetch_census()
    rows = demand_prior.build_priors(tracts=tracts, places=demand_places.load_geocoded())
    async with get_session_factory()() as db:
        n = await demand_prior.save_priors(db, rows)
    zones = sum(1 for r in rows.values() if r["zone_key"])
    print(f"hex_priors: {n} cells from {len(tracts)} tract polygons; {zones} cells in a zone")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_demand_prior.py -v && ruff check .`
Expected: all PASS. `test_cells_for_polygon_covers_a_small_square` depends on the h3 4.x API: `h3.LatLngPoly(outer, *holes)` and `h3.polygon_to_cells(poly, 8)`; if `polygon_to_cells` is missing in the installed version, use `h3.h3shape_to_cells(poly, 8)`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/demand_places.py backend/app/scripts/geocode_places.py backend/data/demand_places.json backend/app/services/demand_prior.py backend/app/scripts/build_demand_priors.py backend/tests/test_demand_prior.py
git commit -m "feat(demand): curated luxury places (geocoded via OSM) and Census-based hex priors"
```

---

### Task 8: DEN flight baseline from BTS On-Time — `flights_baseline.py`

**Files:**
- Create: `backend/app/services/flights_baseline.py`
- Create: `backend/app/scripts/build_flight_baseline.py`
- Test: `backend/tests/test_flights_baseline.py`

**Interfaces:**
- Produces:
  - `bin_rows(rows: Iterable[dict]) -> dict[tuple[int, int, int], dict]` — pure; rows are BTS On-Time dicts with `FlightDate` (`YYYY-MM-DD`), `Origin`, `Dest`, `CRSDepTime`, `CRSArrTime` (`hhmm`); returns `(month, dow, hour) → {"departures": avg/day, "arrivals": avg/day, "days": int}` for DEN only.
  - `multipliers(baseline: dict[tuple[int, int, int], dict], *, month: int, dow: int) -> list[float]` — 24 values: `(dep+arr at hour) / mean over the day`, clamped to `FLIGHT_RANGE`, `1.0` everywhere when the day is missing.
  - `iter_month(year: int, month: int) -> Iterator[dict]` — downloads the BTS zip for that month to a temp file and streams the CSV rows (network).
  - `async def save_baseline(db, bins: dict, source_period: str) -> int`.
  - `async def load_baseline(db) -> dict[tuple[int, int, int], dict]`.
  - `BTS_URL = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_flights_baseline.py`:

```python
"""BTS On-Time rows → typical DEN departures/arrivals per (month, dow, hour)."""
import pytest

from app.services import flights_baseline as fb


def _row(date: str, origin: str, dest: str, dep: str, arr: str) -> dict:
    return {"FlightDate": date, "Origin": origin, "Dest": dest, "CRSDepTime": dep, "CRSArrTime": arr}


def test_bin_rows_counts_den_only_and_averages_per_day():
    rows = [
        _row("2026-06-01", "DEN", "LAX", "0605", "0730"),  # Monday 6am departure
        _row("2026-06-01", "DEN", "SFO", "0640", "0800"),
        _row("2026-06-08", "DEN", "ORD", "0615", "0900"),  # next Monday
        _row("2026-06-01", "LAX", "DEN", "1200", "1530"),  # arrival 15:xx
        _row("2026-06-01", "LAX", "SFO", "0600", "0700"),  # not DEN → ignored
        _row("2026-06-01", "DEN", "LAX", "2400", "0130"),  # 2400 = midnight edge → hour 0
    ]
    bins = fb.bin_rows(rows)
    mon6 = bins[(6, 0, 6)]
    assert mon6["days"] == 2 and mon6["departures"] == pytest.approx(1.5)  # 3 over 2 Mondays
    assert bins[(6, 0, 15)]["arrivals"] == pytest.approx(0.5)
    assert bins[(6, 0, 0)]["departures"] == pytest.approx(0.5)
    assert (6, 0, 12) not in bins or bins[(6, 0, 12)]["departures"] == 0


def test_multipliers_relative_and_clamped():
    bins = {(6, 0, h): {"departures": 10.0, "arrivals": 10.0, "days": 4} for h in range(24)}
    bins[(6, 0, 6)] = {"departures": 80.0, "arrivals": 10.0, "days": 4}
    m = fb.multipliers(bins, month=6, dow=0)
    assert len(m) == 24
    assert m[6] > m[12] and m[6] <= fb.FLIGHT_RANGE[1]
    assert fb.multipliers(bins, month=1, dow=3) == [1.0] * 24


def test_bts_url_shape():
    assert fb.BTS_URL.format(year=2026, month=6).endswith("_2026_6.zip")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flights_baseline.py -v`
Expected: FAIL — import error.

- [ ] **Step 3: Implement**

Create `backend/app/services/flights_baseline.py`:

```python
"""Typical DEN flight banks from BTS On-Time Reporting (free, monthly, ~6-week lag).
Domestic scheduled flights of the large US carriers only — enough for a RELATIVE
hour-of-day multiplier (this hour ÷ the day's mean), which is all Phase 1 uses.
"""
from __future__ import annotations

import csv
import io
import logging
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DenFlightBaseline
from app.services.demand_model import FLIGHT_RANGE, clamp

logger = logging.getLogger("blackvolt.demand.flights")

BTS_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)


def _hour(hhmm: str | None) -> int | None:
    v = (hhmm or "").strip()
    if not v or not v.isdigit():
        return None
    h = int(v) // 100
    return 0 if h == 24 else (h if 0 <= h <= 23 else None)


def bin_rows(rows: Iterable[dict]) -> dict[tuple[int, int, int], dict]:
    counts: dict[tuple[int, int, int], dict] = defaultdict(
        lambda: {"departures": 0.0, "arrivals": 0.0}
    )
    days_seen: dict[tuple[int, int], set[str]] = defaultdict(set)
    for r in rows:
        try:
            d = date.fromisoformat((r.get("FlightDate") or "")[:10])
        except ValueError:
            continue
        key_day = (d.month, d.weekday())
        if r.get("Origin") == "DEN":
            h = _hour(r.get("CRSDepTime"))
            if h is not None:
                counts[(d.month, d.weekday(), h)]["departures"] += 1
                days_seen[key_day].add(d.isoformat())
        if r.get("Dest") == "DEN":
            h = _hour(r.get("CRSArrTime"))
            if h is not None:
                counts[(d.month, d.weekday(), h)]["arrivals"] += 1
                days_seen[key_day].add(d.isoformat())
    out: dict[tuple[int, int, int], dict] = {}
    for (m, dow, h), c in counts.items():
        n = max(1, len(days_seen[(m, dow)]))
        out[(m, dow, h)] = {
            "departures": c["departures"] / n,
            "arrivals": c["arrivals"] / n,
            "days": n,
        }
    return out


def multipliers(baseline: dict[tuple[int, int, int], dict], *, month: int, dow: int) -> list[float]:
    vals = [
        baseline.get((month, dow, h), {}).get("departures", 0.0)
        + baseline.get((month, dow, h), {}).get("arrivals", 0.0)
        for h in range(24)
    ]
    mean = sum(vals) / 24.0
    if mean <= 0:
        return [1.0] * 24
    return [clamp(v / mean, *FLIGHT_RANGE) for v in vals]


def iter_month(year: int, month: int) -> Iterator[dict]:
    """Stream one month of BTS rows (zip ≈ 30 MB) via a temp file; only the five
    columns we need survive."""
    url = BTS_URL.format(year=year, month=month)
    with tempfile.TemporaryFile() as tmp:
        with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                tmp.write(chunk)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                for row in reader:
                    if row.get("Origin") == "DEN" or row.get("Dest") == "DEN":
                        yield {
                            k: row.get(k)
                            for k in ("FlightDate", "Origin", "Dest", "CRSDepTime", "CRSArrTime")
                        }


async def save_baseline(db: AsyncSession, bins: dict, source_period: str) -> int:
    await db.execute(delete(DenFlightBaseline))
    db.add_all(
        DenFlightBaseline(
            month=m, dow=dow, hour=h,
            departures=v["departures"], arrivals=v["arrivals"], source_period=source_period,
        )
        for (m, dow, h), v in bins.items()
    )
    await db.commit()
    return len(bins)


async def load_baseline(db: AsyncSession) -> dict[tuple[int, int, int], dict]:
    rows = (await db.execute(select(DenFlightBaseline))).scalars().all()
    return {
        (r.month, r.dow, r.hour): {"departures": r.departures, "arrivals": r.arrivals, "days": 0}
        for r in rows
    }
```

Create `backend/app/scripts/build_flight_baseline.py`:

```python
"""Rebuild den_flight_baseline from the last 12 available BTS On-Time months.
Run monthly on the VPS (cron or by hand):
  docker compose exec -T backend python -m app.scripts.build_flight_baseline
Fails soft per month: a month BTS has not published yet is skipped and logged.
"""
from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.db.base import get_session_factory
from app.services import flights_baseline as fb


def _months(n: int = 12) -> list[tuple[int, int]]:
    today = date.today()
    y, m = today.year, today.month - 2  # BTS lags ~6 weeks; start two months back
    out = []
    for _ in range(n):
        if m <= 0:
            m += 12
            y -= 1
        out.append((y, m))
        m -= 1
    return out


async def main() -> None:
    rows: list[dict] = []
    used: list[str] = []
    for y, m in _months():
        try:
            n0 = len(rows)
            rows.extend(fb.iter_month(y, m))
            used.append(f"{y}-{m:02d}")
            print(f"{y}-{m:02d}: {len(rows) - n0} DEN rows")
        except httpx.HTTPStatusError as e:
            print(f"{y}-{m:02d}: not available ({e.response.status_code}), skipped")
    if not rows:
        print("no BTS data downloaded; baseline left unchanged")
        return
    bins = fb.bin_rows(rows)
    async with get_session_factory()() as db:
        n = await fb.save_baseline(db, bins, source_period=f"{used[-1]}..{used[0]}")
    print(f"den_flight_baseline: {n} (month,dow,hour) bins from {len(used)} months")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_flights_baseline.py -v && ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/flights_baseline.py backend/app/scripts/build_flight_baseline.py backend/tests/test_flights_baseline.py
git commit -m "feat(demand): DEN hour-of-week flight baseline from BTS On-Time data"
```

---

### Task 15: GPS analytics import — `gps_import.py` (added 2026-09-17; runs after Task 8, before Task 9)

Binding text: spec **Addendum A**. Owner decisions (2026-09-17): home excluded from exposure; "Your waits this month" in the Import tab; manual logging is offers-only. Every threshold below was measured on the owner's real export (218,344 pings, 27 days), not guessed.

**Files:**
- Create: `backend/app/services/gps_import.py`
- Create: `backend/migrations/versions/0051_segment_source_gps.py`
- Modify: `backend/app/services/uber_import.py` (kind `analytics`, `ParsedPing`, `ParsedExport.pings`, `MAX_MEMBER_BYTES`, `KNOWN_FILES` texts, `ParsedSegment.h3_r8/zone_key`, `import_export` calls `gps_import.import_pings` and adds `"gps"` to the summary)
- Modify: `backend/app/models/demand.py` (`SegmentSource.GPS = "gps"`; replace the "Only the 2022 export format carries pickup coordinates" comment with "Filled by the GPS import (Task 15) or the 2022 export format; null otherwise.")
- Modify: `backend/app/config.py` and `docker-compose.yml` (`DEMAND_HOME_LAT: float | None = None`, `DEMAND_HOME_LNG: float | None = None`, `DEMAND_HOME_RADIUS_M: int = 300`, blank → None like the DEN lot validator; compose lines next to `DEN_LOT_*`)
- Modify: `backend/app/services/shift_log.py` (`in_home(lat, lng)` beside `in_den_lot`; a new `open` segment gets `zone_key = "den_lot"` when in the lot, else `"home"` when within the home radius, else `None`)
- Test: `backend/tests/test_gps_import.py` (new); one test added to `backend/tests/test_uber_import.py`; one test added to `backend/tests/test_shift_log.py`

**Interfaces:**
- Consumes: `uber_import.ParsedTrip` (`dedup_key, product, request_at, begin_at, dropoff_at, status`), `uber_import._cell`, `uber_import._round5`, `uber_import._upsert`, `demand_places.load_geocoded/ZONES/METRO_BBOX`, settings `DEN_LOT_*`/`DEMAND_HOME_*`, models `DriverStateSegment`, `UberTrip`, `SegmentSource`, `EarnerState`.
- Produces:
  - `uber_import.ParsedPing` — `@dataclass(slots=True)`: `at: datetime` (UTC), `lat: float`, `lng: float`, `online: bool`. `ParsedExport.pings: list[ParsedPing]`. `ParsedSegment` gains `h3_r8: str | None = None` and `zone_key: str | None = None` (existing callers unaffected; `import_export` writes them when present, else computes `h3_r8` from `begin_*` as today).
  - `uber_import.MAX_MEMBER_BYTES = 150 * 1024 * 1024`; a larger `analytics` member is skipped and listed in `files_missing` with consequence "driver_app_analytics.csv is larger than 150 MB; not read." (kind `analytics_too_large`).
  - `uber_import.KNOWN_FILES["online_offline"]` = "Driver Online Offline.csv not present (the US export never ships it): waiting locations come from the 30-day GPS file (driver_app_analytics) and your offer taps; request a new export monthly." and new `KNOWN_FILES["analytics"]` = "driver_app_analytics.csv not present: no waiting locations from this export; only your taps place you. Request a new export monthly."; `_KIND_PATTERNS` gains `analytics` ← filename contains `driver_app_analytics`.
  - `gps_import` constants: `DWELL_S = 60`, `GAP_S = 600`, `MATCH_S = 120`, `CANCEL_S = 60`, `TOP_WAITS = 10`, `LABEL_KM = 2.0`.
  - `gps_import.coverage(pings) -> tuple[datetime, datetime] | None` — `(min at, max at)`.
  - `gps_import.segment_pings(pings, trips, *, home: tuple[float, float] | None, home_radius_m: int) -> list[ParsedSegment]` — pure; the rules of Addendum A "Segmentation"; states `open`/`enroute`/`ontrip` only; `dedup_key = sha256("gps|state|begin_at.isoformat()|end_at.isoformat()|h3_r8 or ''")`.
  - `gps_import.locate_trips(pings, trips) -> dict[str, tuple[float, float]]` — `dedup_key → (lat, lng)` of the ping nearest to `begin_at` within `MATCH_S`; pure.
  - `gps_import.request_cells(pings, trips) -> list[str]` — one H3 cell per **premium** (`black`, `black_suv`) trip requested while not busy (the same non-queued rule as `enroute`), from the ping nearest to `request_at` within `MATCH_S`; pure.
  - `gps_import.top_waits(open_segments, premium_cells, *, places: dict[str, tuple[float, float]]) -> list[dict]` — pure; items exactly `{"h3_r8", "hours", "premium_requests", "per_hour", "place", "distance_km", "zone_key", "zone_name", "outside"}` per Addendum A; `hours` rounded to 1 decimal, `per_hour` = `premium_requests` ÷ unrounded hours, rounded to 2 decimals; `home` segments excluded by the caller; sorted by minutes desc, `TOP_WAITS` items.
  - `async def gps_import.import_pings(db, *, tenant_id: int, pings: list[ParsedPing], trips: list[ParsedTrip]) -> dict | None` — `None` when `pings` is empty; else does, in this order: coverage → `segment_pings` → `DELETE` tenant `gps` segments with `begin_at >= start` → `UPDATE` tenant `gps` segments with `begin_at < start AND end_at > start` to `end_at = start` → insert segments (`_upsert`, `source=SegmentSource.GPS`) → `UPDATE uber_trips SET begin_lat, begin_lng WHERE tenant_id AND dedup_key AND begin_lat IS NULL` for `locate_trips` → returns `{"start", "end" (isoformat), "days" (int, ceil), "pings", "skipped_rows": 0 placeholder replaced by the caller, "segments": {"open", "enroute", "ontrip"}, "trips_located", "home_hours" (1 decimal), "top_waits"}`. No commit inside; `import_export` commits as today.
  - `import_export` summary gains `"gps": <dict | None>`; `skipped_rows` keeps counting analytics rows that failed to parse.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gps_import.py`. Rules: the analytics header is the real one, verbatim (18 columns); rows are built by a helper that fills the 14 unread columns with constants and the 4 read columns from arguments, in the real formats (`2026-09-01 13:00:00.000`, `true`/`false`, 5-decimal coordinates); trips rows are built from `TRIPS_2025_HEADER`/`TRIPS_2025_ROW` of `test_uber_import.py` via `csv` (parse the row into a dict, override `product_type_name`, `request_timestamp_utc`, `begintrip_timestamp_utc`, `dropoff_timestamp_utc`, `status`, write back with `csv.writer`). Set `DEMAND_HOME_LAT="39.60000"`, `DEMAND_HOME_LNG="-104.80000"` (a synthetic point — never the owner's) and `DEN_LOT_LAT/LNG` as `test_shift_log.py` does, before importing `app`.

```python
ANALYTICS_HEADER = (
    "Analytics Event Name,City,Cellular Carrier,Carrier MCC,Carrier MNC,IP Address,"
    "Device Language,Device Model,Device OS,Device OS Version,Is Driver Online?,"
    "Driver Status,Application Version,Event Time (UTC),Latitude,Longitude,Speed (GPS),"
    "Analytics Event Type"
)

def _ping(t: datetime, lat: float, lng: float, online: bool = True) -> str:
    return (
        f"driver_app,denver,Test Carrier,311,480,10.0.0.1,en,sm-test,android,16,"
        f"{'true' if online else 'false'},,4.593.10000,{t:%Y-%m-%d %H:%M:%S}.000,"
        f"{lat:.5f},{lng:.5f},0.0,custom"
    )
```

Fixture day 2026-09-01 (UTC), pings every 30 s unless stated; cells: A = (39.71700, -104.95300), B = a point ~700 m east of A in a different res-8 cell (assert `h3.latlng_to_cell` differs), C = (39.73500, -104.95300), D = (39.74710, -104.99480), HOME = (39.60000, -104.80000):

- 13:00:00–13:39:30 online at A, except 13:30:30 at B (one ping).
- 13:40:00–14:00:00 online at C; then nothing until 14:20:00; 14:20:00–14:29:30 online at C.
- Trip 1 (`UberBLACK`, completed): request 14:30:00, begin 14:40:00, dropoff 15:00:00. Pings continue every 30 s: at C until 14:39:30, at D from 14:40:00.
- Trip 2 (`UberSUV`, completed, queued): request 14:50:00, begin 15:05:00, dropoff 15:20:00; pings at D throughout.
- 15:20:30–15:45:00 online at D.
- Trip 3 (`UberSUV`, `requester_canceled`): request 15:30:00, no begin, no dropoff.
- 16:00:00–16:10:00 pings at D with `online=false`.
- 17:00:00–17:30:00 online at HOME.
- One `uberX` completed trip on 2026-08-20 (outside coverage) to prove trips outside the window are ignored.

Tests (each asserts exact values):

1. `test_parse_zip_reads_analytics_member`: `parse_zip` with the trips + analytics files → `files_found` includes the analytics name, `len(p.pings)` equals the rows written, first ping `at` is tz-aware UTC with the millisecond kept, `online` False for the 16:00 burst; a row with a broken timestamp is counted in `skipped_rows`.
2. `test_segments_exact`: `segment_pings(p.pings, p.trips, home=(39.6, -104.8), home_radius_m=300)` returns, sorted by `begin_at`, exactly: open A 13:00:00–13:39:30 (`h3_r8` = cell of A, the B blip absorbed); open C 13:40:00–14:00:00; open C 14:20:00–14:29:30; enroute 14:30:00–14:40:00 with `h3_r8` = cell of C; ontrip 14:40:00–15:00:00; ontrip 15:05:00–15:20:00 and **no** enroute for trip 2; open D 15:20:30–15:29:30; enroute 15:30:00–15:31:00 with `h3_r8` = cell of D (cancelled trip); open D 15:31:30–15:45:00; open HOME 17:00:00–17:30:00 with `zone_key == "home"`; nothing from the offline burst; `dedup_key`s all distinct and stable across two calls.
3. `test_locate_and_request_cells`: `locate_trips` → trip 1 at D, trip 2 at D, no entry for trip 3 or the August trip; `request_cells` → `[cell(C), cell(D)]` (trip 1 while open at C, trip 3 cancelled at D; trip 2 queued is absent).
4. `test_top_waits_labels`: with `places={"Clayton Hotel & Members Club": (39.7203, -104.9565)}` and the segments above (home excluded by the caller): first item is cell A (`hours` 0.7 — 39.5 min rounded, `premium_requests` 0), C has `premium_requests` 1 and `per_hour` == 2.03 (1 request ÷ 29.5 unrounded minutes, rounded to 2 decimals — `per_hour` is always computed from unrounded minutes); A's `place` is the Clayton entry with `distance_km` < 2; a cell built from (39.19, -106.82) is `outside == True` with `place is None`; the HOME cell is absent.
5. `test_import_pings_replace_window_and_backfill` (DB, same env/bootstrap as `test_demand_api.py`): import the fixture ZIP through `POST /demand/import` → summary `gps.pings`, `gps.segments == {"open": 6, "enroute": 2, "ontrip": 2}`, `gps.trips_located == 2`, `gps.home_hours == 0.5`, `gps.top_waits[0]["h3_r8"]` = cell of A, and `uber_trips.begin_lat/lng` of trip 1 equal D rounded to 5 decimals. Import the same ZIP again → identical `driver_state_segments` rows (same count, same set of `dedup_key`). Then import a second ZIP whose pings start at 15:35:00 (overlapping) → the segment open D 15:31:30–15:45:00 is truncated to end 15:35:00, every gps segment with `begin_at ≥ 15:35:00` comes from the new file only, and the final rows, sorted by `begin_at`, are exactly: open A 13:00:00–13:39:30; open C 13:40:00–14:00:00; open C 14:20:00–14:29:30; enroute 14:30:00–14:40:00; ontrip 14:40:00–15:00:00; ontrip 15:05:00–15:20:00; open D 15:20:30–15:29:30; enroute 15:30:00–15:31:00; open D 15:31:30–**15:35:00** (truncated); open D 15:35:00–15:45:00 (new file); open HOME 17:00:00–17:30:00 (deleted and re-inserted, same `dedup_key`) — 11 rows, none duplicated.
6. `test_analytics_privacy_and_size_cap`: the summary JSON and every stored row contain no `10.0.0.1`, no `sm-test`; monkeypatch `MAX_MEMBER_BYTES = 10` → analytics member skipped, `files_missing` carries kind `analytics_too_large`, `gps is None`, trips still imported.

Add to `test_uber_import.py`: `test_missing_analytics_is_reported_with_consequence` — a ZIP with trips only lists kind `analytics` with the exact consequence text above, and the `online_offline` consequence is the new text.

Add to `test_shift_log.py`: `test_home_tag` — `online` at the synthetic home point → `zone_key == "home"`; `online` 1 km away → `None`; `here` in the DEN lot → `"den_lot"`.

Run: `cd backend && .venv/bin/pytest -q tests/test_gps_import.py tests/test_uber_import.py tests/test_shift_log.py` → the new tests fail on import/attribute errors.

- [ ] **Step 2: Migration 0051**

`backend/migrations/versions/0051_segment_source_gps.py`: `revision = "0051_segment_source_gps"`, `down_revision = "0050_demand_phase1"`; `upgrade()` runs `op.execute("ALTER TYPE segment_source ADD VALUE IF NOT EXISTS 'gps'")` and nothing else (no row may use the value in the same transaction); `downgrade()` is a documented no-op (Postgres cannot drop an enum value). `alembic upgrade head` on the local stack, then `alembic revision --autogenerate -m probe` must report no changes (delete the probe file).

- [ ] **Step 3: Settings and compose**

`config.py`: the three `DEMAND_HOME_*` settings next to `DEN_LOT_*`, covered by the same blank-to-None validator (add the two names to its decorator). `docker-compose.yml`: `DEMAND_HOME_LAT: ${DEMAND_HOME_LAT:-}`, `DEMAND_HOME_LNG: ${DEMAND_HOME_LNG:-}`, `DEMAND_HOME_RADIUS_M: ${DEMAND_HOME_RADIUS_M:-300}` after the `DEN_LOT_RADIUS_M` line.

- [ ] **Step 4: Models and parser**

`SegmentSource.GPS = "gps"`. `ParsedPing`, `ParsedExport.pings`, `ParsedSegment.h3_r8/zone_key`, the `analytics` kind in `_KIND_PATTERNS`/`KNOWN_FILES`, `MAX_MEMBER_BYTES` checked against `info.file_size` before `z.read` for the analytics member. The analytics row parser reads only the four columns by header name; `_parse_ts(value, "UTC")` already accepts the millisecond form (verify; extend the format list if not). Skip rows with empty/invalid coordinates or timestamp (count them).

- [ ] **Step 5: `gps_import.py`**

Module docstring: why the trips file is the authority on state and why home is excluded. Reference loop for `open` segments (the only non-obvious piece; keep it, adapt names):

```python
def _open_runs(labelled):
    """labelled: (at, lat, lng, is_open) sorted by at. Yields (cell, begin, end, blat, blng, elat, elng)."""
    cur = None          # current open segment
    pend = None         # (cell, first ping of the candidate cell, ping before it)
    prev = None
    for at, lat, lng, is_open in labelled:
        if not is_open:
            if cur: yield _close(cur)
            cur = pend = None; prev = None
            continue
        cell = h3.latlng_to_cell(lat, lng, 8)
        if cur is None or (at - cur.end).total_seconds() > GAP_S:
            if cur: yield _close(cur)
            cur = _Seg(cell, at, lat, lng); pend = None
        elif cell == cur.cell:
            cur.extend(at, lat, lng); pend = None
        else:
            if pend is None or pend[0] != cell:
                pend = (cell, (at, lat, lng), prev)
            if (at - pend[1][0]).total_seconds() >= DWELL_S:
                cur.end, cur.elat, cur.elng = pend[2]          # last ping before the candidate
                yield _close(cur)
                cur = _Seg(cell, *pend[1]); cur.extend(at, lat, lng); pend = None
            else:
                cur.extend(at, lat, lng)                        # absorbed unless it dwells
        prev = (at, lat, lng)
    if cur: yield _close(cur)
```

Busy intervals from the trips (Addendum A), `enroute`/`ontrip` rows from the trips with nearest-ping positions (`bisect` over the sorted ping times), home tag, `top_waits` with the label rules (`places` = `demand_places.load_geocoded()` plus `"DEN Commercial Holding Lot"` when `DEN_LOT_LAT/LNG` are set; zones from `demand_places.ZONES` with `radius_mi`; `METRO_BBOX`), `import_pings` with the replace-window statements. `_haversine_m` is duplicated in three services already (ledger deferred minor): import it from `shift_log` rather than adding a fourth copy.

- [ ] **Step 6: `shift_log` home tag**

`in_home()` mirrors `in_den_lot()` with `DEMAND_HOME_*`; the `zone_key` decision for a new `open` segment: lot → `"den_lot"`, else home → `"home"`, else `None`.

- [ ] **Step 7: Verify**

`cd backend && .venv/bin/ruff check . && .venv/bin/pytest -q tests/test_gps_import.py tests/test_uber_import.py tests/test_shift_log.py tests/test_demand_api.py` (DB tests need `DATABASE_URL` with host `127.0.0.1:5435` and `REDIS_URL=redis://127.0.0.1:6382/0` exported — the root `.env` points at the docker host `db`). Then the acceptance run on the owner's real export, `/Users/enderj/Downloads/Uber Data Request 5680944C.zip`, with the real `DEMAND_HOME_*`/`DEN_LOT_*` values exported from the root `.env` (never copy them into any file under the repo or into the report): call `parse_zip` + `segment_pings` + `locate_trips` + `top_waits` directly and check `pings == 218344`, coverage 2026-08-17 → 2026-09-15, open segments between 470 and 500 with total open hours between 140 and 150, `trips_located == 50`, home hours between 20 and 22, `top_waits[0]` is the DEN lot (`place` starts with "DEN", hours 50–55, `premium_requests == 10`). Write the numbers in the report.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/gps_import.py backend/migrations/versions/0051_segment_source_gps.py backend/app/services/uber_import.py backend/app/models/demand.py backend/app/config.py docker-compose.yml backend/app/services/shift_log.py backend/tests/test_gps_import.py backend/tests/test_uber_import.py backend/tests/test_shift_log.py
git commit -m "feat(demand): import the 30-day GPS file — waits, offers, pickups, home excluded" -m "<body per the repo's CLAUDE.md trailer>"
```

---


### Task 9: Week recompute, scheduler job, `/demand/week` — `demand.py`

**Files:**
- Create: `backend/app/services/demand.py`
- Modify: `backend/app/services/scheduler.py` (one job + registration)
- Modify: `backend/app/api/v1/demand.py` (add `/demand/week`)
- Test: `backend/tests/test_demand_jobs.py`

**Interfaces:**
- Consumes: `demand_model` (Task 3), models, `flights_baseline.load_baseline/multipliers` (Task 8), `demand_places.ZONES` (Task 7), `shift_log.DENVER`. **Amendment (Task 15 / Addendum A):** also `SegmentSource` and `DemandImport` (GPS coverage windows); the four counting rules of Addendum A bind `recompute_week` — they are written into the code and tests below.
- Produces:
  - `async def recompute_week(db, *, tenant_id: int, now: datetime | None = None) -> dict` → `{"zones": int, "rows": int, "computed_at": iso}`; replaces the tenant's `week_scores`.
  - `async def week_payload(db, *, tenant_id: int, zone: str | None) -> dict | None` → `None` for an unknown zone; otherwise `{"zone", "zone_name", "zones": [{"key","name"}], "computed_at", "grid": [[cell×24]×7], "top_blocks": [...], "private_rides": [...], "own_minutes_total": float}` where cell = `{"mean","lo","hi","p15","own_share","reasons"}`; computes on the fly when the tenant has no scores yet.
  - `async def tenants_with_data(db) -> list[int]`
  - `def base_profile(*, windows: list[DispatchWindow], trips: list[UberTrip], live_rate: float | None) -> list[float]` — 168 offers/min values (pure).
  - `def event_multipliers(events: list[dict], zone: dict, now: datetime) -> tuple[list[float], list[list[str]]]` — 168 multipliers + reason names per hour-of-week for the coming 7 days (pure; event = `{"title","lat","lng","starts_at"}`).
  - Scheduler job `_demand_week_job` (hourly, id `demand_week`), gated by `DEMAND_ENABLED`.
  - `GET /demand/week?zone=` → payload; 404 `unknown_zone`; header `ETag: "<sha of computed_at>"`, `Cache-Control: private, max-age=300, stale-while-revalidate=900`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_demand_jobs.py`:

```python
"""Week recompute end-to-end: seeded segments/offers → week_scores → /demand/week."""
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

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

from app.db.base import get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DispatchWindow, HexPrior, UberProduct, UberTrip  # noqa: E402
from app.services import demand  # noqa: E402

client = TestClient(app)
CHERRY_CREEK = (39.7170, -104.9530)


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _tenant_id(c: TestClient) -> int:
    return c.get("/api/v1/auth/me").json()["tenant_id"]


def _seed_priors():
    import h3

    async def _run():
        async with get_session_factory()() as db:
            centre = h3.latlng_to_cell(*CHERRY_CREEK, 8)
            for cell in h3.grid_disk(centre, 2):
                await db.merge(HexPrior(h3_r8=cell, affluence=0.8, hotels=2, generators=3,
                                        den_distance_mi=20.0, zone_key="cherry_creek"))
            await db.commit()

    asyncio.run(_run())


def _log(c: TestClient, kind: str, at: datetime, **extra):
    body = {"client_event_id": str(uuid.uuid4()), "kind": kind, "at": at.isoformat(),
            "lat": CHERRY_CREEK[0], "lng": CHERRY_CREEK[1], **extra}
    r = c.post("/api/v1/demand/log", json=body)
    assert r.status_code in (200, 201), r.text


def test_base_profile_from_trips_is_normalized_to_mean_one():
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # Tue 06:00 Denver
    trips = [UberTrip(product=UberProduct.BLACK, request_at=t0 + timedelta(minutes=i))
             for i in range(10)]
    prof = demand.base_profile(windows=[], trips=trips, live_rate=None)
    assert len(prof) == 168
    assert abs(sum(prof) / 168 - demand.dm.DEFAULT_BASE_RATE) < 1e-9
    assert prof[24 + 6] > prof[24 + 12]


def test_base_profile_prefers_dispatch_windows():
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    w = DispatchWindow(window_start=t0, window_end=t0 + timedelta(hours=1),
                       minutes_online=60, dispatches=6)
    prof = demand.base_profile(windows=[w], trips=[], live_rate=None)
    assert prof[24 + 6] == max(prof)


def test_event_multipliers_lift_hours_around_the_event():
    now = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)  # Mon 00:00 Denver
    ev = {"title": "Concert", "lat": 39.7487, "lng": -105.0077,  # Ball Arena
          "starts_at": datetime(2026, 9, 15, 1, 0, tzinfo=UTC)}  # Mon 19:00 Denver
    zone = {"key": "downtown", "lat": 39.7392, "lng": -104.9903, "radius_mi": 1.5}
    mult, reasons = demand.event_multipliers([ev], zone, now)
    assert mult[17] > 1.0 and mult[19] > 1.0 and mult[22] > 1.0 and mult[12] == 1.0
    assert "Concert" in reasons[19]
    far = {"key": "boulder", "lat": 40.0150, "lng": -105.2705, "radius_mi": 2.5}
    assert demand.event_multipliers([ev], far, now)[0] == [1.0] * 168


def test_recompute_and_week_endpoint():
    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    # Two Tuesday-morning waits in Cherry Creek with one Black offer each.
    for day in (8, 15):
        t = datetime(2026, 9, day, 13, 0, tzinfo=UTC)  # Tue 07:00 Denver
        _log(c, "online", t)
        _log(c, "offer", t + timedelta(minutes=20), product="black", accepted=True)
        _log(c, "offline", t + timedelta(minutes=50))

    async def _run():
        async with get_session_factory()() as db:
            return await demand.recompute_week(db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC))

    res = asyncio.run(_run())
    assert res["rows"] >= 168 and res["zones"] >= 1

    assert client.get("/api/v1/demand/week").status_code == 401
    r = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zone"] == "cherry_creek" and len(body["grid"]) == 7 and len(body["grid"][0]) == 24
    tue7 = body["grid"][1][7]
    assert tue7["own_share"] > 0 and 0 < tue7["p15"] < 1
    assert tue7["mean"] > body["grid"][1][3]["mean"]  # data at 07 lifts it above 03
    assert "top_blocks" in body and "private_rides" in body
    etag1 = r.headers.get("etag")
    assert etag1
    asyncio.run(_run())
    r2 = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"})
    assert r2.headers.get("etag") != etag1
    assert c.get("/api/v1/demand/week", params={"zone": "narnia"}).status_code == 404


def test_gps_coverage_and_home_rules():
    """Addendum A: inside a GPS window live waits are ignored; home never counts."""
    import h3

    from app.models import DemandImport, DriverStateSegment, EarnerState, SegmentSource

    _seed_priors()
    c = _owner()
    tid = _tenant_id(c)
    cell = h3.latlng_to_cell(*CHERRY_CREEK, 8)
    t = datetime(2026, 9, 15, 13, 0, tzinfo=UTC)  # Tue 07:00 Denver
    # A live wait inside the covered window: must not count.
    _log(c, "online", t)
    _log(c, "offline", t + timedelta(minutes=50))

    async def _seed_and_run():
        async with get_session_factory()() as db:
            db.add(DemandImport(tenant_id=tid, summary={"gps": {
                "start": "2026-09-01T00:00:00+00:00", "end": "2026-09-30T00:00:00+00:00"}}))
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="gps-open", state=EarnerState.OPEN, begin_at=t,
                end_at=t + timedelta(minutes=50), begin_lat=CHERRY_CREEK[0],
                begin_lng=CHERRY_CREEK[1], h3_r8=cell, source=SegmentSource.GPS))
            db.add(DriverStateSegment(
                tenant_id=tid, dedup_key="gps-home", state=EarnerState.OPEN,
                begin_at=t + timedelta(hours=2), end_at=t + timedelta(hours=2, minutes=50),
                begin_lat=CHERRY_CREEK[0], begin_lng=CHERRY_CREEK[1], h3_r8=cell,
                zone_key="home", source=SegmentSource.GPS))
            await db.commit()
            return await demand.recompute_week(
                db, tenant_id=tid, now=datetime(2026, 9, 16, tzinfo=UTC)
            )

    asyncio.run(_seed_and_run())
    body = c.get("/api/v1/demand/week", params={"zone": "cherry_creek"}).json()
    assert body["grid"][1][7]["reasons"]["own_minutes"] == 50  # the GPS wait, not 100
    assert body["grid"][1][9]["reasons"]["own_minutes"] == 0  # home excluded



def test_recompute_error_does_not_kill_the_job(monkeypatch):
    from app.services import scheduler

    async def boom(*a, **k):
        raise RuntimeError("compute failed")

    monkeypatch.setattr(demand, "recompute_week", boom)
    asyncio.run(scheduler._demand_week_job())  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_demand_jobs.py -v`
Expected: FAIL — `ImportError: cannot import name 'demand'`.

- [ ] **Step 3: Implement `demand.py`**

Create `backend/app/services/demand.py`:

```python
"""'Where to wait' orchestration: turn the owner's trips, waits and offers plus the
static priors into the 7×24 planner per zone, on a schedule, cached in Redis.

Data flow per tenant:
  base_profile   — offers/min by hour-of-week (dispatch windows → trips → default)
  priors         — per-zone average of cell multipliers (affluence, hotels, generators)
  covariates     — DEN flight banks (relative), events near the zone, US/CO holidays
  own data       — `open` minutes (exposure) and Black/SUV offers per zone × hour
  posterior      — demand_model.posterior per (zone, hour), hours pooled ±1
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    DemandImport,
    DispatchWindow,
    DriverStateSegment,
    EarnerState,
    EventSuggestion,
    HexPrior,
    OfferEvent,
    Ride,
    RideStatus,
    SegmentSource,
    UberProduct,
    UberTrip,
    WeekScore,
)
from app.services import demand_model as dm
from app.services import demand_places as dpl
from app.services import flights_baseline as fb

logger = logging.getLogger("blackvolt.demand")

_PREMIUM = {UberProduct.BLACK, UberProduct.BLACK_SUV}
_LIVE_RATE_MIN_MINUTES = 600.0   # below this the global rate stays the default
_EVENT_RADIUS_MI = 3.0
_EVENT_LIFT = 1.5


def _miles(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


# ── Pure pieces ─────────────────────────────────────────────────────────────────
def _normalize(profile: list[float], level: float) -> list[float]:
    mean = sum(profile) / len(profile)
    if mean <= 0:
        return [level] * len(profile)
    return [level * v / mean for v in profile]


def base_profile(
    *, windows: list[DispatchWindow], trips: list[UberTrip], live_rate: float | None
) -> list[float]:
    """168 offers/min. Shape from dispatch windows (real offer counts) when present,
    else from the trips' request-time histogram; level = live observed rate or default."""
    level = live_rate if live_rate is not None else dm.DEFAULT_BASE_RATE
    shape = [0.0] * dm.HOURS_PER_WEEK
    if windows:
        minutes = [0.0] * dm.HOURS_PER_WEEK
        for w in windows:
            how = dm.hour_of_week(w.window_start)
            shape[how] += float(w.dispatches or 0)
            minutes[how] += float(w.minutes_online or 0)
        shape = [s / m if m > 0 else 0.0 for s, m in zip(shape, minutes, strict=True)]
    elif trips:
        for t in trips:
            at = t.request_at or t.begin_at
            if at is not None:
                shape[dm.hour_of_week(at)] += 1.0
    else:
        return [level] * dm.HOURS_PER_WEEK
    pooled = [o for o, _ in dm.pool_hours([(v, 0.0) for v in shape])]
    return _normalize(pooled, level)


def event_multipliers(
    events: list[dict], zone: dict, now: datetime
) -> tuple[list[float], list[list[str]]]:
    """Lift the hours people travel to/from an event near the zone: 2h before doors
    to 1h after (arrivals) and 2h–4h after (departures)."""
    mult = [1.0] * dm.HOURS_PER_WEEK
    reasons: list[list[str]] = [[] for _ in range(dm.HOURS_PER_WEEK)]
    horizon = now + timedelta(days=7)
    for ev in events:
        if ev.get("lat") is None or ev.get("lng") is None:
            continue
        if _miles(ev["lat"], ev["lng"], zone["lat"], zone["lng"]) > _EVENT_RADIUS_MI:
            continue
        start = ev["starts_at"]
        if not (now <= start <= horizon):
            continue
        for off_h in (-2, -1, 0, 1, 2, 3, 4):
            how = dm.hour_of_week(start + timedelta(hours=off_h))
            mult[how] = max(mult[how], _EVENT_LIFT)
            if ev["title"] not in reasons[how]:
                reasons[how].append(ev["title"])
    return mult, reasons


def _segment_minutes_by_hour(segs: list[DriverStateSegment]) -> list[float]:
    """Exposure: `open` minutes per hour-of-week, walking each segment in 10-min steps."""
    out = [0.0] * dm.HOURS_PER_WEEK
    for s in segs:
        end = s.end_at or s.last_ping_at
        if end is None or end <= s.begin_at:
            continue
        t = s.begin_at
        while t < end:
            step = min(timedelta(minutes=10), end - t)
            out[dm.hour_of_week(t)] += step.total_seconds() / 60.0
            t += step
    return out


# ── DB helpers ──────────────────────────────────────────────────────────────────
async def tenants_with_data(db: AsyncSession) -> list[int]:
    ids: set[int] = set()
    for model in (DriverStateSegment, UberTrip, OfferEvent):
        rows = (await db.execute(select(model.tenant_id).distinct())).scalars().all()
        ids.update(int(r) for r in rows)
    return sorted(ids)


async def _zone_cells(db: AsyncSession) -> dict[str, list[HexPrior]]:
    rows = (await db.execute(select(HexPrior).where(HexPrior.zone_key.is_not(None)))).scalars().all()
    out: dict[str, list[HexPrior]] = {}
    for r in rows:
        out.setdefault(r.zone_key, []).append(r)
    return out


async def _upcoming_events(db: AsyncSession, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(EventSuggestion).where(
                EventSuggestion.starts_at >= now,
                EventSuggestion.starts_at <= now + timedelta(days=7),
                EventSuggestion.venue_lat.is_not(None),
            )
        )
    ).scalars().all()
    return [
        {"title": r.title, "lat": r.venue_lat, "lng": r.venue_lng, "starts_at": r.starts_at}
        for r in rows
    ]


def _holiday_dows(now: datetime) -> dict[int, str]:
    """dow → holiday name for the next 7 days (US + Colorado)."""
    try:
        import holidays

        cal = holidays.country_holidays("US", subdiv="CO", years={now.year, now.year + 1})
    except Exception as e:  # never block the recompute on the calendar package
        logger.warning("holidays unavailable: %s", e)
        return {}
    out: dict[int, str] = {}
    for i in range(7):
        d = (now.astimezone(dm.DENVER) + timedelta(days=i)).date()
        if d in cal:
            out[d.weekday()] = str(cal.get(d))
    return out


async def _gps_coverage(db: AsyncSession, tenant_id: int) -> list[tuple[datetime, datetime]]:
    """[start, end] of every imported GPS file: inside them the GPS owns the exposure."""
    rows = (
        await db.execute(
            select(DemandImport.summary).where(DemandImport.tenant_id == tenant_id)
        )
    ).scalars().all()
    out: list[tuple[datetime, datetime]] = []
    for summary in rows:
        gps = (summary or {}).get("gps") or {}
        if gps.get("start") and gps.get("end"):
            out.append((datetime.fromisoformat(gps["start"]), datetime.fromisoformat(gps["end"])))
    return out
# ── Recompute ───────────────────────────────────────────────────────────────────
async def recompute_week(
    db: AsyncSession, *, tenant_id: int, now: datetime | None = None
) -> dict:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    since = now - timedelta(days=90)

    windows = (
        await db.execute(select(DispatchWindow).where(DispatchWindow.tenant_id == tenant_id))
    ).scalars().all()
    trips = (
        await db.execute(
            select(UberTrip).where(
                UberTrip.tenant_id == tenant_id, UberTrip.product.in_(_PREMIUM)
            )
        )
    ).scalars().all()
    segs = (
        await db.execute(
            select(DriverStateSegment).where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.state == EarnerState.OPEN,
                DriverStateSegment.begin_at >= since,
            )
        )
    ).scalars().all()
    # Addendum A: inside a GPS coverage window the GPS owns the exposure; home never counts.
    coverage = await _gps_coverage(db, tenant_id)

    def _covered(at: datetime) -> bool:
        return any(a <= at <= b for a, b in coverage)

    segs = [
        s
        for s in segs
        if s.zone_key != "home"
        and not (s.source == SegmentSource.LIVE and _covered(s.begin_at))
    ]
    offers = (
        await db.execute(
            select(OfferEvent).where(
                OfferEvent.tenant_id == tenant_id,
                OfferEvent.product.in_(_PREMIUM),
                OfferEvent.at >= since,
            )
        )
    ).scalars().all()
    # Export `enroute` segments = accepted offers with a location; the product comes
    # from the trip whose request time matches within 3 minutes.
    enroute = (
        await db.execute(
            select(DriverStateSegment).where(
                DriverStateSegment.tenant_id == tenant_id,
                DriverStateSegment.state == EarnerState.ENROUTE,
                DriverStateSegment.begin_at >= since,
                DriverStateSegment.h3_r8.is_not(None),
            )
        )
    ).scalars().all()
    premium_requests = sorted(t.request_at for t in trips if t.request_at)

    def _is_premium_at(at: datetime) -> bool:
        lo = at - timedelta(minutes=3)
        hi = at + timedelta(minutes=3)
        return any(lo <= r <= hi for r in premium_requests)

    accepted_live = [o.at for o in offers if o.accepted]

    def _live_accepted_near(at: datetime) -> bool:
        return any(abs((a - at).total_seconds()) <= 180 for a in accepted_live)

    enroute = [s for s in enroute if not _live_accepted_near(s.begin_at)]

    total_open_min = sum(_segment_minutes_by_hour(segs))
    live_offers = len(offers) + sum(1 for s in enroute if _is_premium_at(s.begin_at))
    live_rate = (
        live_offers / total_open_min if total_open_min >= _LIVE_RATE_MIN_MINUTES else None
    )
    base = base_profile(windows=list(windows), trips=list(trips), live_rate=live_rate)

    zone_cells = await _zone_cells(db)
    baseline = await fb.load_baseline(db)
    events = await _upcoming_events(db, now)
    holidays_by_dow = _holiday_dows(now)
    denver_now = now.astimezone(dm.DENVER)

    await db.execute(delete(WeekScore).where(WeekScore.tenant_id == tenant_id))
    rows = 0
    for zone in dpl.ZONES:
        cells = zone_cells.get(zone["key"], [])
        if not cells:
            continue
        cell_ids = {c.h3_r8 for c in cells}
        # Static multiplier of the zone = mean over its cells (with base=1).
        static = sum(
            dm.prior_rate(1.0, affluence=c.affluence, hotels=c.hotels, generators=c.generators)
            for c in cells
        ) / len(cells)
        ev_mult, ev_reasons = event_multipliers(events, zone, now)
        zone_segs = [s for s in segs if s.h3_r8 in cell_ids or s.zone_key == zone["key"]]
        exposure = _segment_minutes_by_hour(zone_segs)
        offer_counts = [0.0] * dm.HOURS_PER_WEEK
        for o in offers:
            if o.h3_r8 in cell_ids:
                offer_counts[dm.hour_of_week(o.at)] += 1
        for s in enroute:
            if s.h3_r8 in cell_ids and _is_premium_at(s.begin_at):
                offer_counts[dm.hour_of_week(s.begin_at)] += 1
        pooled = dm.pool_hours(list(zip(offer_counts, exposure, strict=True)))

        for how in range(dm.HOURS_PER_WEEK):
            dow, hour = divmod(how, 24)
            month = (denver_now + timedelta(days=(dow - denver_now.weekday()) % 7)).month
            flights = fb.multipliers(baseline, month=month, dow=dow)[hour]
            flight_mult = flights if zone["key"] == "den" else 1.0 + 0.5 * (flights - 1.0)
            prior = (
                base[how]
                * static
                * dm.clamp(flight_mult, *dm.FLIGHT_RANGE)
                * dm.clamp(ev_mult[how], *dm.EVENT_RANGE)
            )
            y, e = pooled[how]
            est = dm.posterior(prior, y, e)
            reasons = {
                "flights": round(flight_mult, 2),
                "events": ev_reasons[how],
                "holiday": holidays_by_dow.get(dow),
                "own_minutes": round(e, 1),
                "own_offers": round(y, 2),
            }
            db.add(
                WeekScore(
                    tenant_id=tenant_id, computed_at=now, zone_key=zone["key"], dow=dow,
                    hour=hour, mean=est.mean, lo=est.lo, hi=est.hi, own_share=est.own_share,
                    reasons=reasons,
                )
            )
            rows += 1
    await db.commit()
    await _cache_clear(tenant_id)
    return {"zones": rows // dm.HOURS_PER_WEEK, "rows": rows, "computed_at": now.isoformat()}


# ── Payload ─────────────────────────────────────────────────────────────────────
async def _private_rides(db: AsyncSession, tenant_id: int, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(Ride).where(
                Ride.tenant_id == tenant_id,
                Ride.scheduled_at >= now,
                Ride.scheduled_at <= now + timedelta(days=7),
                Ride.status.in_([RideStatus.CONFIRMED, RideStatus.ASSIGNED]),
            )
        )
    ).scalars().all()
    return [
        {"id": r.id, "at": r.scheduled_at.isoformat(), "pickup": r.pickup_text}
        for r in rows
    ]


async def week_payload(db: AsyncSession, *, tenant_id: int, zone: str | None) -> dict | None:
    zones = [{"key": z["key"], "name": z["name"]} for z in dpl.ZONES]
    keys = {z["key"] for z in dpl.ZONES}
    if zone is not None and zone not in keys:
        return None
    rows = (
        await db.execute(select(WeekScore).where(WeekScore.tenant_id == tenant_id))
    ).scalars().all()
    if not rows:
        await recompute_week(db, tenant_id=tenant_id)
        rows = (
            await db.execute(select(WeekScore).where(WeekScore.tenant_id == tenant_id))
        ).scalars().all()
    if not rows:
        return {"zone": zone, "zone_name": None, "zones": zones, "computed_at": None,
                "grid": [], "top_blocks": [], "private_rides": [], "own_minutes_total": 0}
    if zone is None:
        # Default: the zone with the most of the owner's own minutes, else the first scored.
        by_zone: dict[str, float] = {}
        for r in rows:
            by_zone[r.zone_key] = by_zone.get(r.zone_key, 0.0) + float(
                (r.reasons or {}).get("own_minutes", 0.0)
            )
        zone = max(by_zone, key=by_zone.get)
    cached = await _cache_get(tenant_id, zone)
    if cached is not None:
        return cached
    zrows = [r for r in rows if r.zone_key == zone]
    if not zrows:
        return None
    grid = [[None] * 24 for _ in range(7)]
    ests: list[dm.Estimate] = [None] * dm.HOURS_PER_WEEK  # type: ignore[list-item]
    for r in zrows:
        est = dm.Estimate(r.mean, r.lo, r.hi, r.own_share,
                          (r.reasons or {}).get("own_offers", 0.0),
                          (r.reasons or {}).get("own_minutes", 0.0))
        ests[r.dow * 24 + r.hour] = est
        grid[r.dow][r.hour] = {
            "mean": r.mean, "lo": r.lo, "hi": r.hi, "p15": dm.p_within(r.mean),
            "own_share": r.own_share, "reasons": r.reasons or {},
        }
    blocks = dm.top_blocks(ests) if all(e is not None for e in ests) else []
    now = datetime.now(UTC)
    payload = {
        "zone": zone,
        "zone_name": next(z["name"] for z in zones if z["key"] == zone),
        "zones": zones,
        "computed_at": zrows[0].computed_at.isoformat(),
        "grid": grid,
        "top_blocks": [
            {"dow": b.dow, "start_hour": b.start_hour, "end_hour": b.end_hour,
             "expected_offers": round(b.expected_offers, 2), "mean": b.mean,
             "reasons": grid[b.dow][b.start_hour]["reasons"]}
            for b in blocks
        ],
        "private_rides": await _private_rides(db, tenant_id, now),
        "own_minutes_total": round(sum(e.exposure_min for e in ests if e), 1),
    }
    await _cache_set(tenant_id, zone, payload)
    return payload


def etag_for(payload: dict) -> str:
    return '"' + hashlib.sha1(
        f"{payload.get('computed_at')}|{payload.get('zone')}".encode()
    ).hexdigest()[:16] + '"'


# ── Redis (best-effort, same pattern as coach.py) ───────────────────────────────
def _key(tenant_id: int, zone: str) -> str:
    return f"demand:week:{tenant_id}:{zone}"


async def _cache_get(tenant_id: int, zone: str) -> dict | None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            raw = await client.get(_key(tenant_id, zone))
        finally:
            await client.aclose()
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning("demand cache get failed: %s", e)
        return None


async def _cache_set(tenant_id: int, zone: str, value: dict) -> None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            await client.set(_key(tenant_id, zone), json.dumps(value), ex=2 * 3600)
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("demand cache set failed: %s", e)


async def _cache_clear(tenant_id: int) -> None:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(get_settings().REDIS_URL)
        try:
            keys = await client.keys(f"demand:week:{tenant_id}:*")
            if keys:
                await client.delete(*keys)
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("demand cache clear failed: %s", e)
```

`dm.prior_rate` (the cell-level function) is not called here on purpose: `static` already averages the cell multipliers over the zone; `prior_rate` is for the Phase 2 per-cell map.

- [ ] **Step 4: Scheduler job and route**

In `backend/app/services/scheduler.py` add, after `_blog_gsc_job`:

```python
async def _demand_week_job() -> None:
    """Hourly: rebuild the 'Where to wait' 7×24 planner for every tenant with data."""
    try:
        from app.db.base import get_session_factory
        from app.services import demand

        async with get_session_factory()() as db:
            for tid in await demand.tenants_with_data(db):
                try:
                    logger.info("demand week %s: %s", tid, await demand.recompute_week(db, tenant_id=tid))
                except Exception as e:
                    logger.warning("demand week job failed for tenant %s: %s", tid, e)
    except Exception as e:  # never let a job crash the scheduler
        logger.warning("demand week job failed: %s", e)
```

and in `start()`, before `sched.start()`:

```python
        if get_settings().DEMAND_ENABLED:
            sched.add_job(
                _demand_week_job, "interval", hours=1, id="demand_week",
                max_instances=1, coalesce=True,
            )
```

In `backend/app/api/v1/demand.py` add `from app.services import demand` and:

```python
@router.get("/demand/week")
async def get_week(
    response: Response,
    zone: str | None = Query(default=None, max_length=40),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    tenant_id = await resolve_tenant_id(db, payload)
    body = await demand.week_payload(db, tenant_id=tenant_id, zone=zone)
    if body is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_zone")
    response.headers["ETag"] = demand.etag_for(body)
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=900"
    return body
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_demand_jobs.py tests/test_demand_api.py tests/test_shift_log.py -v && ruff check .`
Expected: all PASS. If `test_recompute_and_week_endpoint` returns 404 for `cherry_creek`, the seeded `HexPrior` rows did not commit before the recompute (check `_seed_priors` awaits `db.merge` and commits) or `TARGET_ZONES` has no `cherry_creek` key (it does; verify with `grep cherry_creek app/services/uber_research.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/demand.py backend/app/services/scheduler.py backend/app/api/v1/demand.py backend/tests/test_demand_jobs.py
git commit -m "feat(demand): hourly 7×24 planner per zone — priors, flights, events, own data; GET /demand/week"
```

---

### Task 10: Frontend foundation — API client, i18n, nav, route, tabs shell

**Files:**
- Create: `frontend/lib/demand.ts`
- Modify: `frontend/lib/i18n.tsx` (EN block near `"dash.nav.stats"` ~line 637; ES block near ~line 1946)
- Modify: `frontend/components/bv/dash/DriverTabBar.tsx` (`MORE` list + feature gate)
- Modify: `frontend/components/bv/dash/DashShell.tsx` (`NAV` list + feature gate)
- Create: `frontend/components/bv/dash/demand/DemandPage.tsx`
- Create: `frontend/app/dashboard/demand/page.tsx`

**Interfaces:**
- Consumes: `Me.features.demand` (Task 1); API routes from Tasks 5, 6, 9.
- Produces (`lib/demand.ts`): types `LogKind`, `Product`, `LogEvent`, `TodayLog`, `ImportSummary`, `WeekCell`, `WeekPayload`; functions `logEvent(body) → Promise<LogEvent>`, `getToday() → Promise<TodayLog>`, `importZip(file, onProgress?) → Promise<ImportSummary>`, `getImportStatus() → Promise<ImportSummary & {at: string} | {never: true}>`, `getWeek(zone?) → Promise<WeekPayload>`, `newEventId() → string`, `PRODUCTS` const, `DOW_KEYS` const. `DemandPage` renders tabs `log | week | import` (query `?tab=`), each tab component receives no props and fetches on its own. **Amendment (Task 15):** `ImportSummary.gps?: GpsSummary | null` with `GpsSummary = { start: string; end: string; days: number; pings: number; segments: { open: number; enroute: number; ontrip: number }; trips_located: number; home_hours: number; top_waits: { h3_r8: string; hours: number; premium_requests: number; per_hour: number; place: string | null; distance_km: number | null; zone_key: string | null; zone_name: string | null; outside: boolean }[] }`.

- [ ] **Step 1: API client**

Create `frontend/lib/demand.ts`:

```ts
/* Client for the "Where to wait" API (one-tap log, Uber export import, week planner). */
import { ApiError, fmtApiDetail } from "./booking";

export type LogKind = "online" | "here" | "ping" | "offer" | "offline";
export type Product = "black_suv" | "black" | "comfort" | "x" | "xl";
export const PRODUCTS: Product[] = ["black_suv", "black", "comfort", "x", "xl"];
export const DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export interface LogEvent {
  id: number;
  kind: LogKind;
  at: string;
  lat: number | null;
  lng: number | null;
  h3_r8: string | null;
  product: Product | null;
  accepted: boolean | null;
  fare: number | null;
  zone_key: string | null;
  no_position: boolean;
}

export interface TodayLog {
  state: "open" | "enroute" | "offline";
  open_since: string | null;
  events: LogEvent[];
  segments: { state: string; begin_at: string; end_at: string | null; minutes: number; zone_key: string | null }[];
}

export interface ImportSummary {
  files_found: string[];
  files_missing: { kind: string; consequence: string }[];
  skipped_rows: number;
  trips: { inserted: number; skipped: number; date_min: string | null; date_max: string | null; by_product: Record<string, number> };
  segments: { inserted: number; skipped: number };
  windows: { inserted: number; skipped: number };
}

export interface WeekCell {
  mean: number;
  lo: number;
  hi: number;
  p15: number;
  own_share: number;
  reasons: { flights?: number; events?: string[]; holiday?: string | null; own_minutes?: number; own_offers?: number };
}

export interface WeekPayload {
  zone: string | null;
  zone_name: string | null;
  zones: { key: string; name: string }[];
  computed_at: string | null;
  grid: WeekCell[][];
  top_blocks: { dow: number; start_hour: number; end_hour: number; expected_offers: number; mean: number; reasons: WeekCell["reasons"] }[];
  private_rides: { id: number; at: string; pickup: string }[];
  own_minutes_total: number;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`, { credentials: "include", cache: "no-store" });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new ApiError(fmtApiDetail((d as { detail?: unknown }).detail, `${path}:${r.status}`), r.status);
  }
  return r.json();
}

export function newEventId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function logEvent(body: {
  client_event_id: string;
  kind: LogKind;
  lat?: number | null;
  lng?: number | null;
  product?: Product;
  accepted?: boolean;
  fare?: number | null;
}): Promise<LogEvent> {
  return jpost<LogEvent>("/v1/demand/log", body);
}

export function getToday(): Promise<TodayLog> {
  return jget<TodayLog>("/v1/demand/log/today");
}

export function getImportStatus(): Promise<(ImportSummary & { at: string }) | { never: true }> {
  return jget("/v1/demand/import/status");
}

export function getWeek(zone?: string | null): Promise<WeekPayload> {
  const q = zone ? `?zone=${encodeURIComponent(zone)}` : "";
  return jget<WeekPayload>(`/v1/demand/week${q}`);
}

/* XHR so the upload can report progress; fetch cannot. */
export function importZip(file: File, onProgress?: (pct: number) => void): Promise<ImportSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/demand/import");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let body: unknown = {};
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as ImportSummary);
      else
        reject(
          new ApiError(
            fmtApiDetail((body as { detail?: unknown }).detail, `import:${xhr.status}`),
            xhr.status,
          ),
        );
    };
    xhr.onerror = () => reject(new ApiError("import:network", 0));
    const fd = new FormData();
    fd.append("file", file, file.name);
    xhr.send(fd);
  });
}
```

Check that `ApiError` and `fmtApiDetail` are exported from `lib/booking.ts` (they are, lines ~72 and ~90).

- [ ] **Step 2: i18n strings (both dictionaries)**

Add to the `EN` dictionary in `frontend/lib/i18n.tsx`, right after `"dash.nav.stats": "My Stats",`:

```ts
  "dash.nav.demand": "Where to wait",
  "dash.demand.title": "Where to wait",
  "dash.demand.tab.log": "Log",
  "dash.demand.tab.week": "Week",
  "dash.demand.tab.import": "Import",
  "dash.demand.log.online": "Online",
  "dash.demand.log.here": "I'm here",
  "dash.demand.log.offer": "Offer",
  "dash.demand.log.offline": "Offline",
  "dash.demand.log.accepted": "Accepted",
  "dash.demand.log.fare": "Fare (optional)",
  "dash.demand.log.send": "Log offer",
  "dash.demand.log.cancel": "Cancel",
  "dash.demand.log.state.open": "Waiting since",
  "dash.demand.log.state.enroute": "On a ride since",
  "dash.demand.log.state.offline": "Offline",
  "dash.demand.log.today": "Today",
  "dash.demand.log.empty": "No taps yet today. Tap Online when you go on.",
  "dash.demand.log.noPosition": "no position",
  "dash.demand.log.retry": "Retry position",
  "dash.demand.log.saved": "Saved",
  "dash.demand.log.failed": "Could not save, tap again",
  "dash.demand.log.denLot": "DEN lot",
  "dash.demand.log.autoPing": "Auto-logging every minute while this screen is open",
  "dash.demand.product.black_suv": "Black SUV",
  "dash.demand.product.black": "Black",
  "dash.demand.product.comfort": "Comfort",
  "dash.demand.product.x": "X",
  "dash.demand.product.xl": "XL",
  "dash.demand.week.zone": "Zone",
  "dash.demand.week.blocks": "Best blocks this week",
  "dash.demand.week.noBlocks": "No block stands out yet. Log a few shifts.",
  "dash.demand.week.expected": "expected offers",
  "dash.demand.week.ownData": "from your data",
  "dash.demand.week.hoursLogged": "hours logged here",
  "dash.demand.week.computed": "Computed",
  "dash.demand.week.p15": "chance of a Black offer within 15 min",
  "dash.demand.week.flights": "DEN flights",
  "dash.demand.week.events": "Events",
  "dash.demand.week.holiday": "Holiday",
  "dash.demand.week.privateRide": "Your private ride",
  "dash.demand.week.empty": "Import your Uber data or log your first shift to see the week.",
  "dash.demand.week.thin": "Thin data: mostly the proxy prior",
  "dash.demand.dow.mon": "Mon",
  "dash.demand.dow.tue": "Tue",
  "dash.demand.dow.wed": "Wed",
  "dash.demand.dow.thu": "Thu",
  "dash.demand.dow.fri": "Fri",
  "dash.demand.dow.sat": "Sat",
  "dash.demand.dow.sun": "Sun",
  "dash.demand.import.title": "Import your Uber data",
  "dash.demand.import.help":
    "Request the ZIP from Uber (Help → Request your personal Uber data), then drop it here. Only the CSV files inside are read.",
  "dash.demand.import.drop": "Drop the ZIP here or tap to choose",
  "dash.demand.import.uploading": "Uploading",
  "dash.demand.import.processing": "Reading the files",
  "dash.demand.import.done": "Import finished",
  "dash.demand.import.found": "Files found",
  "dash.demand.import.missing": "Files missing",
  "dash.demand.import.trips": "Trips",
  "dash.demand.import.segments": "Waiting segments",
  "dash.demand.import.windows": "Offer windows",
  "dash.demand.import.inserted": "new",
  "dash.demand.import.skipped": "already there",
  "dash.demand.import.range": "Date range",
  "dash.demand.import.byProduct": "By product",
  "dash.demand.import.last": "Last import",
  "dash.demand.import.never": "Nothing imported yet.",
  "dash.demand.import.err.not_a_zip": "That file is not a ZIP.",
  "dash.demand.import.err.no_csv": "The ZIP has no CSV files inside.",
  "dash.demand.import.err.too_large": "The ZIP is over 50 MB.",
  "dash.demand.import.err.generic": "Import failed. Try again.",
```

Add to the `ES` dictionary right after `"dash.nav.stats": "Mis Stats",`:

```ts
  "dash.nav.demand": "Dónde esperar",
  "dash.demand.title": "Dónde esperar",
  "dash.demand.tab.log": "Registro",
  "dash.demand.tab.week": "Semana",
  "dash.demand.tab.import": "Importar",
  "dash.demand.log.online": "En línea",
  "dash.demand.log.here": "Estoy aquí",
  "dash.demand.log.offer": "Oferta",
  "dash.demand.log.offline": "Fuera",
  "dash.demand.log.accepted": "Aceptada",
  "dash.demand.log.fare": "Tarifa (opcional)",
  "dash.demand.log.send": "Registrar oferta",
  "dash.demand.log.cancel": "Cancelar",
  "dash.demand.log.state.open": "Esperando desde",
  "dash.demand.log.state.enroute": "En viaje desde",
  "dash.demand.log.state.offline": "Fuera de línea",
  "dash.demand.log.today": "Hoy",
  "dash.demand.log.empty": "Sin toques hoy. Toca En línea cuando te conectes.",
  "dash.demand.log.noPosition": "sin posición",
  "dash.demand.log.retry": "Reintentar posición",
  "dash.demand.log.saved": "Guardado",
  "dash.demand.log.failed": "No se guardó, toca de nuevo",
  "dash.demand.log.denLot": "Lote DEN",
  "dash.demand.log.autoPing": "Registro automático cada minuto mientras esta pantalla está abierta",
  "dash.demand.product.black_suv": "Black SUV",
  "dash.demand.product.black": "Black",
  "dash.demand.product.comfort": "Comfort",
  "dash.demand.product.x": "X",
  "dash.demand.product.xl": "XL",
  "dash.demand.week.zone": "Zona",
  "dash.demand.week.blocks": "Mejores bloques de la semana",
  "dash.demand.week.noBlocks": "Ningún bloque destaca todavía. Registra unos turnos.",
  "dash.demand.week.expected": "ofertas esperadas",
  "dash.demand.week.ownData": "de tus datos",
  "dash.demand.week.hoursLogged": "horas registradas aquí",
  "dash.demand.week.computed": "Calculado",
  "dash.demand.week.p15": "probabilidad de una oferta Black en 15 min",
  "dash.demand.week.flights": "Vuelos DEN",
  "dash.demand.week.events": "Eventos",
  "dash.demand.week.holiday": "Festivo",
  "dash.demand.week.privateRide": "Tu viaje privado",
  "dash.demand.week.empty": "Importa tus datos de Uber o registra tu primer turno para ver la semana.",
  "dash.demand.week.thin": "Pocos datos: sobre todo el prior de proxies",
  "dash.demand.dow.mon": "Lun",
  "dash.demand.dow.tue": "Mar",
  "dash.demand.dow.wed": "Mié",
  "dash.demand.dow.thu": "Jue",
  "dash.demand.dow.fri": "Vie",
  "dash.demand.dow.sat": "Sáb",
  "dash.demand.dow.sun": "Dom",
  "dash.demand.import.title": "Importa tus datos de Uber",
  "dash.demand.import.help":
    "Pide el ZIP a Uber (Ayuda → Request your personal Uber data) y suéltalo aquí. Solo se leen los CSV de dentro.",
  "dash.demand.import.drop": "Suelta el ZIP aquí o toca para elegir",
  "dash.demand.import.uploading": "Subiendo",
  "dash.demand.import.processing": "Leyendo los archivos",
  "dash.demand.import.done": "Importación terminada",
  "dash.demand.import.found": "Archivos encontrados",
  "dash.demand.import.missing": "Archivos que faltan",
  "dash.demand.import.trips": "Viajes",
  "dash.demand.import.segments": "Tramos de espera",
  "dash.demand.import.windows": "Ventanas de ofertas",
  "dash.demand.import.inserted": "nuevos",
  "dash.demand.import.skipped": "ya estaban",
  "dash.demand.import.range": "Rango de fechas",
  "dash.demand.import.byProduct": "Por producto",
  "dash.demand.import.last": "Última importación",
  "dash.demand.import.never": "Nada importado todavía.",
  "dash.demand.import.err.not_a_zip": "Ese archivo no es un ZIP.",
  "dash.demand.import.err.no_csv": "El ZIP no tiene archivos CSV dentro.",
  "dash.demand.import.err.too_large": "El ZIP pesa más de 50 MB.",
  "dash.demand.import.err.generic": "La importación falló. Inténtalo de nuevo.",
```

- [ ] **Step 3: Navigation, gated by the feature flag**

In `frontend/components/bv/dash/DriverTabBar.tsx`: add a constant after `MORE`:

```ts
const DEMAND_ITEM = { seg: "demand", href: "/dashboard/demand", icon: "map-pin", key: "dash.nav.demand" };
```

and change the two places that build the "more" list so the item is included when `me?.features?.demand`:

```ts
  const moreItems = [...(me?.features?.demand ? [DEMAND_ITEM] : []), ...MORE];
  const moreActive = (me?.is_admin ? [...moreItems, ...ADMIN_ITEMS] : moreItems).some((m) => m.seg === seg);
```

and use `moreItems` where `MORE` is rendered inside the sheet (`MORE.map(` → `moreItems.map(`).

In `frontend/components/bv/dash/DashShell.tsx`: add after the `NAV` constant:

```ts
const DEMAND_NAV = { seg: "demand", href: "/dashboard/demand", icon: "map-pin", key: "dash.nav.demand" };
```

and change `const nav = me?.is_admin ? [...NAV, ...ADMIN_NAV] : NAV;` to:

```ts
  const base = me?.features?.demand ? [...NAV.slice(0, 5), DEMAND_NAV, ...NAV.slice(5)] : NAV;
  const nav = me?.is_admin ? [...base, ...ADMIN_NAV] : base;
```

(the item lands right after "My Stats").

- [ ] **Step 4: Route and tabs shell**

Create `frontend/app/dashboard/demand/page.tsx`:

```tsx
import { Suspense } from "react";

import { DemandPage } from "@/components/bv/dash/demand/DemandPage";

export const dynamic = "force-dynamic";

export default function DemandRoute() {
  return (
    <Suspense fallback={null}>
      <DemandPage />
    </Suspense>
  );
}
```

Create `frontend/components/bv/dash/demand/DemandPage.tsx`:

```tsx
"use client";

/* "Where to wait" — three tabs: one-tap shift log (default while driving), the
   7×24 week planner, and the Uber export import. The tab lives in the URL
   (?tab=) so a phone reload lands where the driver was. */

import { useRouter, useSearchParams } from "next/navigation";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { ImportTab } from "./ImportTab";
import { LogTab } from "./LogTab";
import { WeekTab } from "./WeekTab";

type Tab = "log" | "week" | "import";
const TABS: { id: Tab; icon: string; key: string }[] = [
  { id: "log", icon: "zap", key: "dash.demand.tab.log" },
  { id: "week", icon: "calendar", key: "dash.demand.tab.week" },
  { id: "import", icon: "upload", key: "dash.demand.tab.import" },
];

export function DemandPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = raw === "week" || raw === "import" ? raw : "log";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 900 }}>
      <div style={{ display: "flex", gap: 6 }} role="tablist">
        {TABS.map((tb) => {
          const active = tb.id === tab;
          return (
            <button
              key={tb.id}
              role="tab"
              aria-selected={active}
              onClick={() => router.replace(`/dashboard/demand?tab=${tb.id}`)}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                minHeight: 44,
                borderRadius: 10,
                border: `1px solid ${active ? "var(--volt)" : "var(--line-strong)"}`,
                background: active ? "rgba(0,229,255,0.08)" : "var(--obsidian)",
                color: active ? "var(--volt)" : "var(--silver)",
                fontFamily: "var(--font-sans)",
                fontWeight: active ? 700 : 500,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              <Icon name={tb.icon} size={18} color="currentColor" />
              {t(tb.key)}
            </button>
          );
        })}
      </div>
      {tab === "log" && <LogTab />}
      {tab === "week" && <WeekTab />}
      {tab === "import" && <ImportTab />}
    </div>
  );
}
```

Create placeholder-free stubs so the build passes until Tasks 11–12 replace them: `LogTab.tsx`, `WeekTab.tsx`, `ImportTab.tsx`, each:

```tsx
"use client";

export function LogTab() {
  return null;
}
```

(with `WeekTab` / `ImportTab` respectively). They are fully implemented in the next two tasks.

- [ ] **Step 5: Type-check, lint, build**

Run (from `frontend/`): `npm run typecheck && npm run lint && npm run build`
Expected: zero errors. A `map-pin` icon warning means the registry name differs; check `grep -n '"map-pin"' components/bv/Icon.tsx`.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/demand.ts frontend/lib/i18n.tsx frontend/components/bv/dash/DriverTabBar.tsx frontend/components/bv/dash/DashShell.tsx frontend/components/bv/dash/demand frontend/app/dashboard/demand
git commit -m "feat(frontend): 'Where to wait' route, API client, i18n and nav (feature-flagged)"
```

---

### Task 11: Log tab — four one-tap buttons, offer chips, auto-ping, today's list

**Files:**
- Replace: `frontend/components/bv/dash/demand/LogTab.tsx`

**Interfaces:**
- Consumes: `logEvent`, `getToday`, `newEventId`, `PRODUCTS`, types (Task 10); `Icon`, `Pill` from `../../ui`; `useI18n`.
- Behaviour (from the spec, "Tab Log"): four big buttons (Online, Here, Offer, Offline) in the upper half; Offer expands product chips + Accepted toggle + optional fare; each tap → `getCurrentPosition` (8 s, high accuracy) → POST with a fresh `client_event_id`; GPS failure → event sent without position, row shows a "no position" badge with a retry that re-sends a `here` with position; while state is `open` and the tab is visible, a `ping` every 60 s with a Screen Wake Lock (best effort); today's list newest first; layout fits 390 px wide and Android split-screen (~390×400): no page header, no scroll needed for the buttons.
- **Amendment (2026-09-17, Addendum A):** Offer is the primary control — first and largest, its product chips + Accepted toggle always visible; Online, Here and Offline are secondary (smaller, one row). Copy under the buttons, EN/ES: "Your monthly Uber export covers where you waited; tap every offer." / "Tu exportación mensual de Uber cubre dónde esperaste; toca cada oferta." Everything else in this task stands.

- [ ] **Step 1: Implement**

Replace `frontend/components/bv/dash/demand/LogTab.tsx` with:

```tsx
"use client";

/* One-tap shift log. This is the screen that sits next to Uber Driver in Android
   split-screen, so: no header, four thumb-sized buttons in the upper half, and the
   offer chips inline. Every tap gets a client id so a retried POST is a no-op. */

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import {
  type LogEvent,
  type LogKind,
  type Product,
  PRODUCTS,
  type TodayLog,
  getToday,
  logEvent,
  newEventId,
} from "@/lib/demand";

const GPS_TIMEOUT_MS = 8000;
const PING_MS = 60_000;

type Pos = { lat: number; lng: number } | null;

function getPosition(): Promise<Pos> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: GPS_TIMEOUT_MS, maximumAge: 15_000 },
    );
  });
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function LogTab() {
  const { t } = useI18n();
  const [today, setToday] = useState<TodayLog | null>(null);
  const [busy, setBusy] = useState<LogKind | null>(null);
  const [offerOpen, setOfferOpen] = useState(false);
  const [product, setProduct] = useState<Product>("black");
  const [accepted, setAccepted] = useState(false);
  const [fare, setFare] = useState("");
  const [flash, setFlash] = useState<"saved" | "failed" | null>(null);
  const wakeLock = useRef<{ release: () => Promise<void> } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setToday(await getToday());
    } catch {
      /* keep the last known state; the next tap refreshes */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const send = useCallback(
    async (kind: LogKind, extra: Partial<Parameters<typeof logEvent>[0]> = {}) => {
      setBusy(kind);
      const pos = await getPosition();
      try {
        await logEvent({
          client_event_id: newEventId(),
          kind,
          lat: pos?.lat ?? null,
          lng: pos?.lng ?? null,
          ...extra,
        });
        setFlash("saved");
      } catch {
        setFlash("failed");
      } finally {
        setBusy(null);
        setTimeout(() => setFlash(null), 1800);
        refresh();
      }
    },
    [refresh],
  );

  // Auto-ping while waiting and this screen is visible; a wake lock keeps the
  // screen on so the ping loop survives (best effort — iOS ignores it when hidden).
  const waiting = today?.state === "open";
  useEffect(() => {
    if (!waiting) return;
    let alive = true;
    const tick = () => {
      if (!alive || document.visibilityState !== "visible") return;
      send("ping");
    };
    const id = setInterval(tick, PING_MS);
    (async () => {
      try {
        const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
        if (nav.wakeLock) wakeLock.current = await nav.wakeLock.request("screen");
      } catch {
        /* unsupported or denied: pings still run while visible */
      }
    })();
    return () => {
      alive = false;
      clearInterval(id);
      wakeLock.current?.release().catch(() => {});
      wakeLock.current = null;
    };
  }, [waiting, send]);

  const submitOffer = async () => {
    const f = fare.trim() ? Number(fare) : null;
    await send("offer", { product, accepted, fare: Number.isFinite(f as number) ? f : null });
    setOfferOpen(false);
    setAccepted(false);
    setFare("");
  };

  const big = (active: boolean, tone: "volt" | "silver" | "warn"): React.CSSProperties => ({
    minHeight: 84,
    borderRadius: 14,
    border: `1px solid ${active ? "var(--volt)" : "var(--line-strong)"}`,
    background: tone === "warn" ? "rgba(255,90,90,0.08)" : active ? "rgba(0,229,255,0.10)" : "var(--obsidian)",
    color: tone === "warn" ? "#ff7a7a" : active ? "var(--volt)" : "var(--white)",
    fontFamily: "var(--font-display)",
    fontSize: 20,
    fontWeight: 700,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    cursor: "pointer",
    WebkitTapHighlightColor: "transparent",
  });

  const chip = (on: boolean): React.CSSProperties => ({
    padding: "10px 14px",
    borderRadius: 999,
    border: `1px solid ${on ? "var(--volt)" : "var(--line-strong)"}`,
    background: on ? "rgba(0,229,255,0.12)" : "transparent",
    color: on ? "var(--volt)" : "var(--silver)",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
  });

  const stateKey =
    today?.state === "open" ? "dash.demand.log.state.open"
    : today?.state === "enroute" ? "dash.demand.log.state.enroute"
    : "dash.demand.log.state.offline";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13, color: "var(--silver)" }}>
        <span>
          {t(stateKey)}
          {today?.open_since ? ` ${fmtTime(today.open_since)}` : ""}
        </span>
        <span style={{ color: flash === "failed" ? "#ff7a7a" : "var(--volt)", minHeight: 16 }}>
          {flash === "saved" ? t("dash.demand.log.saved") : flash === "failed" ? t("dash.demand.log.failed") : ""}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <button style={big(today?.state === "open", "volt")} disabled={busy !== null} onClick={() => send("online")}>
          <Icon name="zap" size={22} color="currentColor" />
          {t("dash.demand.log.online")}
        </button>
        <button style={big(false, "silver")} disabled={busy !== null} onClick={() => send("here")}>
          <Icon name="map-pin" size={22} color="currentColor" />
          {t("dash.demand.log.here")}
        </button>
        <button style={big(offerOpen, "volt")} disabled={busy !== null} onClick={() => setOfferOpen((o) => !o)}>
          <Icon name="bell" size={22} color="currentColor" />
          {t("dash.demand.log.offer")}
        </button>
        <button style={big(false, "warn")} disabled={busy !== null} onClick={() => send("offline")}>
          <Icon name="x" size={22} color="currentColor" />
          {t("dash.demand.log.offline")}
        </button>
      </div>

      {offerOpen && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--obsidian)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {PRODUCTS.map((p) => (
              <button key={p} style={chip(product === p)} onClick={() => setProduct(p)}>
                {t(`dash.demand.product.${p}`)}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button style={chip(accepted)} onClick={() => setAccepted((a) => !a)}>
              <Icon name="check" size={14} color="currentColor" /> {t("dash.demand.log.accepted")}
            </button>
            <input
              inputMode="decimal"
              placeholder={t("dash.demand.log.fare")}
              value={fare}
              onChange={(e) => setFare(e.target.value)}
              style={{ flex: 1, minWidth: 0, padding: "10px 12px", borderRadius: 10, border: "1px solid var(--line-strong)", background: "transparent", color: "var(--white)" }}
            />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={{ ...chip(true), flex: 1, textAlign: "center", padding: "12px" }} disabled={busy !== null} onClick={submitOffer}>
              {t("dash.demand.log.send")}
            </button>
            <button style={{ ...chip(false), padding: "12px 16px" }} onClick={() => setOfferOpen(false)}>
              {t("dash.demand.log.cancel")}
            </button>
          </div>
        </div>
      )}

      {waiting && (
        <div style={{ fontSize: 12, color: "var(--silver)" }}>{t("dash.demand.log.autoPing")}</div>
      )}

      <div style={{ fontFamily: "var(--font-display)", fontSize: 14, fontWeight: 700, marginTop: 4 }}>
        {t("dash.demand.log.today")}
      </div>
      {!today || today.events.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.log.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {today.events.map((e: LogEvent) => (
            <div key={`${e.kind}-${e.id}`} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, padding: "8px 10px", borderRadius: 10, background: "var(--obsidian)" }}>
              <span style={{ color: "var(--silver)", width: 48 }}>{fmtTime(e.at)}</span>
              <span style={{ fontWeight: 600 }}>{t(`dash.demand.log.${e.kind === "offer" ? "offer" : e.kind}`)}</span>
              {e.product && <span style={{ color: "var(--volt)" }}>{t(`dash.demand.product.${e.product}`)}</span>}
              {e.accepted && <Icon name="circle-check" size={14} color="var(--volt)" />}
              {e.fare != null && <span>${e.fare}</span>}
              {e.zone_key === "den_lot" && <span style={{ color: "var(--silver)" }}>{t("dash.demand.log.denLot")}</span>}
              {e.no_position && (
                <button onClick={() => send("here")} style={{ marginLeft: "auto", ...chip(false), padding: "4px 10px", fontSize: 12 }}>
                  {t("dash.demand.log.noPosition")} · {t("dash.demand.log.retry")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

`bell` and `check` are in the icon registry (see the registry list in Global Constraints); `circle-check` too.

- [ ] **Step 2: Type-check, lint, build**

Run (from `frontend/`): `npm run typecheck && npm run lint && npm run build`
Expected: zero errors.

- [ ] **Step 3: Manual check on a phone-sized viewport**

With the local stack up (`docker compose up -d` from the repo root, frontend on `http://localhost:3005`), log in as owner (`DASHBOARD_PASSWORD` from `.env`), open `/dashboard/demand`, set the viewport to 390×844 (Chrome devtools) and to 390×400 (split-screen height): the four buttons and the state line must be visible without scrolling; tapping Online creates a row in the list; the console shows no errors. Use the Playwright MCP for this if driving a browser by hand is not possible:

```
browser_navigate http://localhost:3005/login → fill password → browser_navigate /dashboard/demand → browser_resize 390 844 → browser_click "Online" → browser_snapshot → browser_console_messages
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/bv/dash/demand/LogTab.tsx
git commit -m "feat(frontend): one-tap shift log — Online/Here/Offer/Offline, product chips, auto-ping"
```

---

### Task 12: Week tab and Import tab

**Files:**
- Replace: `frontend/components/bv/dash/demand/WeekTab.tsx`
- Replace: `frontend/components/bv/dash/demand/ImportTab.tsx`

**Interfaces:**
- Consumes: `getWeek`, `importZip`, `getImportStatus`, `DOW_KEYS`, types (Task 10).
- Behaviour (spec "Tab Week" / "Tab Import"): zone chips; 7×24 grid coloured by `mean` (sequential cyan scale), hatched when `own_share < 0.2`; tap a cell → detail line (p15, interval, own share, hours, reasons); top blocks list above the grid; private rides outlined; empty state. Import: drop zone / picker, progress, summary with missing files in red and their consequence, last import on load, error strings by code.
- **Amendment (2026-09-17, Addendum A):** when `summary.gps` is present the Import tab renders, after the files block, a "Your waits this month" / "Tus esperas del mes" table: one row per `top_waits` item — label (`place` + `distance_km` with one decimal when `place` is set; else `zone_name`; else `dash.demand.import.gps.outside` when `outside`; else `dash.demand.import.gps.other`), `hours`, `premium_requests`, `per_hour` (2 decimals) — plus one line "GPS: {days} days, {pings} pings, {home_hours} h at home excluded" (EN/ES). New i18n keys under `dash.demand.import.gps.*`. When `summary.gps` is null nothing extra renders. The Playwright fixture ZIP of Task 13 gains an analytics file so the table is exercised.

- [ ] **Step 1: Week tab**

Replace `frontend/components/bv/dash/demand/WeekTab.tsx` with:

```tsx
"use client";

/* 7×24 planner per zone. Colour = expected Black offers; hatching = the estimate
   is still mostly the proxy prior (own_share < 0.2). Hand-rolled like the other
   dashboard charts — no chart library. */

import { useEffect, useMemo, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { DOW_KEYS, type WeekCell, type WeekPayload, getWeek } from "@/lib/demand";

const THIN = 0.2;

function shade(v: number, max: number): string {
  const x = max > 0 ? Math.min(1, v / max) : 0;
  // 0 → near-black, 1 → electric cyan.
  const a = 0.08 + 0.72 * x;
  return `rgba(0,229,255,${a.toFixed(3)})`;
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export function WeekTab() {
  const { t } = useI18n();
  const [zone, setZone] = useState<string | null>(null);
  const [data, setData] = useState<WeekPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<{ d: number; h: number } | null>(null);

  useEffect(() => {
    let alive = true;
    setErr(null);
    getWeek(zone)
      .then((w) => alive && setData(w))
      .catch((e) => alive && setErr(String(e?.message || e)));
    return () => {
      alive = false;
    };
  }, [zone]);

  const max = useMemo(
    () => (data?.grid.length ? Math.max(...data.grid.flat().map((c) => c?.mean ?? 0)) : 0),
    [data],
  );
  const privateByCell = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.private_rides ?? []) {
      const d = new Date(r.at);
      s.add(`${(d.getDay() + 6) % 7}-${d.getHours()}`);
    }
    return s;
  }, [data]);

  if (err) return <div style={{ color: "#ff7a7a", fontSize: 13 }}>{err}</div>;
  if (!data) return null;
  if (!data.grid.length) {
    return <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.week.empty")}</div>;
  }
  const cell: WeekCell | null = sel ? data.grid[sel.d][sel.h] : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        {data.zones.map((z) => {
          const on = z.key === data.zone;
          return (
            <button
              key={z.key}
              onClick={() => setZone(z.key)}
              style={{ whiteSpace: "nowrap", padding: "8px 12px", borderRadius: 999, border: `1px solid ${on ? "var(--volt)" : "var(--line-strong)"}`, background: on ? "rgba(0,229,255,0.12)" : "transparent", color: on ? "var(--volt)" : "var(--silver)", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              {z.name}
            </button>
          );
        })}
      </div>

      <div>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
          {t("dash.demand.week.blocks")}
        </div>
        {data.top_blocks.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.week.noBlocks")}</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.top_blocks.map((b, i) => (
              <div key={i} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "8px 10px", borderRadius: 10, background: "var(--obsidian)", fontSize: 13 }}>
                <span style={{ fontWeight: 700, color: "var(--volt)" }}>
                  {t(`dash.demand.dow.${DOW_KEYS[b.dow]}`)} {b.start_hour}:00–{b.end_hour}:00
                </span>
                <span>{b.expected_offers.toFixed(1)} {t("dash.demand.week.expected")}</span>
                {b.reasons.flights != null && b.reasons.flights > 1.2 && (
                  <span style={{ color: "var(--silver)" }}><Icon name="plane" size={12} color="currentColor" /> {t("dash.demand.week.flights")} ×{b.reasons.flights}</span>
                )}
                {(b.reasons.events ?? []).map((ev) => (
                  <span key={ev} style={{ color: "var(--silver)" }}><Icon name="calendar" size={12} color="currentColor" /> {ev}</span>
                ))}
                {b.reasons.holiday && <span style={{ color: "var(--silver)" }}>{t("dash.demand.week.holiday")}: {b.reasons.holiday}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "34px repeat(24, minmax(11px, 1fr))", gap: 2, minWidth: 360 }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} style={{ fontSize: 9, color: "var(--silver)", textAlign: "center" }}>{h % 3 === 0 ? h : ""}</div>
          ))}
          {data.grid.map((row, d) => (
            <FragmentRow key={d} d={d} row={row} max={max} sel={sel} setSel={setSel} privateByCell={privateByCell} label={t(`dash.demand.dow.${DOW_KEYS[d]}`)} />
          ))}
        </div>
      </div>

      {cell && sel && (
        <div style={{ padding: 12, borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--obsidian)", fontSize: 13, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontWeight: 700 }}>
            {t(`dash.demand.dow.${DOW_KEYS[sel.d]}`)} {sel.h}:00 — <span style={{ color: "var(--volt)" }}>{pct(cell.p15)}</span> {t("dash.demand.week.p15")}
          </div>
          <div style={{ color: "var(--silver)" }}>
            {pct(cell.own_share)} {t("dash.demand.week.ownData")} · {((cell.reasons.own_minutes ?? 0) / 60).toFixed(1)} {t("dash.demand.week.hoursLogged")}
            {cell.own_share < THIN ? ` · ${t("dash.demand.week.thin")}` : ""}
          </div>
          <div style={{ color: "var(--silver)" }}>
            {t("dash.demand.week.flights")} ×{cell.reasons.flights ?? 1}
            {(cell.reasons.events ?? []).length ? ` · ${t("dash.demand.week.events")}: ${cell.reasons.events!.join(", ")}` : ""}
            {cell.reasons.holiday ? ` · ${t("dash.demand.week.holiday")}: ${cell.reasons.holiday}` : ""}
            {privateByCell.has(`${sel.d}-${sel.h}`) ? ` · ${t("dash.demand.week.privateRide")}` : ""}
          </div>
        </div>
      )}

      {data.computed_at && (
        <div style={{ fontSize: 11, color: "var(--silver)" }}>
          {t("dash.demand.week.computed")} {new Date(data.computed_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}

function FragmentRow({
  d, row, max, sel, setSel, privateByCell, label,
}: {
  d: number;
  row: WeekCell[];
  max: number;
  sel: { d: number; h: number } | null;
  setSel: (s: { d: number; h: number }) => void;
  privateByCell: Set<string>;
  label: string;
}) {
  return (
    <>
      <div style={{ fontSize: 11, color: "var(--silver)", display: "flex", alignItems: "center" }}>{label}</div>
      {row.map((c, h) => {
        const on = sel?.d === d && sel?.h === h;
        const thin = (c?.own_share ?? 0) < THIN;
        const priv = privateByCell.has(`${d}-${h}`);
        return (
          <button
            key={h}
            aria-label={`${label} ${h}:00`}
            onClick={() => setSel({ d, h })}
            style={{
              height: 22,
              padding: 0,
              borderRadius: 3,
              border: on ? "2px solid var(--white)" : priv ? "2px solid #ffd166" : "1px solid rgba(255,255,255,0.06)",
              background: thin
                ? `repeating-linear-gradient(45deg, ${shade(c?.mean ?? 0, max)} 0 3px, rgba(0,0,0,0.35) 3px 5px)`
                : shade(c?.mean ?? 0, max),
              cursor: "pointer",
            }}
          />
        );
      })}
    </>
  );
}
```

- [ ] **Step 2: Import tab**

Replace `frontend/components/bv/dash/demand/ImportTab.tsx` with:

```tsx
"use client";

/* Upload the Uber data export ZIP and show exactly what came in — and what did
   not, with the consequence, so the owner knows what the model can learn from. */

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "../../Icon";
import { useI18n } from "@/lib/i18n";
import { type ImportSummary, getImportStatus, importZip } from "@/lib/demand";

type Phase = "idle" | "uploading" | "processing" | "done" | "error";

export function ImportTab() {
  const { t } = useI18n();
  const [phase, setPhase] = useState<Phase>("idle");
  const [pct, setPct] = useState(0);
  const [summary, setSummary] = useState<(ImportSummary & { at?: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getImportStatus()
      .then((s) => {
        if (!("never" in s)) setSummary(s);
      })
      .catch(() => {});
  }, []);

  const run = useCallback(
    async (file: File) => {
      setError(null);
      setPhase("uploading");
      setPct(0);
      try {
        const s = await importZip(file, (p) => {
          setPct(p);
          if (p >= 100) setPhase("processing");
        });
        setSummary({ ...s, at: new Date().toISOString() });
        setPhase("done");
      } catch (e) {
        const code = (e as { message?: string })?.message || "";
        const key = ["not_a_zip", "no_csv", "too_large"].includes(code)
          ? `dash.demand.import.err.${code}`
          : "dash.demand.import.err.generic";
        setError(t(key));
        setPhase("error");
      }
    },
    [t],
  );

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (f) run(f);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 16, fontWeight: 700 }}>{t("dash.demand.import.title")}</div>
      <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.import.help")}</div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }}
        onClick={() => input.current?.click()}
        style={{ minHeight: 120, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 14, border: `2px dashed ${drag ? "var(--volt)" : "var(--line-strong)"}`, background: drag ? "rgba(0,229,255,0.06)" : "var(--obsidian)", cursor: "pointer", fontSize: 14 }}
      >
        <Icon name="upload" size={24} color="var(--volt)" />
        {phase === "uploading" ? `${t("dash.demand.import.uploading")} ${pct}%`
          : phase === "processing" ? t("dash.demand.import.processing")
          : t("dash.demand.import.drop")}
        <input ref={input} type="file" accept=".zip,application/zip" style={{ display: "none" }} onChange={(e) => onFiles(e.target.files)} />
      </div>
      {(phase === "uploading" || phase === "processing") && (
        <div style={{ height: 6, borderRadius: 3, background: "var(--line-strong)" }}>
          <div style={{ width: `${phase === "processing" ? 100 : pct}%`, height: "100%", borderRadius: 3, background: "var(--volt)", transition: "width .2s" }} />
        </div>
      )}
      {error && <div style={{ color: "#ff7a7a", fontSize: 13 }}><Icon name="alert-circle" size={14} color="currentColor" /> {error}</div>}

      {summary && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 12, borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--obsidian)", fontSize: 13 }}>
          <div style={{ fontWeight: 700 }}>
            {phase === "done" ? t("dash.demand.import.done") : t("dash.demand.import.last")}
            {summary.at ? ` · ${new Date(summary.at).toLocaleString()}` : ""}
          </div>
          <Row label={t("dash.demand.import.trips")} a={summary.trips.inserted} b={summary.trips.skipped} t={t} />
          <Row label={t("dash.demand.import.segments")} a={summary.segments.inserted} b={summary.segments.skipped} t={t} />
          <Row label={t("dash.demand.import.windows")} a={summary.windows.inserted} b={summary.windows.skipped} t={t} />
          {summary.trips.date_min && (
            <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.range")}:</span> {summary.trips.date_min.slice(0, 10)} → {summary.trips.date_max?.slice(0, 10)}</div>
          )}
          {Object.keys(summary.trips.by_product).length > 0 && (
            <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.byProduct")}:</span> {Object.entries(summary.trips.by_product).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
          )}
          <div><span style={{ color: "var(--silver)" }}>{t("dash.demand.import.found")}:</span> {summary.files_found.join(", ") || "—"}</div>
          {summary.files_missing.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ color: "#ff7a7a", fontWeight: 700 }}>{t("dash.demand.import.missing")}</div>
              {summary.files_missing.map((m) => (
                <div key={m.kind} style={{ color: "#ff9a9a" }}>• {m.consequence}</div>
              ))}
            </div>
          )}
        </div>
      )}
      {!summary && phase === "idle" && <div style={{ fontSize: 13, color: "var(--silver)" }}>{t("dash.demand.import.never")}</div>}
    </div>
  );
}

function Row({ label, a, b, t }: { label: string; a: number; b: number; t: (k: string) => string }) {
  return (
    <div>
      <span style={{ color: "var(--silver)" }}>{label}:</span> {a} {t("dash.demand.import.inserted")} · {b} {t("dash.demand.import.skipped")}
    </div>
  );
}
```

- [ ] **Step 3: Type-check, lint, build, and a browser pass**

Run (from `frontend/`): `npm run typecheck && npm run lint && npm run build` — zero errors.

Then with the local stack: import the fixture ZIP built in `tests/test_uber_import.py` (write it to disk once with `python -c "from tests.test_uber_import import *; open('/tmp/bv-uber.zip','wb').write(_zip({'driver_lifetime_trips-0.csv': TRIPS_2025_HEADER+'\n'+TRIPS_2025_ROW+'\n'}))"` from `backend/`), upload it in the Import tab, confirm the summary shows 1 trip and the two missing files in red; open the Week tab, confirm the grid renders and a tapped cell shows its detail; 390 px wide, no horizontal page scroll, zero console errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/bv/dash/demand/WeekTab.tsx frontend/components/bv/dash/demand/ImportTab.tsx
git commit -m "feat(frontend): week planner grid with best blocks, and the Uber export import screen"
```

---

### Task 13: Version bump, CHANGELOG, setup doc, full verification (Playwright + TestSprite)

**Files:**
- Modify: `frontend/lib/version.ts` (`CURRENT_VERSION` + prepend a `CHANGELOG` entry)
- Modify: `CHANGELOG.md` (prepend, same format as the top entry)
- Create: `docs/setup-demand.md`

- [ ] **Step 1: Version and changelog**

In `frontend/lib/version.ts` set `export const CURRENT_VERSION = "0.93.0";` and prepend to the `CHANGELOG` array:

```ts
  {
    version: "0.93.0",
    date: "<today, YYYY-MM-DD>",
    title: "Where to wait: your week, planned from your own Black data",
    changes: [
      "New 'Where to wait' tab: import your Uber data export and see which hours of the week bring Black and Black SUV offers, zone by zone, with the reasons (DEN flight banks, events, holidays).",
      "One-tap shift log built for split-screen next to Uber: Online, I'm here, Offer (with product), Offline. Every minute you wait and every offer you see teaches the planner.",
      "Every cell says how much comes from your data and how many hours you have logged there — thin cells are hatched, never hidden.",
    ],
  },
```

Prepend the equivalent entry to `CHANGELOG.md` in the file's existing format: heading `## 0.93.0 — <date> — Where to wait: your week, planned from your own Black data`, one short paragraph saying what shipped, then the three bullets above as `- **bold lead** — detail`. Replace `<today, YYYY-MM-DD>` and `<date>` with the actual date on the day you commit.

- [ ] **Step 2: Setup doc**

Create `docs/setup-demand.md`:

```markdown
# "Where to wait" — setup (Phase 1)

The planner needs three things once, plus the owner's data.

## 1. Environment (`.env` on the VPS)

| var | value |
|---|---|
| `DEMAND_ENABLED` | `true` (shows the tab, schedules the hourly recompute) |
| `CENSUS_API_KEY` | free key from https://api.census.gov/data/key_signup.html |
| `DEN_LOT_LAT` / `DEN_LOT_LNG` | `39.8399691` / `-104.6698651` — Google Maps place pin "Commercial Holding Lot", 8500 Peña Blvd, Denver, CO 80249 (place id `0x876c67929cf14ec3:0x1cf80066bd0b9c72`), confirmed by the owner on 2026-09-17 and already set in the local root `.env`. The map embed/viewport centre (`39.8399732, -104.67244`) sits 220 m west of the pin: inside the 400 m radius, but use the pin. Leaving both empty keeps DEN-lot tagging off |
| `DEN_LOT_RADIUS_M` | `400` |
| `DEMAND_HOME_LAT` / `DEMAND_HOME_LNG` | the owner's home point — it lives in the root `.env` of his Mac; copy it from there, never write it in a doc or a commit. Waits within the radius are excluded from the model (Addendum A) |
| `DEMAND_HOME_RADIUS_M` | `300` |
| `DEMAND_BRIDGE_FARE_DEFAULT` | `35` |

Restart the backend after changing them (`docker compose up -d backend`).

## 2. Static data (run once, then when the curated list changes)

```bash
docker compose exec -T backend python -m app.scripts.build_demand_priors     # Census + places → hex_priors
docker compose exec -T backend python -m app.scripts.build_flight_baseline   # BTS On-Time → den_flight_baseline (monthly)
```

`backend/data/demand_places.json` is committed; regenerate it locally with
`python -m app.scripts.geocode_places` after editing `app/services/demand_places.py`.

Monthly cron on the VPS (user crontab):

```
15 4 3 * * cd ~/Black-Volt-Mobility && docker compose exec -T backend python -m app.scripts.build_flight_baseline >> ~/bv_flights.log 2>&1
```

## 3. The owner's data

1. Uber → Help → "Request your personal Uber data" → download the ZIP when the email arrives.
2. Dashboard → Where to wait → Import → drop the ZIP. The summary lists the files found and, in red, the ones missing and what that means.
3. Log every shift: Online when going on, I'm here on each move, Offer (with product) on every ping, Offline at the end. The Week tab improves as hours accumulate; cells with < 20% own data are hatched.

## What it does not do (yet)

No live map (Phase 2), no paid flight schedules, no Uber credential linking, no background GPS.
```

- [ ] **Step 3: Full backend and frontend verification**

From `backend/` (local docker stack up, migrated):

```bash
ruff check . && alembic upgrade head && pytest -q
```

Expected: all tests pass (previous count + the new files: `test_demand_models`, `test_demand_model`, `test_uber_import`, `test_demand_api`, `test_shift_log`, `test_demand_prior`, `test_flights_baseline`, `test_demand_jobs`). Record the final count in the commit message.

From `frontend/`: `npm run lint && npm run typecheck && npm run build` — zero errors.

- [ ] **Step 4: End-to-end in a real browser (Playwright MCP)**

With the local stack running and `DEMAND_ENABLED=true` in the local `.env`:

1. `browser_navigate` to `http://localhost:3005/login`, sign in with the owner password, `browser_resize` to 390×844.
2. `/dashboard` → the "More" sheet shows "Where to wait"; open it.
3. Log tab: click Online, then Offer → chip "Black" → "Log offer"; the list shows both rows with times. `browser_console_messages` has zero errors.
4. Import tab: upload `/tmp/bv-uber.zip` (from Task 12 step 3) via `browser_file_upload`; the summary shows 1 trip and the red "missing" lines.
5. Week tab: the grid renders; click a cell; the detail line shows a percentage and "from your data".
6. `browser_resize` to 390×400 (split-screen): the four Log buttons remain visible without scrolling.
7. Switch language to ES with the header toggle: every string in the three tabs is Spanish (no raw `dash.demand.*` keys on screen).

Save two screenshots (`browser_take_screenshot`) — Log at 390×400 and Week at 390×844 — under the scratchpad for the PR description.

- [ ] **Step 5: TestSprite run (the owner allowed it)**

If the repo already has a TestSprite project, use the `testsprite-verify` skill to run the existing frontend tests plus one new plan covering steps 2–5 above; otherwise use `testsprite-onboard` once to create the project against `http://localhost:3005` with the owner login, then run. Report the verdict as-is; a red TestSprite run on a step that passed by hand in Step 4 is investigated, not dismissed.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/version.ts CHANGELOG.md docs/setup-demand.md
git commit -m "chore(release): v0.93.0 — Where to wait phase 1 (planner + one-tap log); N backend tests green"
```

(replace `N` with the pytest count).

---

### Task 14: PR, merge, tag, deploy to the VPS, run the scripts, verify live

**Files:** none new. Uses `gh`, `ssh ender-vps`.

- [ ] **Step 1: Push the branch and open the PR**

```bash
git push -u origin feat/demand-phase1
gh pr create --base main --head feat/demand-phase1 --title "Where to wait — phase 1: planner + one-tap log (v0.93.0)" --body-file - <<'EOF2'
## What
- Import of the Uber driver data export (three real layouts), idempotent.
- One-tap shift log (Online / Here / Offer with product / Offline) with auto-ping.
- Hourly 7×24 planner per zone: proxy prior (Census affluence, luxury hotels, generators, DEN flight banks, events, holidays) corrected by the owner's own waits and offers (Gamma-Poisson), with own-data share per cell.
- New dashboard tab (feature-flagged by `DEMAND_ENABLED`), EN + ES.

## Spec / plan
- docs/superpowers/specs/2026-09-17-black-demand-heatmap-design.md
- docs/superpowers/plans/2026-09-17-black-demand-phase1.md

## Verification
- backend: ruff, alembic head (no drift), pytest N green
- frontend: lint, typecheck, build; Playwright at 390×844 and 390×400, EN and ES, zero console errors
- TestSprite: <verdict>

## Deploy notes
- migration 0050; new env vars (see docs/setup-demand.md); run `build_demand_priors` and `build_flight_baseline` once after deploy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF2
```

Wait for CI (`gh pr checks --watch`). Green → `gh pr merge --squash --delete-branch` (or merge commit, whichever the repo used last: `git log --merges -1`). Then:

```bash
git checkout main && git pull
git tag v0.93.0 && git push origin v0.93.0
gh release create v0.93.0 --title "v0.93.0 — Where to wait (phase 1)" --notes-file CHANGELOG.md
```

- [ ] **Step 2: Deploy**

The production stack runs on the host behind the `ender-vps` SSH alias (`vps3427209.trouble-free.net`; the `vps` alias points elsewhere and times out — do not use it). Before touching it, confirm it is the right machine: `ssh ender-vps 'hostname; docker ps --format "{{.Names}}" | grep blackvolt'` must list `blackvolt-backend`.

```bash
ssh ender-vps 'cd ~/Black-Volt-Mobility && git fetch && git checkout main && git pull && \
  grep -q "^DEMAND_ENABLED=" .env || echo "DEMAND_ENABLED=true" >> .env; \
  grep -q "^CENSUS_API_KEY=" .env || echo "CENSUS_API_KEY=<owner supplies>" >> .env; \
  docker compose build backend frontend && docker compose up -d && \
  docker compose exec -T backend alembic upgrade head && \
  docker compose exec -T backend python -m app.scripts.build_demand_priors && \
  docker compose exec -T backend python -m app.scripts.build_flight_baseline'
```

If the repo on the VPS is not a git checkout that tracks `origin/main` (check `git remote -v` first), deploy the way the last release was deployed (see the most recent `docs/` deploy notes or the previous release's memory) instead of `git pull`.

The `CENSUS_API_KEY` must come from the owner (Owner TODO 2); the priors script fails with a clear `CENSUS_API_KEY is not set` until then — the rest of the deploy still works, and the Week tab shows only the flat prior.

- [ ] **Step 3: Verify live**

```bash
curl -s https://blackvoltmobility.com/api/v1/health           # version 0.93.0? (frontend reports it; backend health shows env/db)
curl -s -o /dev/null -w "%{http_code}\n" https://blackvoltmobility.com/api/v1/demand/week   # 401 without a session
ssh ender-vps 'cd ~/Black-Volt-Mobility && docker compose exec -T db psql -U blackvolt -d blackvolt -Atc "select count(*) from hex_priors; select count(*) from den_flight_baseline;"'
ssh ender-vps 'cd ~/Black-Volt-Mobility && docker compose logs --tail=50 backend | grep -i "demand\|scheduler"'
```

Expected: health `db: true`, `/demand/week` → 401, `hex_priors` in the thousands and `den_flight_baseline` up to 2016 rows (12 months × 7 × 24), the scheduler log line lists `demand_week`. Then, in a real browser on the phone: log in, the "Where to wait" item is in the More sheet, the Log tab responds, and the Import tab is ready for the owner's ZIP.

- [ ] **Step 4: Hand back to the owner**

Tell the owner, in Spanish, exactly: what is live, the two things only they can do (upload the Uber ZIP; provide the Census key and the DEN lot position), and that the 4-week logging period starts now. Update the memory note `project_blackvolt_black_demand_heatmap.md` with the deployed version, the commit, and the date.
