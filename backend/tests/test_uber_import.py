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
