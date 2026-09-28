"""Overlays drawn over every frame, all by code (spec §8.2): hook, subtitles, source chip, AI label, watermark."""
from __future__ import annotations

from bisect import bisect_right

from PIL import Image, ImageDraw

from ..config import get_settings
from ..fonts import font
from ..schema import Paper, Storyboard
from ..timeline import Timeline
from .assets import ramp
from .scenes import Context
from .style import HOOK_YELLOW, INK, MUTED
from .text import balanced_wrap, fit_lines, paste_center, paste_rgba, text_sprite

HOOK_IN, HOOK_OUT, CHIP_FADE = 0.22, 0.2, 0.25


def _pill(text: str, fnt, fill, background, pad_x: int, pad_y: int) -> Image.Image:
    txt = text_sprite([text], fnt, fill)
    w, h = txt.width + 2 * pad_x, txt.height + 2 * pad_y
    pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=background)
    pill.alpha_composite(txt, (pad_x, pad_y))
    return pill


def chip_text(paper: Paper) -> str:
    venue = (paper.venue or "").strip()
    return f"文献 · {paper.short_ref()}" + (f" · {venue}" if venue and len(venue) <= 36 else "")


class Overlays:
    def __init__(self, ctx: Context, sb: Storyboard, tl: Timeline):
        L, s = ctx.layout, ctx.layout.s
        self.L, self.s = L, s
        x, y, w, h = L.content

        f, sw = fit_lines(sb.hook, "black", w * 0.86, s(220), s(80), stroke_ratio=0.12)
        self.hook = text_sprite(sb.hook, f, HOOK_YELLOW + (255,), stroke_width=sw, stroke_fill=(0, 0, 0, 255),
                                line_spacing=1.06, shadow=(0, s(8), (0, 0, 0, 120)))
        self.hook_center = (x + w / 2, y + h * 0.42)
        self.hook_span = tl.hook

        self.cues = tl.cues
        self.cue_starts = [c.start for c in tl.cues]
        self.sub_font = font("black", s(64))
        self.sub_stroke = s(6)
        self._subs: dict[str, Image.Image] = {}

        self.facts = tl.facts
        self.showing_paper = {sc.id: sc.paper for sc in sb.scenes if sc.type in ("paper", "paper_scroll")}
        chip_font = font("bold", s(24))
        self.chips = {sid: _pill(chip_text(p), chip_font, (255, 255, 255, 255), INK + (215,), s(16), s(8))
                      for sid, p in ctx.papers.items()}

        label = get_settings().ai_label
        self.ai = (_pill(label, font("regular", s(24)), (255, 255, 255, 235), (0, 0, 0, 110), s(14), s(7))
                   if label and label.lower() != "none" else None)
        self.watermark = (text_sprite(["预览 · ANIMATIC"], font("bold", s(26)), MUTED + (200,))
                          if ctx.animatic else None)

    def subtitle(self, text: str) -> Image.Image:
        if text not in self._subs:
            max_w = self.L.subtitle_max_w - 2 * self.sub_stroke
            lines = [text] if self.sub_font.getlength(text) <= max_w else balanced_wrap(text, self.sub_font, max_w)
            self._subs[text] = text_sprite(lines, self.sub_font, (255, 255, 255, 255), stroke_width=self.sub_stroke,
                                           stroke_fill=(0, 0, 0, 255), line_spacing=1.1, trim="x")
        return self._subs[text]

    def chip(self, t: float, scene_id: str) -> tuple[Image.Image, float] | None:
        """The source chip shows during source_fact sentences, unless that paper is already on screen."""
        for span in self.facts:
            if span["start"] - CHIP_FADE <= t < span["end"] + CHIP_FADE and span["sources"]:
                source = span["sources"][0]
                if self.showing_paper.get(scene_id) == source or source not in self.chips:
                    return None
                alpha = min(ramp(t, span["start"] - CHIP_FADE, CHIP_FADE), 1 - ramp(t, span["end"], CHIP_FADE))
                return self.chips[source], alpha
        return None

    def apply(self, frame: Image.Image, t: float, scene_id: str) -> None:
        x, y, w, h = self.L.content
        s = self.s
        a, b = self.hook_span
        if a <= t < b:
            k_in = ramp(t, a, HOOK_IN)
            alpha = min(k_in, 1 - ramp(t, b - HOOK_OUT, HOOK_OUT))
            scale = 1.18 - 0.18 * k_in
            sprite = self.hook
            if scale > 1.001:
                sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.BICUBIC)
            paste_center(frame, sprite, *self.hook_center, alpha)
        chip = self.chip(t, scene_id)
        if chip:
            paste_rgba(frame, chip[0], x + s(24), y + s(20), chip[1])  # top line, clear of poster titles
        i = bisect_right(self.cue_starts, t) - 1
        if i >= 0 and self.cues[i].start <= t < self.cues[i].end:
            paste_center(frame, self.subtitle(self.cues[i].text), self.L.subtitle_cx, self.L.subtitle_cy)
        if self.ai:
            paste_rgba(frame, self.ai, x + w - s(24) - self.ai.width, y + s(20))
        if self.watermark:
            paste_rgba(frame, self.watermark, x + s(24), y + h - s(24) - self.watermark.height)
