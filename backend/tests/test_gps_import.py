"""GPS analytics import (Task 15, Addendum A): segmentation, request cells, top
waits and the DB replace-window/backfill, on a synthetic day built on the real
18-column analytics header."""
import asyncio
import csv
import io
import os
from datetime import UTC, datetime, timedelta

import asyncpg
import h3
import pytest

os.environ["DASHBOARD_PASSWORD"] = "test-pw"
os.environ["AUTH_SECRET"] = "api-test-secret"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_SIMULATED"] = "true"
os.environ["MAPS_SIMULATED"] = "true"
os.environ["SMART_SIMULATED"] = "true"
os.environ["DEMAND_ENABLED"] = "true"
os.environ["DEN_LOT_LAT"] = "39.8000"
os.environ["DEN_LOT_LNG"] = "-104.7000"
os.environ["DEMAND_HOME_LAT"] = "39.60000"
os.environ["DEMAND_HOME_LNG"] = "-104.80000"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import gps_import  # noqa: E402
from app.services import uber_import as ui  # noqa: E402
from tests.test_uber_import import TRIPS_2025_HEADER, TRIPS_2025_ROW, _zip  # noqa: E402

client = TestClient(app)

ANALYTICS_HEADER = (
    "Analytics Event Name,City,Cellular Carrier,Carrier MCC,Carrier MNC,IP Address,"
    "Device Language,Device Model,Device OS,Device OS Version,Is Driver Online?,"
    "Driver Status,Application Version,Event Time (UTC),Latitude,Longitude,Speed (GPS),"
    "Analytics Event Type"
)

A = (39.71700, -104.95300)
B = (39.71699971270586, -104.94481595238592)  # ~700 m east of A, a different res-8 cell
C = (39.73500, -104.95300)
D = (39.74710, -104.99480)
HOME = (39.60000, -104.80000)
OUTSIDE = (39.19, -106.82)

DAY = datetime(2026, 9, 1, tzinfo=UTC)

assert h3.latlng_to_cell(*A, 8) != h3.latlng_to_cell(*B, 8)


def _cell(pt: tuple[float, float]) -> str:
    return h3.latlng_to_cell(pt[0], pt[1], 8)


def _at(h: int, m: int, s: int = 0, day: datetime = DAY) -> datetime:
    return day.replace(hour=h, minute=m, second=s)


def _seq(start: datetime, end: datetime, step: int = 30) -> list[datetime]:
    out = []
    t = start
    while t <= end:
        out.append(t)
        t += timedelta(seconds=step)
    return out


def _ping_row(t: datetime, lat: float, lng: float, online: bool = True) -> str:
    return (
        f"driver_app,denver,Test Carrier,311,480,10.0.0.1,en,sm-test,android,16,"
        f"{'true' if online else 'false'},,4.593.10000,{t:%Y-%m-%d %H:%M:%S}.000,"
        f"{lat:.5f},{lng:.5f},0.0,custom"
    )


def _fixture_pings() -> list[tuple[datetime, tuple[float, float], bool]]:
    rows: list[tuple[datetime, tuple[float, float], bool]] = []
    for t in _seq(_at(13, 0), _at(13, 39, 30)):
        rows.append((t, B if t == _at(13, 30, 30) else A, True))
    for t in _seq(_at(13, 40), _at(14, 0)):
        rows.append((t, C, True))
    # One continuous stream 14:20→15:45 (no real gap): trip1's request/enroute and
    # trip2's queued request/ontrip carve "busy" out of it, not a ping gap.
    for t in _seq(_at(14, 20), _at(15, 45)):
        rows.append((t, C if t <= _at(14, 39, 30) else D, True))
    for t in _seq(_at(16, 0), _at(16, 10)):
        rows.append((t, D, False))
    for t in _seq(_at(17, 0), _at(17, 30)):
        rows.append((t, HOME, True))
    return rows


def _analytics_text(
    rows: list[tuple[datetime, tuple[float, float], bool]], bad: bool = False
) -> str:
    lines = [ANALYTICS_HEADER]
    lines += [_ping_row(t, pos[0], pos[1], online) for t, pos, online in rows]
    if bad:
        lines.append(
            "driver_app,denver,Test Carrier,311,480,10.0.0.1,en,sm-test,android,16,"
            "true,,4.593.10000,not-a-timestamp,39.7,-104.9,0.0,custom"
        )
    return "\n".join(lines) + "\n"


def _trip_row(
    product: str,
    request_at: datetime,
    begin_at: datetime | None,
    dropoff_at: datetime | None,
    status: str = "completed",
) -> str:
    header = TRIPS_2025_HEADER.split(",")
    d = dict(zip(header, next(csv.reader([TRIPS_2025_ROW])), strict=True))
    d["product_type_name"] = product
    d["request_timestamp_utc"] = request_at.strftime("%Y-%m-%d %H:%M:%S")
    d["request_timestamp_local"] = ""
    d["begintrip_timestamp_utc"] = begin_at.strftime("%Y-%m-%d %H:%M:%S") if begin_at else ""
    d["begintrip_timestamp_local"] = ""
    d["dropoff_timestamp_utc"] = dropoff_at.strftime("%Y-%m-%d %H:%M:%S") if dropoff_at else ""
    d["dropoff_timestamp_local"] = ""
    d["status"] = status
    d["is_completed"] = "true" if status == "completed" else "false"
    out = io.StringIO()
    csv.writer(out).writerow(d[h] for h in header)
    return out.getvalue().rstrip("\r\n")


def _trips_text() -> str:
    rows = [
        _trip_row("UberBLACK", _at(14, 30), _at(14, 40), _at(15, 0)),
        _trip_row("UberSUV", _at(14, 50), _at(15, 5), _at(15, 20)),
        _trip_row("UberSUV", _at(15, 30), None, None, status="requester_canceled"),
        _trip_row(
            "uberX",
            datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
            datetime(2026, 8, 20, 12, 10, tzinfo=UTC),
            datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        ),
    ]
    return TRIPS_2025_HEADER + "\n" + "\n".join(rows) + "\n"


def _export_zip(
    pings: list[tuple[datetime, tuple[float, float], bool]], bad: bool = False
) -> bytes:
    return _zip({
        "driver_lifetime_trips-0.csv": _trips_text(),
        "Driver/driver_app_analytics-0.csv": _analytics_text(pings, bad=bad),
    })


def _owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200, r.text
    return c


def _dsn() -> str:
    return get_settings().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _rows(query: str, *args) -> list:
    async def _run():
        conn = await asyncpg.connect(_dsn())
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.close()

    return asyncio.run(_run())


def test_parse_zip_reads_analytics_member():
    good = _fixture_pings()
    p = ui.parse_zip(_export_zip(good, bad=True))
    assert "driver_app_analytics-0.csv" in p.files_found
    assert len(p.pings) == len(good)
    assert p.pings_skipped == 1
    assert p.skipped_rows == 0
    first = p.pings[0]
    assert first.at.tzinfo is not None and first.at == good[0][0]
    burst_16 = [pg for pg in p.pings if pg.at.hour == 16]
    assert burst_16 and all(pg.online is False for pg in burst_16)
    assert ui._parse_ts("2026-08-25 15:28:46.190", "UTC").microsecond == 190000


def test_segments_exact():
    p = ui.parse_zip(_export_zip(_fixture_pings()))
    segs = gps_import.segment_pings(p.pings, p.trips, home=(39.6, -104.8), home_radius_m=300)
    got = [
        (s.state, s.begin_at, s.end_at, s.h3_r8, s.zone_key)
        for s in sorted(segs, key=lambda s: s.begin_at)
    ]
    expected = [
        ("open", _at(13, 0), _at(13, 39, 30), _cell(A), None),
        ("open", _at(13, 40), _at(14, 0), _cell(C), None),
        ("open", _at(14, 20), _at(14, 29, 30), _cell(C), None),
        ("enroute", _at(14, 30), _at(14, 40), _cell(C), None),
        ("ontrip", _at(14, 40), _at(15, 0), _cell(D), None),
        ("ontrip", _at(15, 5), _at(15, 20), _cell(D), None),
        ("open", _at(15, 20, 30), _at(15, 29, 30), _cell(D), None),
        ("enroute", _at(15, 30), _at(15, 31), _cell(D), None),
        ("open", _at(15, 31, 30), _at(15, 45), _cell(D), None),
        ("open", _at(17, 0), _at(17, 30), _cell(HOME), "home"),
    ]
    assert got == expected
    assert len({s.dedup_key for s in segs}) == len(segs)
    segs2 = gps_import.segment_pings(p.pings, p.trips, home=(39.6, -104.8), home_radius_m=300)
    assert {s.dedup_key for s in segs} == {s.dedup_key for s in segs2}


def test_locate_and_request_cells():
    p = ui.parse_zip(_export_zip(_fixture_pings()))
    trip1, trip2, trip3, trip_aug = p.trips
    located = gps_import.locate_trips(p.pings, p.trips)
    assert located[trip1.dedup_key] == D
    assert located[trip2.dedup_key] == D
    assert trip3.dedup_key not in located
    assert trip_aug.dedup_key not in located

    cells = gps_import.request_cells(p.pings, p.trips)
    assert cells == [_cell(C), _cell(D)]


def test_top_waits_labels():
    p = ui.parse_zip(_export_zip(_fixture_pings()))
    segs = gps_import.segment_pings(p.pings, p.trips, home=(39.6, -104.8), home_radius_m=300)
    open_segs = [s for s in segs if s.state == "open" and s.zone_key != "home"]
    outside_seg = ui.ParsedSegment(
        dedup_key="synthetic-outside",
        state="open",
        begin_at=_at(18, 0),
        end_at=_at(18, 5),
        begin_lat=OUTSIDE[0],
        begin_lng=OUTSIDE[1],
        end_lat=OUTSIDE[0],
        end_lng=OUTSIDE[1],
        h3_r8=_cell(OUTSIDE),
        zone_key=None,
    )
    premium_cells = gps_import.request_cells(p.pings, p.trips)
    waits = gps_import.top_waits(
        open_segs + [outside_seg],
        premium_cells,
        places={"Clayton Hotel & Members Club": (39.7203, -104.9565)},
    )
    by_cell = {w["h3_r8"]: w for w in waits}

    assert waits[0]["h3_r8"] == _cell(A)
    assert waits[0]["hours"] == 0.7
    assert waits[0]["premium_requests"] == 0
    assert waits[0]["place"] == "Clayton Hotel & Members Club"
    assert waits[0]["distance_km"] < 2

    c_item = by_cell[_cell(C)]
    assert c_item["premium_requests"] == 1
    assert c_item["per_hour"] == 2.03

    out_item = by_cell[_cell(OUTSIDE)]
    assert out_item["outside"] is True
    assert out_item["place"] is None

    assert _cell(HOME) not in by_cell


def test_import_pings_replace_window_and_backfill():
    c = _owner()
    data = _export_zip(_fixture_pings())
    r = c.post("/api/v1/demand/import", files=[("file", ("uber.zip", data, "application/zip"))])
    assert r.status_code == 201, r.text
    gps = r.json()["gps"]
    assert gps["pings"] == len(_fixture_pings())
    assert gps["segments"] == {"open": 6, "enroute": 2, "ontrip": 2}
    assert gps["trips_located"] == 2
    assert gps["home_hours"] == 0.5
    assert gps["top_waits"][0]["h3_r8"] == _cell(A)

    tenant_id = _rows("SELECT tenant_id FROM demand_imports ORDER BY id DESC LIMIT 1")[0][
        "tenant_id"
    ]
    trip1_key = ui.parse_zip(data).trips[0].dedup_key
    trow = _rows(
        "SELECT begin_lat, begin_lng FROM uber_trips WHERE tenant_id = $1 AND dedup_key = $2",
        tenant_id,
        trip1_key,
    )
    assert trow[0]["begin_lat"] == pytest.approx(round(D[0], 5))
    assert trow[0]["begin_lng"] == pytest.approx(round(D[1], 5))

    def _gps_rows():
        return _rows(
            "SELECT dedup_key, begin_at, end_at FROM driver_state_segments "
            "WHERE tenant_id = $1 AND source = 'gps' ORDER BY begin_at",
            tenant_id,
        )

    first_rows = _gps_rows()
    assert len(first_rows) == 10

    r2 = c.post("/api/v1/demand/import", files=[("file", ("uber.zip", data, "application/zip"))])
    assert r2.status_code == 201
    second_rows = _gps_rows()
    assert len(second_rows) == len(first_rows)
    assert {row["dedup_key"] for row in second_rows} == {row["dedup_key"] for row in first_rows}

    overlap = (
        [(t, D, True) for t in _seq(_at(15, 35), _at(15, 45))]
        + [(t, HOME, True) for t in _seq(_at(17, 0), _at(17, 30))]
    )
    data2 = _zip({"driver_app_analytics-1.csv": _analytics_text(overlap)})
    r3 = c.post("/api/v1/demand/import", files=[("file", ("uber2.zip", data2, "application/zip"))])
    assert r3.status_code == 201, r3.text

    final_rows = _gps_rows()
    assert len(final_rows) == 11
    got = [(row["begin_at"], row["end_at"]) for row in final_rows]
    expected = [
        (_at(13, 0), _at(13, 39, 30)),
        (_at(13, 40), _at(14, 0)),
        (_at(14, 20), _at(14, 29, 30)),
        (_at(14, 30), _at(14, 40)),
        (_at(14, 40), _at(15, 0)),
        (_at(15, 5), _at(15, 20)),
        (_at(15, 20, 30), _at(15, 29, 30)),
        (_at(15, 30), _at(15, 31)),
        (_at(15, 31, 30), _at(15, 35)),
        (_at(15, 35), _at(15, 45)),
        (_at(17, 0), _at(17, 30)),
    ]
    assert got == expected


def test_analytics_privacy_and_size_cap(monkeypatch):
    c = _owner()
    data = _export_zip(_fixture_pings())
    r = c.post("/api/v1/demand/import", files=[("file", ("uber3.zip", data, "application/zip"))])
    assert r.status_code == 201, r.text
    assert "10.0.0.1" not in r.text and "sm-test" not in r.text

    tenant_id = _rows("SELECT tenant_id FROM demand_imports ORDER BY id DESC LIMIT 1")[0][
        "tenant_id"
    ]
    rows = _rows(
        "SELECT begin_lat, begin_lng, h3_r8, zone_key FROM driver_state_segments "
        "WHERE tenant_id = $1 AND source = 'gps'",
        tenant_id,
    )
    assert rows
    for row in rows:
        blob = str(dict(row))
        assert "10.0.0.1" not in blob and "sm-test" not in blob

    monkeypatch.setattr(ui, "MAX_MEMBER_BYTES", 10)
    parsed = ui.parse_zip(data)
    assert any(m["kind"] == "analytics_too_large" for m in parsed.files_missing)
    assert parsed.pings == []
    assert len(parsed.trips) == 4
