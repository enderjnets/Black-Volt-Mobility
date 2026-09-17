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
