"""Image work that runs locally (Pillow): photo cleanup, paper keying, sticker outline, crayon palette.

Stability AI models on Bedrock do the heavy lifting in AWS mode; these helpers prepare their inputs, validate their
outputs, and provide a deterministic fallback so a child's drawing is never lost.
"""

from __future__ import annotations

import io
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

MAX_SIDE = 1024
MIN_SIDE = 320


def load_photo(data: bytes) -> Image.Image:
    """Decode a phone photo, honour EXIF rotation, and fit it to image-model size limits."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    if min(img.size) < MIN_SIDE:
        scale = MIN_SIDE / min(img.size)
        img = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.LANCZOS)
    return img


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def to_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def paper_key(photo: Image.Image) -> Image.Image:
    """Make paper transparent: pixels close to the estimated paper colour become clear.

    Works well for crayon/marker on white or cream paper, where generic subject segmentation can drop
    thin strokes.
    """
    rgb = photo.convert("RGB")
    w, h = rgb.size
    # Paper colour = median of a border band (drawings rarely touch every edge).
    band = max(4, min(w, h) // 25)
    border = []
    px = rgb.load()
    step = max(1, (w + h) // 400)
    for x in range(0, w, step):
        for y in list(range(0, band, 2)) + list(range(h - band, h, 2)):
            border.append(px[x, y])
    for y in range(0, h, step):
        for x in list(range(0, band, 2)) + list(range(w - band, w, 2)):
            border.append(px[x, y])
    paper = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))

    # Distance from paper colour, boosted by saturation so pale crayon still registers.
    paper_img = Image.new("RGB", rgb.size, paper)
    diff = ImageChops.difference(rgb, paper_img).convert("L")
    sat = rgb.convert("HSV").split()[1]
    signal = ImageChops.add(diff, sat.point(lambda v: v // 2))
    signal = signal.filter(ImageFilter.GaussianBlur(1.2))
    alpha = signal.point(lambda v: 0 if v < 28 else 255 if v > 70 else int((v - 28) * 255 / 42))
    # Close small gaps in strokes, then drop speckles.
    alpha = alpha.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def coverage(rgba: Image.Image) -> float:
    alpha = rgba.getchannel("A")
    hist = alpha.histogram()
    opaque = sum(hist[64:])
    return opaque / float(rgba.width * rgba.height)


def is_plausible_cutout(rgba: Image.Image) -> bool:
    """Reject segmentations that kept the whole page or lost almost everything."""
    c = coverage(rgba)
    return 0.01 <= c <= 0.85


def sticker(rgba: Image.Image, outline: int = 10, pad: int = 24) -> Image.Image:
    """Crop to the drawing and add a white 'sticker' border - reads well from 10 feet and hides rough edges."""
    alpha = rgba.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    bbox = alpha.getbbox()
    if not bbox:
        return rgba
    left, top, right, bottom = bbox
    margin = outline + pad
    crop_box = (max(0, left - margin), max(0, top - margin), min(rgba.width, right + margin), min(rgba.height, bottom + margin))
    art = rgba.crop(crop_box)
    canvas = Image.new("RGBA", (art.width + margin * 2, art.height + margin * 2), (0, 0, 0, 0))
    canvas.alpha_composite(art, (margin, margin))
    a = canvas.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    size = outline * 2 + 1
    grown = a.filter(ImageFilter.MaxFilter(size if size % 2 else size + 1)).filter(ImageFilter.GaussianBlur(1.5))
    border = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    border.putalpha(grown)
    border.alpha_composite(canvas)
    border.thumbnail((900, 900), Image.LANCZOS)
    return border


def palette(rgba: Image.Image, count: int = 4) -> list[str]:
    """Dominant crayon colours of the cut-out (ignoring outline white and near-black ink)."""
    small = rgba.copy()
    small.thumbnail((160, 160))
    flat = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    pixels = [p[:3] for p in flat if p[3] > 200]
    pixels = [p for p in pixels if not (min(p) > 225) and not (max(p) < 40)]
    if len(pixels) < 20:
        return ["#FF8A3D", "#4C9AFF", "#7BD389", "#FFD166"][:count]
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quant = strip.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette()[: 8 * 3]
    counts = sorted(quant.getcolors(), reverse=True)
    colours: list[str] = []
    for _, idx in counts:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        hexc = f"#{r:02X}{g:02X}{b:02X}"
        if all(_distance(hexc, c) > 60 for c in colours):
            colours.append(hexc)
        if len(colours) == count:
            break
    return colours or ["#FF8A3D"]


_NAMED = {
    "red": "#E53935", "crimson": "#B0183D", "pink": "#F48FB1", "magenta": "#D81B9A", "orange": "#FB8C00",
    "peach": "#FFBE98", "yellow": "#FDD835", "gold": "#E6B422", "lime green": "#9CCC3C", "green": "#43A047",
    "forest green": "#2E5E2E", "teal": "#00897B", "turquoise": "#3FD0D4", "sky blue": "#64B5F6", "blue": "#1E63D6",
    "navy blue": "#1A237E", "lavender": "#B39DDB", "purple": "#8E44C8", "violet": "#5E2A8C", "brown": "#7B4A2A",
    "tan": "#C8A070", "grey": "#8C8C8C", "cream": "#FFF4DC",
}


def colour_names(colours: list[str]) -> list[str]:
    """Nearest friendly colour name for each hex colour (image models follow words better than hex codes)."""
    names: list[str] = []
    for c in colours:
        name = min(_NAMED, key=lambda n: _distance(c, _NAMED[n]))
        if name not in names:
            names.append(name)
    return names


def _distance(a: str, b: str) -> float:
    ra, ga, ba = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    rb, gb, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def mock_scene(colours: list[str], seed: int, bedtime: bool, width: int = 1280, height: int = 720) -> Image.Image:
    """A soft, picture-book-ish placeholder background for mock mode (no AWS)."""
    rnd = random.Random(seed)
    if bedtime:
        top, bottom = (24, 30, 74), (88, 70, 140)
    else:
        top, bottom = (126, 200, 255), (255, 236, 200)
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        draw.line([(0, y), (width, y)], fill=_mix(top, bottom, y / height))
    if bedtime:
        for _ in range(70):
            x, y, r = rnd.randint(0, width), rnd.randint(0, height // 2), rnd.choice([1, 1, 2, 3])
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 220))
        draw.ellipse([width - 300, 60, width - 180, 180], fill=(255, 246, 200))
    else:
        draw.ellipse([width - 260, 50, width - 130, 180], fill=(255, 221, 120))
        for _ in range(4):
            cx, cy = rnd.randint(80, width - 80), rnd.randint(60, 220)
            for dx in (-50, 0, 50):
                draw.ellipse([cx + dx - 60, cy - 30, cx + dx + 60, cy + 30], fill=(255, 255, 255))
    hill_colours = [_hex(c) for c in (colours or ["#7BD389"])] + [(120, 190, 120)]
    for i in range(3):
        base = height - 200 + i * 60
        colour = _mix(hill_colours[i % len(hill_colours)], (40, 40, 80) if bedtime else (255, 255, 255), 0.35 + 0.15 * i)
        points = [(0, height)]
        phase = rnd.random() * math.pi * 2
        for x in range(0, width + 40, 40):
            points.append((x, base + int(40 * math.sin(x / 180 + phase))))
        points.append((width, height))
        draw.polygon(points, fill=colour)
    return img.filter(ImageFilter.GaussianBlur(0.8))
