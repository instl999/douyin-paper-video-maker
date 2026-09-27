"""Fonts. Rendering uses only openly licensed fonts (SIL OFL): Noto Sans CJK SC and Source Serif 4.

Proprietary system fonts such as Microsoft YaHei are used only with PVM_ALLOW_SYSTEM_FONTS=1: their
commercial rights sit with their foundries (spec §13.4), and a silent fallback would put them in published
videos without anyone noticing.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .config import get_settings
from .util import ROOT, PvmError, ensure_dir, log, warn, write_bytes

FONT_DIR = ROOT / "assets" / "fonts"
_WIN = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
_LINUX = Path("/usr/share/fonts")

_NOTO = ("https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/{path}",
         "https://github.com/notofonts/noto-cjk/raw/main/{path}",
         "https://fastly.jsdelivr.net/gh/notofonts/noto-cjk@main/{path}")
_SERIF = ("https://cdn.jsdelivr.net/gh/adobe-fonts/source-serif@release/{path}",
          "https://github.com/adobe-fonts/source-serif/raw/release/{path}")
DOWNLOADS = {  # file -> (mirrors, path in the upstream repository)
    "NotoSansCJKsc-Black.otf": (_NOTO, "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Black.otf"),
    "NotoSansCJKsc-Bold.otf": (_NOTO, "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf"),
    "NotoSansCJKsc-Regular.otf": (_NOTO, "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"),
    "SourceSerif4-Regular.otf": (_SERIF, "OTF/SourceSerif4-Regular.otf"),
    "SourceSerif4-Bold.otf": (_SERIF, "OTF/SourceSerif4-Bold.otf"),
    "SourceSerif4-It.otf": (_SERIF, "OTF/SourceSerif4-It.otf"),
}

# Free for commercial video output: the OFL downloads above, plus the same families from a Linux install.
FREE: dict[str, list[Path]] = {
    "black": [FONT_DIR / "NotoSansCJKsc-Black.otf", _LINUX / "opentype/noto/NotoSansCJK-Black.ttc"],
    "bold": [FONT_DIR / "NotoSansCJKsc-Bold.otf", _LINUX / "opentype/noto/NotoSansCJK-Bold.ttc"],
    "regular": [FONT_DIR / "NotoSansCJKsc-Regular.otf", _LINUX / "opentype/noto/NotoSansCJK-Regular.ttc"],
    "serif": [FONT_DIR / "SourceSerif4-Regular.otf"],
    "serif_bold": [FONT_DIR / "SourceSerif4-Bold.otf"],
    "serif_italic": [FONT_DIR / "SourceSerif4-It.otf"],
}
SYSTEM: dict[str, list[Path]] = {
    "black": [_WIN / "msyhbd.ttc", _WIN / "simhei.ttf"],
    "bold": [_WIN / "msyhbd.ttc", _WIN / "simhei.ttf"],
    "regular": [_WIN / "msyh.ttc", _WIN / "simsun.ttc"],
    "serif": [_WIN / "georgia.ttf", _WIN / "times.ttf"],
    "serif_bold": [_WIN / "georgiab.ttf", _WIN / "timesbd.ttf"],
    "serif_italic": [_WIN / "georgiai.ttf", _WIN / "timesi.ttf"],
}


def font_path(role: str) -> Path:
    for p in FREE[role]:
        if p.exists():
            return p
    if get_settings().allow_system_fonts:
        for p in SYSTEM[role]:
            if p.exists():
                return p
    if role.startswith("serif"):
        # Noto Sans CJK has Latin glyphs too: better a sans than a proprietary serif.
        return font_path("bold" if "bold" in role else "regular")
    raise PvmError(f"no openly licensed font for '{role}'. Run  pvm fonts  to download Noto Sans CJK and "
                   "Source Serif 4 (SIL OFL), or set PVM_ALLOW_SYSTEM_FONTS=1 to use system fonts such as "
                   "Microsoft YaHei (check their license before publishing).")


def _collection_index(path: Path) -> int:
    """Pick the Simplified Chinese face in a font collection (Noto's .ttc starts with Japanese)."""
    if path.suffix.lower() != ".ttc":
        return 0
    for i in range(12):
        try:
            family, _ = ImageFont.truetype(str(path), 12, index=i).getname()
        except OSError:
            break
        if " SC" in f" {family} ":
            return i
    return 0


@lru_cache(maxsize=256)
def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    path = font_path(role)
    return ImageFont.truetype(str(path), max(6, int(size)), index=_collection_index(path))


def has_cjk(text: str) -> bool:
    return any("\u3000" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef" for ch in text)


def _is_font_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) in (b"OTTO", b"\x00\x01\x00\x00") and path.stat().st_size > 50_000
    except OSError:
        return False


def download_fonts(force: bool = False) -> bool:
    import httpx

    ok = True
    ensure_dir(FONT_DIR)
    for name, (mirrors, path) in DOWNLOADS.items():
        dest = FONT_DIR / name
        if not force and _is_font_file(dest):
            log(f"  font ok: {name}")
            continue
        for mirror in mirrors:
            url = mirror.format(path=path)
            try:
                log(f"  downloading {name} from {url.split('/')[2]} ...")
                r = httpx.get(url, follow_redirects=True, timeout=httpx.Timeout(300.0, connect=15.0))
                if r.status_code == 200 and r.content[:4] == b"OTTO":
                    write_bytes(dest, r.content)
                    log(f"  saved {dest.relative_to(ROOT)} ({len(r.content) // 1024} KB)")
                    break
                warn(f"{url}: HTTP {r.status_code}")
            except httpx.HTTPError as e:
                warn(f"{url}: {e}")
        else:
            ok = False
            warn(f"could not download {name}")
    font.cache_clear()
    return ok
