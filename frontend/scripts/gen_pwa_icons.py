"""Generate the PWA icon set for both apps (client + driver).

Mirrors scripts/gen_hero_webp.py: run once, commit the PNGs. Draws an on-brand
lightning bolt (Volt Electric #00E5FF on Void #0A0A0F) with Pillow — no design
tools, deterministic output.

    python scripts/gen_pwa_icons.py   # writes to frontend/public/icons/

Client = volt bolt on dark. Driver = inverted (dark bolt on volt) so the two home-
screen icons are instantly distinguishable. Maskable variants keep the bolt inside
the center safe-zone; the badge is a white bolt on transparent (Android status bar).
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

VOID = (10, 10, 15, 255)          # #0A0A0F
VOLT = (0, 229, 255, 255)         # #00E5FF
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "icons")

# Lightning-bolt polygon in a 0..1 unit square.
BOLT = [
    (0.56, 0.06), (0.30, 0.56), (0.48, 0.56),
    (0.42, 0.94), (0.72, 0.40), (0.53, 0.40),
]


def _draw_bolt(size: int, bg, fg, *, scale: float, rounded: bool) -> Image.Image:
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    d = ImageDraw.Draw(img)
    if bg is not None:
        if rounded:
            r = int(size * 0.22)
            d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=bg)
        else:
            d.rectangle([0, 0, size, size], fill=bg)
    # Center the bolt at `scale` of the canvas.
    span = size * scale
    off = (size - span) / 2
    pts = [(off + x * span, off + y * span) for (x, y) in BOLT]
    d.polygon(pts, fill=fg)
    return img


def _save(img: Image.Image, name: str) -> None:
    path = os.path.join(OUT, name)
    img.save(path, "PNG")
    print("wrote", os.path.relpath(path))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # Client (volt bolt on dark), full-bleed "any" + maskable.
    _save(_draw_bolt(192, VOID, VOLT, scale=0.62, rounded=True), "icon-192.png")
    _save(_draw_bolt(512, VOID, VOLT, scale=0.62, rounded=True), "icon-512.png")
    _save(_draw_bolt(512, VOID, VOLT, scale=0.50, rounded=False), "maskable-512.png")
    _save(_draw_bolt(180, VOID, VOLT, scale=0.66, rounded=False), "apple-touch-icon.png")

    # Driver (inverted: dark bolt on volt).
    _save(_draw_bolt(192, VOLT, VOID, scale=0.62, rounded=True), "driver-192.png")
    _save(_draw_bolt(512, VOLT, VOID, scale=0.62, rounded=True), "driver-512.png")
    _save(_draw_bolt(512, VOLT, VOID, scale=0.50, rounded=False), "driver-maskable-512.png")
    _save(_draw_bolt(180, VOLT, VOID, scale=0.66, rounded=False), "driver-apple-touch-icon.png")

    # Notification badge: white bolt on transparent (Android tints it).
    _save(_draw_bolt(72, None, WHITE, scale=0.72, rounded=False), "badge-72.png")


if __name__ == "__main__":
    main()
