"""Paper pages and citation cards (spec §6.6): the full page, its title region, or a card drawn from metadata."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from ..evidence import locate
from ..fonts import font, has_cjk
from ..schema import Paper
from ..util import PvmError
from .assets import sheet
from .style import INK, MUTED, NAVY, OCHRE, SHEET
from .text import balanced_wrap, text_sprite, wrap

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels


@dataclass
class PageImage:
    image: Image.Image  # RGB render of one page
    scale: float  # pixels per PDF point
    index: int  # 0-based page number
    title_boxes: list[Box] = field(default_factory=list)
    highlight_boxes: dict[str, list[Box]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # highlight texts not found on the page


def _open(path: Path):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(path))
    except Exception as e:  # damaged or encrypted files
        raise PvmError(f"could not open {path}: {e}") from e


def _line_boxes(textpage, start: int, end: int, scale: float, page_h: float) -> list[Box]:
    """Character boxes of [start, end) merged into one box per text line."""
    lines: list[list[float]] = []
    for i in range(start, end):
        left, bottom, right, top = textpage.get_charbox(i)
        if right - left <= 0 or top - bottom <= 0:
            continue  # generated spaces and line breaks have no box
        x0, x1 = left * scale, right * scale
        y0, y1 = (page_h - top) * scale, (page_h - bottom) * scale
        mid = (y0 + y1) / 2
        if lines and abs(mid - lines[-1][4]) < max(y1 - y0, lines[-1][3] - lines[-1][1]) * 0.6:
            b = lines[-1]
            b[0], b[1], b[2], b[3] = min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)
        else:
            lines.append([x0, y0, x1, y1, mid])
    return [(b[0], b[1], b[2], b[3]) for b in lines]


def title_page_index(pdf, title: str, max_pages: int = 3) -> int:
    """The page that carries the title (skips journal cover sheets); the first page if not found."""
    words = " ".join(title.split()[:6])
    for i in range(min(max_pages, len(pdf))):
        page = pdf[i]
        textpage = page.get_textpage()
        try:
            if words and locate(textpage.get_text_range(), words):
                return i
        finally:
            textpage.close()
            page.close()
    return 0


def render_page(path: Path, width_px: int, *, page: int | None, title: str,
                highlights: list[str] = ()) -> PageImage:
    pdf = _open(path)
    try:
        index = page - 1 if page else title_page_index(pdf, title)
        if not 0 <= index < len(pdf):
            raise PvmError(f"{path.name} has {len(pdf)} pages; there is no page {index + 1}")
        pg = pdf[index]
        page_w, page_h = pg.get_size()
        scale = width_px / page_w
        out = PageImage(pg.render(scale=scale).to_pil().convert("RGB"), scale, index)
        textpage = pg.get_textpage()
        raw = textpage.get_text_range()
        span = (locate(raw, title) or locate(raw, " ".join(title.split()[:6]))) if title else None
        if span:
            out.title_boxes = _line_boxes(textpage, span[0], span[1], scale, page_h)
        for text in highlights:
            span = locate(raw, text)
            if span:
                out.highlight_boxes[text] = _line_boxes(textpage, span[0], span[1], scale, page_h)
            else:
                out.missing.append(text)
        textpage.close()
        pg.close()
        return out
    finally:
        pdf.close()


def render_pages(path: Path, width_px: int, first: int, last: int) -> list[Image.Image]:
    pdf = _open(path)
    try:
        last = min(last, len(pdf))
        pages = []
        for i in range(first - 1, last):
            pg = pdf[i]
            pages.append(pg.render(scale=width_px / pg.get_size()[0]).to_pil().convert("RGB"))
            pg.close()
        if not pages:
            raise PvmError(f"{path.name} has no pages {first}-{last}")
        return pages
    finally:
        pdf.close()


def title_region(page: PageImage) -> tuple[Image.Image, list[Box]]:
    """The top of the page down to just below the title block: journal header, title, authors."""
    h = page.image.height
    if page.title_boxes:
        bottom = max(b[3] for b in page.title_boxes)
        cut = min(max(bottom + 0.16 * h, 0.34 * h), 0.55 * h)
    else:
        cut = 0.36 * h
    return page.image.crop((0, 0, page.image.width, int(cut))), [b for b in page.title_boxes if b[3] <= cut]


def torn_bottom(img: Image.Image, depth: int, seed: int = 3) -> Image.Image:
    """RGBA copy of `img` whose bottom edge looks torn off (collage style)."""
    rng = random.Random(seed)
    w, h = img.size
    points, x = [(0, 0), (w, 0), (w, h - depth)], w
    while x > 0:
        x = max(0, x - rng.randint(max(3, depth), max(6, depth * 3)))
        points.append((x, h - rng.randint(0, depth)))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _authors(paper: Paper, n: int = 3) -> str:
    names = [a for a in paper.authors if a.strip()]
    text = ", ".join(names[:n])
    return text + (" et al." if len(names) > n else "")


def draw_citation(paper: Paper, width: int, s, *, label: str | None = None, compact: bool = False) -> Image.Image:
    """Citation card (RGBA), drawn entirely by code from the source metadata (spec §8.2)."""
    pad = s(30 if compact else 44)
    inner = width - 2 * pad
    serif_bold = "bold" if has_cjk(paper.title) else "serif_bold"
    parts: list[tuple[Image.Image, int]] = []

    if label:
        f = font("bold", s(34))
        parts.append((text_sprite([label], f, INK + (255,), align="left"), s(14)))
    if paper.venue and not compact:
        f = font("serif_bold", s(28))
        parts.append((text_sprite(wrap(paper.venue.upper(), f, inner)[:2], f, OCHRE + (255,), align="left"), s(18)))
    title_max, title_min, max_lines = (s(40), s(28), 3) if compact else (s(58), s(34), 4)
    size = title_max
    while True:
        f = font(serif_bold, size)
        lines = balanced_wrap(paper.title, f, inner)
        if len(lines) <= max_lines or size <= title_min:
            break
        size = max(title_min, int(size * 0.92))
    parts.append((text_sprite(lines[:max_lines], f, INK + (255,), align="left", line_spacing=1.15), s(16)))
    if not compact and paper.authors:
        f = font("serif", s(30))
        parts.append((text_sprite(wrap(_authors(paper), f, inner)[:2], f, MUTED + (255,), align="left"), s(10)))
    meta = [str(paper.year)] if paper.year else []
    if paper.volume:
        meta.append(paper.volume + (f"({paper.issue})" if paper.issue else ""))
    if paper.pages:
        meta.append(paper.pages)
    if compact and paper.venue:
        meta.insert(0, paper.venue)
    if meta:
        f = font("serif", s(28))
        parts.append((text_sprite([" · ".join(meta)], f, MUTED + (255,), align="left"), s(10)))
    if paper.doi:
        f = font("regular", s(26))
        parts.append((text_sprite([f"doi: {paper.doi}"], f, NAVY + (255,), align="left"), 0))

    height = 2 * pad + sum(sp.height + gap for sp, gap in parts)
    card = sheet((width, height), s(18), SHEET, border=(30, 30, 30, 60), border_width=max(1, s(2)))
    y = pad
    for sp, gap in parts:
        card.alpha_composite(sp, (pad, y))
        y += sp.height + gap
    return card
