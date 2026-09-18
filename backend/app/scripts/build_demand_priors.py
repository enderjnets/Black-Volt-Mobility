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
