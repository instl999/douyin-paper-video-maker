"""Style pack and layouts (spec §9.2, §10.6). All sizes are for a 1080-px-wide frame; Layout.s() scales them."""
from __future__ import annotations

from dataclasses import dataclass

STYLE_VERSION = "paper-cut@1"

IVORY = (244, 239, 230)
SHEET = (251, 248, 241)
INK = (30, 30, 30)
NAVY = (31, 58, 95)
OCHRE = (227, 162, 26)
HOOK_YELLOW = (255, 225, 26)
MARKER = (255, 214, 10)
MUTED = (120, 112, 100)


@dataclass(frozen=True)
class Layout:
    ratio: str  # "3x4" or "9x16"
    width: int
    height: int
    content: tuple[int, int, int, int]  # x, y, w, h of the 3:4 composition inside the frame
    subtitle_cx: int
    subtitle_cy: int
    subtitle_max_w: int
    fps: int
    scale: float  # 1.0 for final renders, 0.5 for animatics

    def s(self, v: float) -> int:
        """A size given for a 1080-px-wide frame, at this layout's scale."""
        return max(1, int(round(v * self.scale)))

    @property
    def content_size(self) -> tuple[int, int]:
        return self.content[2], self.content[3]


def layout(ratio: str = "3x4", *, animatic: bool = False) -> Layout:
    k = 0.5 if animatic else 1.0
    fps = 15 if animatic else 30

    def px(v: float) -> int:
        return int(round(v * k))

    if ratio == "3x4":
        # Subtitles at ~86% of the height (spec §10.6), clear of the panels, which end at ~82%.
        return Layout("3x4", px(1080), px(1440), (0, 0, px(1080), px(1440)), px(540), px(1246), px(920), fps, k)
    if ratio == "9x16":
        # The 3:4 composition sits in the middle; subtitles at ~77% and left of the platform's action rail.
        return Layout("9x16", px(1080), px(1920), (0, px(150), px(1080), px(1440)), px(500), px(1478), px(820), fps, k)
    raise ValueError(f"unknown ratio '{ratio}' (use 3x4 or 9x16)")
