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
