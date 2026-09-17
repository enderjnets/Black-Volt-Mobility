"""BTS On-Time rows → typical DEN departures/arrivals per (month, dow, hour)."""
import pytest

from app.services import flights_baseline as fb


def _row(date: str, origin: str, dest: str, dep: str, arr: str) -> dict:
    return {
        "FlightDate": date,
        "Origin": origin,
        "Dest": dest,
        "CRSDepTime": dep,
        "CRSArrTime": arr,
    }


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
