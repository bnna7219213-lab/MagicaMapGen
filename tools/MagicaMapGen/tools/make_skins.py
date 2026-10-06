"""Procedural dark-fantasy nine-patch frame generator.

The frames are drawn rather than downloaded. Three reasons, in order of importance:
licence risk is zero (authored here, so effectively CC0); the palette is generated
from the same constants as the QSS theme, so the frame and the stylesheet cannot drift
apart; and the source is vector maths, so any corner size stays crisp instead of being
resampled from a fixed bitmap.

Run:  python tools/make_skins.py
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from app import theme  # noqa: E402

OUT = HERE / "assets" / "skins"


def _rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def make_frame(panel: int = 96, corner: int = 24, ornate: bool = True,
               accent: str = None, filename: str = "frame_dark.png") -> Path:
    """Render one nine-patch frame.

    ``corner`` is both the nine-patch slice and the ornament extent, so ornaments sit
    in the slice and are never stretched when the panel is resized. All ornament
    geometry is anchored to the *band* (the few pixels just outside the panel body);
    anchoring it to the image corner instead leaves rivets floating in transparent
    space, which is what the first attempt did.
    """
    accent = accent or theme.EMBER
    size = panel + corner * 2
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    bronze = _rgb(theme.BORDER_LIT)
    bronze_dark = _rgb(theme.BORDER)
    deep = _rgb("#0b0908")
    ember = _rgb(accent)
    band = 3

    # Panel body: vertical gradient with rounded inner corners.
    body = Image.new("RGBA", (panel, panel), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    for y in range(panel):
        t = y / max(1, panel - 1)
        bd.line([(0, y), (panel, y)],
                fill=lerp(_rgb(theme.BG_PANEL), _rgb(theme.BG_DEEP), t * 0.9) + (255,))
    inner_radius = max(3, corner // 3)
    mask = Image.new("L", (panel, panel), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, panel - 1, panel - 1], radius=inner_radius, fill=255)
    body.putalpha(mask)
    img.alpha_composite(body, (corner, corner))

    # Band: outer dark line, bronze, inner dark line. Drawn as three rounded rects so
    # the corners read as one continuous piece of metal.
    d.rounded_rectangle([corner - band, corner - band,
                         corner + panel + band - 1, corner + panel + band - 1],
                        radius=max(4, corner // 2), outline=deep + (255,), width=1)
    d.rounded_rectangle([corner - band + 1, corner - band + 1,
                         corner + panel + band - 2, corner + panel + band - 2],
                        radius=max(3, corner // 2), outline=bronze + (255,), width=2)
    d.rounded_rectangle([corner - 1, corner - 1,
                         corner + panel, corner + panel],
                        radius=inner_radius, outline=bronze_dark + (255,), width=1)

    if ornate:
        # Corner brackets anchored on the band: an L of bronze with an ember rivet at
        # the elbow and a short tapered tail along each arm.
        arm = max(8, corner - band)
        r = max(2, corner // 8)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            # Elbow sits on the band's inner corner, mirrored per quadrant.
            ex = corner - band if sx > 0 else corner + panel - 1 + band
            ey = corner - band if sy > 0 else corner + panel - 1 + band
            tx = ex + sx * arm
            ty = ey + sy * arm
            d.line([(ex, ey), (tx, ey)], fill=bronze + (255,), width=2)
            d.line([(ex, ey), (ex, ty)], fill=bronze + (255,), width=2)
            d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=bronze + (255,),
                      outline=deep + (255,), width=1)
            d.ellipse([ex - max(1, r // 2), ey - max(1, r // 2),
                       ex + max(1, r // 2), ey + max(1, r // 2)],
                      fill=ember + (220,))

        # Rune ticks along the mid-edges, skipping the corner zones.
        tick = max(6, corner // 3)
        for i in range(corner + tick, panel - tick, tick):
            d.line([(corner + i, corner - band), (corner + i, corner - band - 2)],
                   fill=bronze + (120,))
            d.line([(corner + i, corner + panel + band - 1),
                    (corner + i, corner + panel + band + 1)], fill=bronze + (120,))
            d.line([(corner - band, corner + i), (corner - band - 2, corner + i)],
                   fill=bronze + (120,))
            d.line([(corner + panel + band - 1, corner + i),
                    (corner + panel + band + 1, corner + i)], fill=bronze + (120,))

    # Patina: a few soft dark blooms so the metal is not perfectly uniform.
    patina = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(patina)
    for i in range(6):
        cx = corner + int((panel - 1) * (0.15 + 0.7 * ((i * 37 % 100) / 100.0)))
        cy = corner + int((panel - 1) * (0.15 + 0.7 * ((i * 61 % 100) / 100.0)))
        rr = 10 + (i * 7) % 18
        pd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(0, 0, 0, 26))
    patina = patina.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(patina)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path)
    return path


def make_header(filename: str = "header_dark.png", width: int = 480, height: int = 44) -> Path:
    """A title-bar strip: a bronze underline with a faint rune-like gradient."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        base = lerp(_rgb(theme.BG_PANEL), _rgb(theme.BG_DEEP), t)
        d.line([(0, y), (width, y)], fill=base + (255,))
    bronze = _rgb(theme.BORDER_LIT)
    d.line([(0, height - 2), (width, height - 2)], fill=bronze + (255,))
    d.line([(0, height - 1), (width, height - 1)], fill=_rgb(theme.EMBER) + (140,))
    # Subtle vertical tick marks, like a ruler, to read as crafted rather than drawn.
    for x in range(6, width - 6, 24):
        d.line([(x, height - 6), (x, height - 3)], fill=bronze + (70,))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path)
    return path


def main() -> int:
    made = [
        make_frame(panel=96, corner=18, ornate=True, filename="frame_dark.png"),
        make_frame(panel=64, corner=14, ornate=True, filename="frame_dark_small.png"),
        make_frame(panel=96, corner=18, ornate=False, filename="frame_plain.png"),
        make_header(),
    ]
    for p in made:
        print("wrote %s (%d bytes)" % (p.name, p.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
