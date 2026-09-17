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
