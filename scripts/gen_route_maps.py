"""One-off: render a real, brand-dark route map per SEO route — no Google key needed.

The project's Google key only has Distance Matrix enabled (Static Maps / Directions are
off), so we build the maps ourselves from open data:
  - geocode endpoints via Nominatim (OpenStreetMap),
  - real driving geometry via OSRM (router.project-osrm.org),
  - basemap from OSM raster tiles, recolored to the Void-Black brand theme,
  - cyan route line + A/B pins drawn with Pillow.

Run once locally (needs internet + Pillow):

    python3 scripts/gen_route_maps.py

Output: frontend/public/assets/maps/<slug>.webp (committed static assets — zero runtime
cost, no API key). Re-run only when a route changes. Tile fetches are cached under
scripts/.maptiles/ and rate-limited to stay within OSM's casual-use policy.
"""
from __future__ import annotations

import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "assets" / "maps"
CACHE = ROOT / "scripts" / ".maptiles"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

UA = "BlackVoltMobility-mapgen/1.0 (enderjnets@gmail.com)"
CANVAS_W, CANVAS_H = 1200, 675          # 16:9
TILE = 256
VOLT = ImageColor.getrgb("#00E5FF")
VOID = ImageColor.getrgb("#0A0A0F")

# Explicit geocoder-friendly endpoint queries per route.
ROUTES = [
    ("aurora-to-den-airport", "Aurora, Colorado", "Denver International Airport, Colorado"),
    ("cherry-creek-to-den-airport", "Cherry Creek, Denver, Colorado", "Denver International Airport, Colorado"),
    ("dtc-corporate-airport-transfer", "Denver Tech Center, Greenwood Village, Colorado", "Denver International Airport, Colorado"),
    ("boulder-to-den-airport", "Boulder, Colorado", "Denver International Airport, Colorado"),
    ("red-rocks-concert-transportation", "Downtown Denver, Colorado", "Red Rocks Amphitheatre, Morrison, Colorado"),
    ("denver-to-vail-private-transfer", "Denver, Colorado", "Vail, Colorado"),
    ("denver-to-breckenridge-private-transfer", "Denver, Colorado", "Breckenridge, Colorado"),
    ("denver-to-aspen-private-transfer", "Denver, Colorado", "Aspen, Colorado"),
]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def geocode(q: str) -> tuple[float, float]:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "json", "q": q, "limit": 1}
    )
    import json

    data = json.loads(_get(url))
    if not data:
        raise RuntimeError(f"geocode failed: {q}")
    time.sleep(1.1)  # Nominatim: max 1 req/s
    return float(data[0]["lat"]), float(data[0]["lon"])


def osrm_route(a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    """Return [(lat, lon), ...] for the real driving route a->b (falls back to a straight line)."""
    import json

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{a[1]},{a[0]};{b[1]},{b[0]}?overview=full&geometries=geojson"
    )
    try:
        data = json.loads(_get(url))
        coords = data["routes"][0]["geometry"]["coordinates"]  # [lon, lat]
        return [(c[1], c[0]) for c in coords]
    except Exception as e:  # noqa: BLE001
        print(f"  osrm fallback (straight line): {e}")
        return [a, b]


# --- web mercator (global pixel space at zoom z) ---
def lonlat_to_px(lat: float, lon: float, z: float) -> tuple[float, float]:
    n = TILE * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def pick_zoom(min_lat, max_lat, min_lon, max_lon) -> int:
    for z in range(14, 5, -1):
        x0, y0 = lonlat_to_px(max_lat, min_lon, z)
        x1, y1 = lonlat_to_px(min_lat, max_lon, z)
        if (x1 - x0) <= CANVAS_W - 80 and (y1 - y0) <= CANVAS_H - 110:
            return z
    return 6


def tile_bytes(z: int, x: int, y: int) -> bytes:
    fp = CACHE / f"{z}_{x}_{y}.png"
    if fp.exists():
        return fp.read_bytes()
    data = _get(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    fp.write_bytes(data)
    time.sleep(0.12)
    return data


def brand_basemap(base: Image.Image) -> Image.Image:
    """Recolor an OSM basemap into a Void-Black monochrome look."""
    gray = ImageOps.grayscale(base)
    # map shadows->near-void, mids->slate, highlights->cool gray
    tinted = ImageOps.colorize(gray, black="#08080d", mid="#23232f", white="#5a5a6e")
    return tinted.convert("RGBA")


def build(slug: str, qa: str, qb: str) -> None:
    a = geocode(qa)
    b = geocode(qb)
    pts = osrm_route(a, b)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    z = pick_zoom(min(lats), max(lats), min(lons), max(lons))

    cx = sum(lonlat_to_px(p[0], p[1], z)[0] for p in (a, b)) / 2
    cy = sum(lonlat_to_px(p[0], p[1], z)[1] for p in (a, b)) / 2
    # bias center toward the route centroid for nicer framing
    rcx = sum(lonlat_to_px(la, lo, z)[0] for la, lo in pts) / len(pts)
    rcy = sum(lonlat_to_px(la, lo, z)[1] for la, lo in pts) / len(pts)
    cx, cy = (cx + rcx) / 2, (cy + rcy) / 2

    left = cx - CANVAS_W / 2
    top = cy - CANVAS_H / 2
    tx0, ty0 = int(left // TILE), int(top // TILE)
    tx1 = int((left + CANVAS_W) // TILE)
    ty1 = int((top + CANVAS_H) // TILE)

    stitched = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), VOID)
    import io

    n_tiles = 2 ** z
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            if not (0 <= ty < n_tiles):
                continue
            png = tile_bytes(z, tx % n_tiles, ty % n_tiles)
            tile = Image.open(io.BytesIO(png)).convert("RGB")
            stitched.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))

    canvas = brand_basemap(stitched)
    ox, oy = tx0 * TILE, ty0 * TILE  # stitched origin in global px

    def to_canvas(la: float, lo: float) -> tuple[float, float]:
        gx, gy = lonlat_to_px(la, lo, z)
        return gx - ox - (left - ox), gy - oy - (top - oy)

    line = [to_canvas(la, lo) for la, lo in pts]
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.line(line, fill=(0, 229, 255, 70), width=14, joint="curve")   # glow
    draw.line(line, fill=(*VOLT, 255), width=5, joint="curve")          # route

    def pin(pt, fill, ring):
        x, y = pt
        r = 11
        draw.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=(*VOID, 230))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=ring)
        draw.ellipse([x - r + 4, y - r + 4, x + r - 4, y + r - 4], fill=fill)

    pin(to_canvas(*a), fill=(*VOID, 255), ring=(*VOLT, 255))   # origin: cyan ring
    pin(to_canvas(*b), fill=(*VOLT, 255), ring=(255, 255, 255, 255))  # dest: white ring

    out = OUT / f"{slug}.webp"
    canvas.convert("RGB").save(out, "WEBP", quality=80, method=6)
    print(f"  {slug}: z={z}, {len(pts)} pts, {out.stat().st_size // 1024} KB")


def main() -> None:
    for slug, qa, qb in ROUTES:
        print(slug)
        build(slug, qa, qb)
    print("done")


if __name__ == "__main__":
    main()
