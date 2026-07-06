#!/usr/bin/env python3
"""Pre-generate WebP variants for the hero JPEGs in public/assets.

For each source JPEG this writes, next to it:
  <name>.webp        full resolution, quality 75  (desktop / retina)
  <name>-800w.webp   800px wide,      quality 80  (mobile srcset entry)

The originals are KEPT: they remain the OpenGraph images (widest social-scraper
compatibility); only the visible <img> tags use the WebP files (see
lib/seoRoutes.ts heroImgSources). Build-time generation keeps runtime free of an
image optimizer (the VPS has 2 vCPUs) — re-run this after adding/replacing a hero:

    python3 scripts/gen_hero_webp.py

CACHE WARNING: /assets/* ships with Cache-Control max-age=2592000 (30 days, see
next.config.js). If you REPLACE an image, give it a NEW filename (and update
HERO_WEBP_STEMS in lib/seoRoutes.ts) — overwriting the same name serves the stale
cached copy for up to a month unless you also purge Cloudflare.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "public" / "assets"
SOURCES = ["ev9-coors-field.jpg", "ev9-charging.jpg"]


def main() -> None:
    for name in SOURCES:
        src = ASSETS / name
        stem = src.with_suffix("")
        im = Image.open(src).convert("RGB")
        im.save(f"{stem}.webp", "WEBP", quality=75, method=6)
        w800 = im.resize((800, round(im.height * 800 / im.width)), Image.LANCZOS)
        w800.save(f"{stem}-800w.webp", "WEBP", quality=80, method=6)
        for out in (Path(f"{stem}.webp"), Path(f"{stem}-800w.webp")):
            print(f"{out.name}: {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
