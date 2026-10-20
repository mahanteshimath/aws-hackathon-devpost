"""Generate original brand art: Android launcher icons, Fire TV banner, and Appstore listing images."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "firetv-app" / "app" / "src" / "main" / "res"
FONT = ROOT / "web" / "shared" / "fonts" / "Fredoka.ttf"
PAPER, INK = (255, 246, 229), (42, 33, 64)
CRAYONS = [(255, 122, 61), (61, 139, 255), (53, 184, 106)]


def font(size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_axes([700, 100])  # weight, width -> bold
    except Exception:
        pass
    return f


def crayon(size: int, colour, angle: float) -> Image.Image:
    w, h = int(size * 0.22), int(size * 0.72)
    img = Image.new("RGBA", (w, h + w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, w * 0.9, w, h + w], radius=int(w * 0.25), fill=colour)
    d.polygon([(0, w), (w, w), (w / 2, 0)], fill=colour)
    d.rectangle([0, w * 1.6, w, w * 1.9], fill=(255, 255, 255, 120))
    return img.rotate(angle, expand=True, resample=Image.BICUBIC)


def icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=PAPER)
    for i, (colour, angle) in enumerate(zip(CRAYONS, (14, 0, -14))):
        c = crayon(size, colour, angle)
        img.alpha_composite(c, (int(size * (0.13 + i * 0.25)) - (c.width - int(size * 0.22)) // 2, int(size * 0.11)))
    return img


def banner(w: int, h: int, title_size: int) -> Image.Image:
    img = Image.new("RGBA", (w, h), PAPER + (255,))
    d = ImageDraw.Draw(img)
    # soft sunburst
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([w * 0.55, -h * 0.4, w * 1.3, h * 1.1], fill=(255, 201, 61, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(h * 0.12)))
    ic = icon(int(h * 0.56))
    img.alpha_composite(ic, (int(h * 0.1), (h - ic.height) // 2))
    f = font(title_size)
    x = int(h * 0.1) + ic.width + int(h * 0.07)
    d.text((x, h * 0.2), "Crayon", font=f, fill=INK)
    d.text((x, h * 0.2 + title_size * 1.0), "Cinema", font=f, fill=CRAYONS[0])
    return img


def main() -> None:
    for density, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        out = RES / f"mipmap-{density}" / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        icon(px).save(out)
    out = RES / "drawable-xhdpi" / "banner.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    banner(320, 180, 40).save(out)
    store = ROOT / "docs" / "store"
    store.mkdir(parents=True, exist_ok=True)
    icon(512).save(store / "icon-512.png")
    banner(1280, 720, 160).convert("RGB").save(store / "banner-1280x720.png")
    print("brand assets written")


if __name__ == "__main__":
    main()
