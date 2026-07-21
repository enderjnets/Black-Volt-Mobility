from PIL import Image
import os

REPO = "/Users/enderj/Black-Volt-Mobility"
BOLT = f"{REPO}/brand/black-volt-bolt-icon.png"
WORD = f"{REPO}/brand/black-volt-logo-official-dark.png"
OUT = f"{REPO}/mobile/assets"
os.makedirs(OUT, exist_ok=True)

VOID = (10, 10, 15, 255)  # #0A0A0F


def black_to_alpha(img):
    """Make near-black pixels transparent with a soft ramp (keeps antialiased edges)."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            mx = max(r, g, b)
            na = min(255, max(0, int((mx - 18) * 8)))
            px[x, y] = (r, g, b, min(a, na))
    return img


def crop_to_content(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def paste_centered(canvas_size, content, target_frac, bg=None):
    """Place `content` centered on a square canvas so its longest side = target_frac of canvas."""
    cv = Image.new("RGBA", (canvas_size, canvas_size), bg if bg else (0, 0, 0, 0))
    cw, ch = content.size
    scale = (canvas_size * target_frac) / max(cw, ch)
    nw, nh = int(cw * scale), int(ch * scale)
    c = content.resize((nw, nh), Image.LANCZOS)
    cv.alpha_composite(c, ((canvas_size - nw) // 2, (canvas_size - nh) // 2))
    return cv


# --- prep transparent, cropped source glyphs ---
bolt = crop_to_content(black_to_alpha(Image.open(BOLT)))
word = crop_to_content(black_to_alpha(Image.open(WORD)))

# 1) Adaptive icon foreground: bolt in the inner safe zone (~52% of frame)
paste_centered(1024, bolt, 0.52).save(f"{OUT}/icon-foreground.png")

# 2) Adaptive icon background: solid void
Image.new("RGBA", (1024, 1024), VOID).save(f"{OUT}/icon-background.png")

# 3) Legacy square icon: bolt on void (~46% so the round mask doesn't clip)
paste_centered(1024, bolt, 0.46, bg=VOID).save(f"{OUT}/icon-only.png")

# 4) Splash (light+dark same): wordmark centered on void, ~46% width
sp = paste_centered(2732, word, 0.46, bg=VOID)
sp.save(f"{OUT}/splash.png")
sp.save(f"{OUT}/splash-dark.png")

# 5) Bonus: 1200x630 OG social image (wordmark on void)
og = Image.new("RGBA", (1200, 630), VOID)
scale = (1200 * 0.5) / max(word.size)
nw, nh = int(word.size[0] * scale), int(word.size[1] * scale)
w2 = word.resize((nw, nh), Image.LANCZOS)
og.alpha_composite(w2, ((1200 - nw) // 2, (630 - nh) // 2))
og.convert("RGB").save(f"{REPO}/frontend/public/brand/og-image.png")

for f in sorted(os.listdir(OUT)):
    im = Image.open(f"{OUT}/{f}")
    print(f"  {f}: {im.size} {im.mode}")
print("  og-image.png:", Image.open(f"{REPO}/frontend/public/brand/og-image.png").size)
