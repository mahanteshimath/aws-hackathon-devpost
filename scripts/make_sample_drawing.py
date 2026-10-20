"""Create sample 'crayon drawings on paper' photos for tests and demos (no real child art needed)."""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def crayon_line(draw: ImageDraw.ImageDraw, pts, colour, width, rnd):
    for _ in range(3):  # several jittery passes look like crayon
        jitter = [(x + rnd.uniform(-2.5, 2.5), y + rnd.uniform(-2.5, 2.5)) for x, y in pts]
        draw.line(jitter, fill=colour, width=width, joint="curve")


def dino(path: Path, seed: int = 7) -> None:
    rnd = random.Random(seed)
    img = Image.new("RGB", (1200, 900), (246, 241, 230))
    noise = Image.effect_noise((1200, 900), 12).convert("RGB")
    img = Image.blend(img, noise, 0.06)
    d = ImageDraw.Draw(img)
    purple, green, orange, black = (128, 64, 190), (60, 170, 80), (250, 130, 40), (30, 30, 30)
    body = [(400 + 220 * math.cos(t / 20 * math.pi * 2), 520 + 140 * math.sin(t / 20 * math.pi * 2)) for t in range(21)]
    d.polygon(body, fill=(170, 120, 230))
    crayon_line(d, body, purple, 9, rnd)
    neck = [(560, 450), (640, 300), (700, 260), (780, 280), (770, 340), (690, 360), (640, 470)]
    d.polygon(neck, fill=(170, 120, 230))
    crayon_line(d, neck + [neck[0]], purple, 9, rnd)
    d.ellipse([720, 285, 745, 310], fill=black)
    for i in range(5):
        x = 260 + i * 70
        crayon_line(d, [(x, 400 - (i % 2) * 10), (x + 30, 330), (x + 60, 400)], orange, 8, rnd)
    for x in (300, 380, 470, 540):
        crayon_line(d, [(x, 640), (x, 760)], purple, 14, rnd)
    crayon_line(d, [(190, 520), (90, 600), (60, 560)], purple, 10, rnd)
    crayon_line(d, [(80, 820), (1120, 820)], green, 10, rnd)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=90)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/dino.jpg")
    dino(out)
    print(out)
