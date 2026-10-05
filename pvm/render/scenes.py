"""Scene renderers: each turns one storyboard scene plus its timing into frames of the 3:4 composition.

Every frame() returns a new image; overlays are drawn on it afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ..evidence import is_open
from ..fonts import font
from ..project import Project
from ..schema import Paper, PaperScene
from ..timeline import SceneTiming
from ..util import PvmError, warn
from .assets import contain_fit, cover_fit, ease, paper_texture, ramp, rounded_mask, sheet, with_shadow, zoom
from .paper import draw_citation, render_page, render_pages, title_region, torn_bottom
from .style import INK, IVORY, MARKER, MUTED, NAVY, OCHRE, SHEET, Layout
from .text import fit_lines, paste_rgba, text_sprite, wrap

MARGIN = 36
FOCUS_EASE = 0.4  # seconds for a panel to lift or settle
PANELS_BOTTOM = 0.816  # panels end at 81.6% of the height, above the subtitles (spec §10.6)


@dataclass
class Context:
    project: Project
    layout: Layout
    papers: dict[str, Paper]
    animatic: bool
    strict: bool = False
    warnings: list[str] = field(default_factory=list)
    visuals: dict[str, str] = field(default_factory=dict)  # scene id -> image file used
    displays: dict[str, str] = field(default_factory=dict)  # scene id -> page / title_crop / card / scroll

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
            warn(message)


def _shift(box, dx, dy):
    return box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy


def _center(boxes):
    return (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2, \
           (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2


class SceneRenderer:
    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        self.ctx, self.scene, self.timing = ctx, scene, timing
        self.L = ctx.layout
        self.s = ctx.layout.s
        self.W, self.H = ctx.layout.content_size

    def progress(self, t: float) -> float:
        span = max(0.01, self.timing.end - self.timing.start)
        return min(max((t - self.timing.start) / span, 0.0), 1.0)

    def background(self) -> Image.Image:
        return paper_texture(self.W, self.H).copy()

    def paste_sprite(self, base: Image.Image, sprite: Image.Image, xy: tuple[int, int], *, blur=10, drop=4,
                     alpha=90) -> None:
        shadowed, (dx, dy) = with_shadow(sprite, self.s(blur), (0, self.s(drop)), alpha)
        base.paste(shadowed, (xy[0] + dx, xy[1] + dy), shadowed)

    def title(self, base: Image.Image, text: str, cy: int, size: int = 84) -> int:
        """Poster title with the ochre underline bar (drawn by code). Returns the y below the bar."""
        f, _ = fit_lines([text], "black", self.W - 2 * self.s(80), self.s(size), self.s(40))
        sprite = text_sprite([text], f, INK + (255,))
        base.paste(sprite, ((self.W - sprite.width) // 2, cy - sprite.height // 2), sprite)
        bar_w, bar_h = int(sprite.width * 0.92), self.s(10)
        y = cy + sprite.height // 2 + self.s(16)
        ImageDraw.Draw(base).rounded_rectangle(((self.W - bar_w) // 2, y, (self.W + bar_w) // 2, y + bar_h),
                                               radius=bar_h // 2, fill=OCHRE)
        return y + bar_h

    def find_image(self, required: bool = True) -> Image.Image | None:
        sc, ctx = self.scene, self.ctx
        candidates = []
        if getattr(sc, "image", None):
            path = Path(sc.image)
            candidates.append(path if path.is_absolute() else ctx.project.dir / path)
        candidates.append(ctx.project.visuals_dir / f"{sc.id}.png")
        for path in candidates:
            if path.exists():
                ctx.visuals[sc.id] = str(path)
                return Image.open(path).convert("RGB")
        if required and not ctx.animatic:
            if ctx.strict:
                raise PvmError(f"{sc.id}: no image yet ({candidates[-1]}); generate it with  pvm images  or set "
                               "\"image\" in the storyboard")
            ctx.warn(f"{sc.id}: no image yet; rendering placeholders")
        return None

    def placeholder(self, size: tuple[int, int], brief: str, labels: list[str]) -> Image.Image:
        """Animatic stand-in for an illustration: the brief and the labels, so timing can be judged."""
        w, h = size
        img = Image.new("RGB", size, (236, 230, 218))
        d = ImageDraw.Draw(img)
        dash = self.s(14)
        for x in range(0, w, dash * 2):
            d.line((x, 1, x + dash, 1), fill=(200, 190, 172), width=max(1, self.s(2)))
            d.line((x, h - 2, x + dash, h - 2), fill=(200, 190, 172), width=max(1, self.s(2)))
        chips = [self.chip(label) for label in labels]
        if chips:
            gap = self.s(16)
            total = sum(c.width for c in chips) + gap * (len(chips) - 1)
            x, y = (w - total) // 2, int(h * 0.36) - chips[0].height // 2
            for c in chips:
                img.paste(c, (x, y), c)
                x += c.width + gap
        f = font("regular", self.s(26))
        lines = wrap(brief, f, w - 2 * self.s(60))[:3]
        if lines:
            sprite = text_sprite(lines, f, MUTED + (255,), line_spacing=1.2)
            img.paste(sprite, ((w - sprite.width) // 2, int(h * 0.68) - sprite.height // 2), sprite)
        return img

    def chip(self, label: str) -> Image.Image:
        f = font("bold", self.s(30))
        txt = text_sprite([label], f, INK + (255,))
        pad_x, pad_y = self.s(16), self.s(8)
        out = sheet((txt.width + 2 * pad_x, txt.height + 2 * pad_y), self.s(10), SHEET, border=(30, 30, 30, 90),
                    border_width=max(1, self.s(2)))
        out.alpha_composite(txt, (pad_x, pad_y))
        return out

    def frame(self, t: float) -> Image.Image:
        raise NotImplementedError


# ---------------------------------------------------------------- paper pages

class PaperRenderer(SceneRenderer):
    """The opening: page, title region or citation card per the license (spec §6.6), highlights, push-in."""

    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        super().__init__(ctx, scene, timing)
        sc = scene
        self.paper = ctx.papers.get(sc.paper)
        pdf = ctx.project.source_pdf(sc.paper)
        mode = "card"
        if sc.source != "card" and pdf.exists():
            mode = "page" if is_open(self.paper) or sc.rights == "permitted" else "title_crop"
        ctx.displays[sc.id] = mode
        self.base = self.background()
        self.title_boxes: list = []
        self.marks: list[tuple[float, list]] = []  # (start time, boxes) per highlight
        self.home = (self.W / 2, self.H * 0.4)
        texts = [h.text for h in sc.highlights]
        if mode == "card":
            self._card()
            if texts:
                ctx.warn(f"{sc.id}: highlights need the PDF page; the citation card is shown without them")
        else:
            m = self.s(MARGIN)
            page = render_page(pdf, self.W - 2 * m, page=sc.page, title=self.paper.title if self.paper else "",
                               highlights=texts)
            for text in page.missing:
                ctx.warn(f"{sc.id}: highlight '{text}' is not on page {page.index + 1} of {sc.paper}")
            (self._page if mode == "page" else self._title_crop)(page, m)
        self.stops = [(timing.start, self.home)] + sorted((t0, _center(b)) for t0, b in self.marks if b)

    def _page(self, page, m: int) -> None:
        img = page.image
        if img.height > self.H - m:  # the page runs off the bottom edge
            img = img.crop((0, 0, img.width, self.H - m))
        self.paste_sprite(self.base, img.convert("RGBA"), (m, m))
        self.title_boxes = [_shift(b, m, m) for b in page.title_boxes]
        for text, t0 in self.timing.highlights:
            boxes = [_shift(b, m, m) for b in page.highlight_boxes.get(text, []) if b[1] + m < self.H]
            if boxes:
                self.marks.append((t0, boxes))
        if self.title_boxes:
            self.home = _center(self.title_boxes)

    def _title_crop(self, page, m: int) -> None:
        crop, boxes = title_region(page)
        top = self.s(70)
        self.paste_sprite(self.base, torn_bottom(crop, self.s(14)), (m, top), alpha=110)
        self.title_boxes = [_shift(b, m, top) for b in boxes]
        if self.paper:
            inset = self.s(90)
            card = draw_citation(self.paper, self.W - 2 * inset, self.s)
            self.paste_sprite(self.base, card, (inset, top + crop.height + self.s(44)))
        for text, t0 in self.timing.highlights:
            inside = [b for b in page.highlight_boxes.get(text, []) if b[3] <= crop.height]
            if inside:
                self.marks.append((t0, [_shift(b, m, top) for b in inside]))
            elif text in page.highlight_boxes:
                self.ctx.warn(f"{self.scene.id}: highlight '{text}' is outside the title region shown for a paper "
                              "that is not openly licensed")
        self.home = _center(self.title_boxes) if self.title_boxes else (self.W / 2, top + crop.height / 2)

    def _card(self) -> None:
        if self.paper is None:
            raise PvmError(f"{self.scene.id}: source '{self.scene.paper}' has no metadata; run  pvm paper")
        inset = self.s(80)
        self.paste_sprite(self.base, draw_citation(self.paper, self.W - 2 * inset, self.s), (inset, int(self.H * 0.12)),
                          blur=12, drop=6, alpha=100)

    @staticmethod
    def _marker(img: Image.Image, boxes, p: float) -> None:
        """Highlighter sweep: multiply-blend yellow over the text, left to right, line by line."""
        remaining = sum(b[2] - b[0] for b in boxes) * p
        for x0, y0, x1, y1 in boxes:
            if remaining <= 0:
                break
            w = min(x1 - x0, remaining)
            remaining -= w
            pad = (y1 - y0) * 0.2
            box = (int(x0 - pad), int(y0 - pad * 0.5), int(x0 + w + pad), int(y1 + pad * 0.5))
            region = img.crop(box)
            img.paste(ImageChops.multiply(region, Image.new("RGB", region.size, MARKER)), box[:2])

    def _underline(self, img: Image.Image, p: float) -> None:
        d = ImageDraw.Draw(img)
        remaining = sum(b[2] - b[0] for b in self.title_boxes) * p
        thick = max(2, self.s(7))
        for x0, _, x1, y1 in self.title_boxes:
            if remaining <= 0:
                break
            w = min(x1 - x0, remaining)
            remaining -= w
            d.rectangle((x0, y1 + self.s(3), x0 + w, y1 + self.s(3) + thick), fill=OCHRE)

    def _focus(self, t: float) -> tuple[float, float]:
        cur = self.stops[0][1]
        for t0, point in self.stops[1:]:
            if t >= t0:
                k = ramp(t, t0, 0.9)
                cur = (cur[0] + (point[0] - cur[0]) * k, cur[1] + (point[1] - cur[1]) * k)
        return cur

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        tt = self.timing.title_highlight
        if tt is not None and self.title_boxes and t >= tt:
            self._underline(img, ramp(t, tt, 0.7))
        for t0, boxes in self.marks:
            if t >= t0:
                self._marker(img, boxes, ramp(t, t0, 0.45 + 0.15 * len(boxes)))
        z = 1 + (self.scene.zoom - 1) * ease(self.progress(t))
        return zoom(img, z, *self._focus(t))


class ScrollRenderer(SceneRenderer):
    """Pages scrolling past; only for openly licensed papers or with recorded permission (spec §6.6)."""

    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        super().__init__(ctx, scene, timing)
        sc = scene
        paper = ctx.papers.get(sc.paper)
        pdf = ctx.project.source_pdf(sc.paper)
        self.fallback = None
        if not pdf.exists() or not (is_open(paper) or sc.rights == "permitted"):
            ctx.warn(f"{sc.id}: scrolling through pages needs an openly licensed paper or rights: permitted; "
                     "showing the opening view instead")
            stand_in = PaperScene(id=sc.id, type="paper", sentences=sc.sentences, paper=sc.paper)
            self.fallback = PaperRenderer(ctx, stand_in, timing)
            return
        ctx.displays[sc.id] = "scroll"
        m, gap = self.s(MARGIN), self.s(28)
        pages = render_pages(pdf, self.W - 2 * m, *sc.pages)
        total = m + sum(p.height + gap for p in pages)
        self.tall = paper_texture(self.W, max(self.H, total)).copy()
        y = m
        for p in pages:
            self.paste_sprite(self.tall, p.convert("RGBA"), (m, y))
            y += p.height + gap
        self.max_offset = max(0, total - self.H)
        self.speed = sc.speed * self.L.scale

    def frame(self, t: float) -> Image.Image:
        if self.fallback:
            return self.fallback.frame(t)
        y = min(self.max_offset, max(0.0, t - self.timing.start - 1.0) * self.speed)
        return self.tall.resize((self.W, self.H), Image.BICUBIC, box=(0, y, self.W, y + self.H))


# ---------------------------------------------------------------- posters

def split_bands(img: Image.Image, n: int) -> list[tuple[int, int]]:
    """Row ranges of n stacked panels in a generated poster, cut at the empty gutters nearest to equal splits
    (spec §8.5). Falls back to equal splits where no gutter is found."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h = g.shape[0]
    background = float(np.median(np.concatenate([g[:, :6].ravel(), g[:, -6:].ravel()])))
    empty = (np.abs(g - background) > 18).mean(axis=1) < 0.01
    edges, window = [0], int(h * 0.12)
    for k in range(1, n):
        target = int(h * k / n)
        rows = [r for r in range(max(edges[-1] + 1, target - window), min(h - 1, target + window)) if empty[r]]
        if not rows:
            edges.append(target)
            continue
        r = min(rows, key=lambda row: abs(row - target))
        a, b = r, r
        while a > 0 and empty[a - 1]:
            a -= 1
        while b < h - 1 and empty[b + 1]:
            b += 1
        edges.append((a + b) // 2)
    edges.append(h)
    return [(edges[i], edges[i + 1]) for i in range(n)]


class PosterRenderer(SceneRenderer):
    """Title + numbered panel sheets (a collage), with the narrated panel lifted (spec §3.3, §8.5)."""

    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        super().__init__(ctx, scene, timing)
        self.base = self.background()
        top = self.header()
        n = len(scene.sections)
        gap, x0 = self.s(22), self.s(40)
        w = self.W - 2 * x0
        h = (int(self.H * PANELS_BOTTOM) - top - gap * (n - 1)) // n
        image = self.find_image()
        bands = split_bands(image, n) if image is not None else [None] * n
        self.sheets = []
        for i, sec in enumerate(scene.sections):
            y = top + i * (h + gap)
            art = image.crop((0, bands[i][0], image.width, bands[i][1])) if image is not None else None
            body = self.sheet_body(i, sec, (w, h), art)
            normal, (dx, dy) = with_shadow(body, self.s(8), (0, self.s(3)), 70)
            lifted, (lx, ly) = with_shadow(body, self.s(16), (0, self.s(9)), 115)
            self.sheets.append({"normal": normal, "pos": (x0 + dx, y + dy), "lifted": lifted, "lpos": (x0 + lx, y + ly),
                                "mask": rounded_mask((w, h), self.s(22)), "rect": (x0, y, w, h)})
        self.focus = [] if getattr(scene, "focus", "follow") == "none" else sorted(timing.focus, key=lambda f: f[1])

    def header(self) -> int:
        self.title(self.base, self.scene.title, self.s(118))
        return self.s(215)

    def sheet_body(self, i: int, sec, size: tuple[int, int], art: Image.Image | None) -> Image.Image:
        w, h = size
        body = sheet(size, self.s(22), SHEET, border=(30, 30, 30, 70), border_width=max(1, self.s(3)))
        inset = self.s(10)
        inner = (w - 2 * inset, h - 2 * inset)
        picture = cover_fit(art, inner) if art is not None else self.placeholder(inner, sec.visual, sec.labels)
        body.paste(picture, (inset, inset), rounded_mask(inner, self.s(14)))
        tag = self.heading_tag(i + 1, sec.heading)
        shadowed, (dx, dy) = with_shadow(tag, self.s(5), (0, self.s(2)), 80)
        body.alpha_composite(shadowed, (max(0, self.s(18) + dx), max(0, self.s(14) + dy)))
        return body

    def heading_tag(self, number: int, heading: str) -> Image.Image:
        """Numbered badge + heading on a paper pill, drawn by code (spec §8.2)."""
        d = self.s(56)
        badge = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(badge).ellipse((0, 0, d - 1, d - 1), fill=NAVY + (255,))
        num = text_sprite([str(number)], font("black", self.s(32)), (255, 255, 255, 255))
        badge.alpha_composite(num, ((d - num.width) // 2, (d - num.height) // 2))
        txt = text_sprite([heading], font("black", self.s(40)), INK + (255,))
        pad, space = self.s(9), self.s(14)
        h = max(d, txt.height) + 2 * pad
        tag = sheet((pad + d + space + txt.width + 2 * pad, h), h // 2, SHEET)
        tag.alpha_composite(badge, (pad, (h - d) // 2))
        tag.alpha_composite(txt, (pad + d + space, (h - txt.height) // 2))
        return tag

    def weights(self, t: float) -> tuple[list[float], float, float]:
        """Lift per panel (0..1), how far focus mode has faded in, and the y the view drifts toward."""
        n = len(self.sheets)
        lift = [0.0] * n
        started = [f for f in self.focus if f[1] <= t]
        mid = self.H / 2
        if not started:
            return lift, 0.0, mid
        i, t0 = started[-1]
        p = ramp(t, t0, FOCUS_EASE)
        lift[i] = p
        target = self.sheets[i]["rect"][1] + self.sheets[i]["rect"][3] / 2
        if len(started) > 1 and started[-2][0] != i:
            j = started[-2][0]
            lift[j] = max(lift[j], 1 - p)
            prev = self.sheets[j]["rect"][1] + self.sheets[j]["rect"][3] / 2
            target = prev + (target - prev) * p
        return lift, ramp(t, started[0][1], FOCUS_EASE), target

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        lift, focus_on, target_y = self.weights(t)
        for i in sorted(range(len(self.sheets)), key=lambda k: lift[k]):  # the lifted panel is drawn last, on top
            sh, w = self.sheets[i], lift[i]
            if w > 0.002:
                spr = sh["lifted"]
                k = 1 + 0.022 * ease(w)
                size = (round(spr.width * k), round(spr.height * k))
                big = spr.resize(size, Image.BICUBIC)
                x = sh["lpos"][0] - (size[0] - spr.width) / 2
                y = sh["lpos"][1] - (size[1] - spr.height) / 2
                img.paste(big, (round(x), round(y)), big)
            else:
                img.paste(sh["normal"], sh["pos"], sh["normal"])
            dim = 0.3 * focus_on * (1 - w)
            if dim > 0.01:
                x, y, _, _ = sh["rect"]
                img.paste(IVORY, (x, y), sh["mask"].point(lambda v: int(v * dim)))
        z = 1 + 0.03 * ease(self.progress(t))
        cy = self.H / 2 + (target_y - self.H / 2) * 0.35 * focus_on
        return zoom(img, z, self.W / 2, cy)


class SummaryRenderer(PosterRenderer):
    """Ending card: title, a citation block drawn by code from the metadata, then the takeaway panels."""

    def header(self) -> int:
        bottom = self.title(self.base, self.scene.title, self.s(96), size=72)
        paper = self.ctx.papers.get("src1") or next(iter(self.ctx.papers.values()), None)
        if paper is None:
            return bottom + self.s(40)
        x = self.s(40)
        card = draw_citation(paper, self.W - 2 * x, self.s, label=self.scene.label, compact=True)
        y = bottom + self.s(26)
        self.paste_sprite(self.base, card, (x, y), blur=8, drop=3, alpha=70)
        return y + card.height + self.s(26)


class ImageRenderer(SceneRenderer):
    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        super().__init__(ctx, scene, timing)
        self.base = self.background()
        top = self.header()
        x0 = self.s(40)
        size = (self.W - 2 * x0, int(self.H * PANELS_BOTTOM) - top)
        image = self.find_image()
        inset = self.s(10)
        inner = (size[0] - 2 * inset, size[1] - 2 * inset)
        body = sheet(size, self.s(22), SHEET, border=(30, 30, 30, 70), border_width=max(1, self.s(3)))
        picture = cover_fit(image, inner) if image is not None else self.placeholder(inner, scene.visual, [])
        body.paste(picture, (inset, inset), rounded_mask(inner, self.s(14)))
        self.paste_sprite(self.base, body, (x0, top), blur=8, drop=3, alpha=70)

    def header(self) -> int:
        return self.title(self.base, self.scene.title, self.s(118)) + self.s(30) if self.scene.title else self.s(60)

    def frame(self, t: float) -> Image.Image:
        return zoom(self.base.copy(), 1 + 0.04 * ease(self.progress(t)), self.W / 2, self.H * 0.45)


class TextRenderer(SceneRenderer):
    """Emphasis card: large lines, optionally with a mascot pose rising in below them."""

    def __init__(self, ctx: Context, scene, timing: SceneTiming):
        from ..mascot import pose_path  # local import: mascot -> images -> scenes

        super().__init__(ctx, scene, timing)
        self.plain = self.background()
        self.pose = None
        pose_file = pose_path(scene.pose) if scene.pose else None
        if pose_file is not None and not pose_file.exists():
            ctx.warn(f"{scene.id}: mascot pose '{scene.pose}' is not generated yet (pvm mascot); text only")
            pose_file = None
        f, _ = fit_lines(scene.lines, "black", self.W - 2 * self.s(90), self.s(96), self.s(40))
        sprite = text_sprite(scene.lines, f, INK + (255,), line_spacing=1.25)
        text_cy = int(self.H * (0.24 if pose_file else 0.42))
        self.base = self.plain.copy()
        self.base.paste(sprite, ((self.W - sprite.width) // 2, text_cy - sprite.height // 2), sprite)
        if pose_file is not None:
            self.pose = contain_fit(Image.open(pose_file).convert("RGBA"), (int(self.W * 0.62), int(self.H * 0.46)))
            self.pose_xy = ((self.W - self.pose.width) // 2, int(self.H * PANELS_BOTTOM) - self.pose.height)

    def frame(self, t: float) -> Image.Image:
        img = Image.blend(self.plain, self.base, ramp(t, self.timing.start, 0.3))
        if self.pose is not None:
            k = ramp(t, self.timing.start + 0.15, 0.45)
            if k > 0:
                x, y = self.pose_xy
                paste_rgba(img, self.pose, x, round(y + (1 - k) * self.s(24)), k)
        return zoom(img, 1 + 0.03 * ease(self.progress(t)), self.W / 2, self.H * 0.45)


def generation_box(ctx: Context, scene) -> tuple[int, int]:
    """Size of the area a generated image fills, so it can be requested at that aspect ratio (spec §8.4)."""
    cls = {"poster": PosterRenderer, "summary": SummaryRenderer, "image": ImageRenderer}[scene.type]
    probe = cls.__new__(cls)  # geometry only: no image lookup, no placeholders
    SceneRenderer.__init__(probe, ctx, scene, SceneTiming(scene.id, scene.type, 0.0, 1.0))
    probe.base = probe.background()
    top = probe.header()
    return probe.W - 2 * probe.s(40), int(probe.H * PANELS_BOTTOM) - top


RENDERERS = {"paper": PaperRenderer, "paper_scroll": ScrollRenderer, "poster": PosterRenderer,
             "summary": SummaryRenderer, "image": ImageRenderer, "text": TextRenderer}


def make_renderer(ctx: Context, scene, timing: SceneTiming) -> SceneRenderer:
    return RENDERERS[scene.type](ctx, scene, timing)
