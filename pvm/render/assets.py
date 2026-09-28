"""Drawing helpers shared by the scene renderers: paper texture, sheets, shadows, easing, sub-pixel zoom."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .style import IVORY, SHEET


def ease(x: float) -> float:
    """Smoothstep: 0 → 1 with gentle start and end."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ramp(t: float, start: float, duration: float) -> float:
    return ease((t - start) / duration) if duration > 0 else float(t >= start)


@lru_cache(maxsize=8)
def paper_texture(w: int, h: int, color: tuple[int, int, int] = IVORY, seed: int = 7) -> Image.Image:
    """Deterministic ivory paper: fine grain plus soft blotches and a faint vignette."""
    rng = np.random.default_rng(seed)
    grain = rng.normal(0.0, 2.6, (h, w))
    small = rng.normal(0.0, 1.0, (max(2, h // 90), max(2, w // 90)))
    blotch = np.asarray(Image.fromarray(small.astype(np.float32)).resize((w, h), Image.BICUBIC)) * 3.0
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    vignette = -6.0 * np.clip(r - 0.7, 0, None)
    base = np.array(color, dtype=np.float32)[None, None, :]
    img = base + (grain + blotch + vignette)[:, :, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def with_shadow(sprite: Image.Image, blur: int, offset: tuple[int, int], alpha: int) -> tuple[Image.Image, tuple[int, int]]:
    """Sprite on a larger transparent canvas with a soft drop shadow. Returns (image, top-left shift)."""
    pad = blur * 3 + max(abs(offset[0]), abs(offset[1]))
    w, h = sprite.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = sprite.getchannel("A").point(lambda v: v * alpha // 255)
    shadow.paste((40, 30, 20, 255), (pad + offset[0], pad + offset[1]), a)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(shadow)
    out.alpha_composite(sprite, (pad, pad))
    return out, (-pad, -pad)


def sheet(size: tuple[int, int], radius: int, color=SHEET, border: tuple[int, int, int, int] | None = None,
          border_width: int = 0) -> Image.Image:
    """A paper sheet: rounded rectangle with an optional thin border."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=color + (255,),
                        outline=border, width=border_width)
    return img


def cover_fit(img: Image.Image, size: tuple[int, int], focus_y: float = 0.5) -> Image.Image:
    """Scale to fill `size` and crop the overflow (centered horizontally, at focus_y vertically)."""
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))), Image.LANCZOS)
    x = (resized.width - w) // 2
    y = int((resized.height - h) * min(max(focus_y, 0.0), 1.0))
    return resized.crop((x, y, x + w, y + h))


def contain_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = min(size[0] / img.width, size[1] / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def zoom(img: Image.Image, z: float, cx: float, cy: float) -> Image.Image:
    """View of `img` magnified by z around source point (cx, cy), same output size, sub-pixel accurate.

    Resizing a fractional source box moves smoothly by fractions of a pixel; boxes rounded to whole pixels
    would make slow push-ins jitter (spec §10.4). It is also ~3x faster than an affine transform.
    """
    w, h = img.size
    if z <= 1.0 + 1e-6:
        return img
    half_w, half_h = w / (2 * z), h / (2 * z)
    cx = min(max(cx, half_w), w - half_w)
    cy = min(max(cy, half_h), h - half_h)
    return img.resize((w, h), Image.BICUBIC, box=(cx - half_w, cy - half_h, cx + half_w, cy + half_h))
