"""Text layout and sprites: CJK-aware wrapping, outlined text, auto-fitting."""
from __future__ import annotations

import re

from PIL import Image, ImageDraw, ImageFont

from ..fonts import font

NO_LINE_START = set("，。、；：！？）」』】》…,.;:!?)%”’")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-./:%]*[,.;:!?)]?\s*|\s+|.", re.S)


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Greedy wrap: breaks anywhere between CJK characters, never inside Latin words."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for tok in _TOKEN.findall(para):
            if not cur and tok.isspace():
                continue
            if fnt.getlength((cur + tok).rstrip()) <= max_width or not cur:
                cur += tok
            elif tok[0] in NO_LINE_START:
                cur += tok  # keep punctuation on the line it closes, even if slightly over
            else:
                lines.append(cur.rstrip())
                cur = tok.lstrip()
        if cur.strip() or not lines:
            lines.append(cur.rstrip())
    return lines


def balanced_wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Wrap into the minimum number of lines, then even out their lengths (avoids one-char widows)."""
    lines = wrap(text, fnt, max_width)
    if len(lines) < 2:
        return lines
    lo, hi = max_width * 0.5, max_width
    best = lines
    for _ in range(12):
        mid = (lo + hi) / 2
        trial = wrap(text, fnt, mid)
        if len(trial) <= len(lines):
            best, hi = trial, mid
        else:
            lo = mid
    return best


def text_sprite(lines: list[str], fnt: ImageFont.FreeTypeFont, fill, *, stroke_width: int = 0, stroke_fill=None,
                line_spacing: float = 1.12, align: str = "center", shadow: tuple | None = None) -> Image.Image:
    """Render lines to a tight RGBA sprite. shadow = (dx, dy, rgba)."""
    ascent, descent = fnt.getmetrics()
    line_h = (ascent + descent) * line_spacing
    widths = [fnt.getlength(l) for l in lines]
    sw = stroke_width
    sx, sy = (abs(shadow[0]), abs(shadow[1])) if shadow else (0, 0)
    w = int(max(widths or [1]) + 2 * sw + sx + 4)
    h = int(line_h * (len(lines) - 1) + ascent + descent + 2 * sw + sy + 4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        if align == "center":
            x = sw + 2 + (max(widths) - widths[i]) / 2
        elif align == "right":
            x = sw + 2 + max(widths) - widths[i]
        else:
            x = sw + 2
        y = sw + 2 + i * line_h
        if shadow:
            draw.text((x + shadow[0], y + shadow[1]), line, font=fnt, fill=shadow[2],
                      stroke_width=sw, stroke_fill=shadow[2])
        draw.text((x, y), line, font=fnt, fill=fill, stroke_width=sw, stroke_fill=stroke_fill)
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def fit_lines(lines: list[str], role: str, max_width: float, max_size: int, min_size: int,
              stroke_ratio: float = 0.0) -> tuple[ImageFont.FreeTypeFont, int]:
    """Largest font size (<= max_size) so every line fits max_width including the stroke."""
    size = max_size
    while size > min_size:
        f = font(role, size)
        sw = int(round(size * stroke_ratio))
        if max(f.getlength(l) for l in lines) + 2 * sw <= max_width:
            return f, sw
        size = int(size * 0.94)
    return font(role, min_size), int(round(min_size * stroke_ratio))


def paste_center(canvas: Image.Image, sprite: Image.Image, cx: float, cy: float, alpha: float = 1.0) -> None:
    x = int(round(cx - sprite.width / 2))
    y = int(round(cy - sprite.height / 2))
    paste_rgba(canvas, sprite, x, y, alpha)


def paste_rgba(canvas: Image.Image, sprite: Image.Image, x: int, y: int, alpha: float = 1.0) -> None:
    if alpha <= 0:
        return
    mask = sprite.getchannel("A")
    if alpha < 0.999:
        mask = mask.point(lambda v: int(v * alpha))
    canvas.paste(sprite, (x, y), mask)
