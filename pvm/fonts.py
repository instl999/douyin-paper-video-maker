"""Font discovery and download. Display text uses Noto Sans CJK SC (SIL OFL) when installed."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .util import ROOT, PvmError, ensure_dir, log, warn, write_bytes

FONT_DIR = ROOT / "assets" / "fonts"
_WIN = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
_LINUX = Path("/usr/share/fonts")

DOWNLOADS = {
    "NotoSansCJKsc-Black.otf": "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Black.otf",
    "NotoSansCJKsc-Bold.otf": "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf",
}
MIRRORS = (
    "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/{path}",
    "https://github.com/notofonts/noto-cjk/raw/main/{path}",
    "https://fastly.jsdelivr.net/gh/notofonts/noto-cjk@main/{path}",
)

CANDIDATES: dict[str, list[Path]] = {
    "black": [FONT_DIR / "NotoSansCJKsc-Black.otf", _WIN / "msyhbd.ttc", _WIN / "simhei.ttf",
              _LINUX / "opentype/noto/NotoSansCJK-Black.ttc"],
    "bold": [FONT_DIR / "NotoSansCJKsc-Bold.otf", _WIN / "msyhbd.ttc", _WIN / "simhei.ttf",
             _LINUX / "opentype/noto/NotoSansCJK-Bold.ttc"],
    "regular": [_WIN / "msyh.ttc", FONT_DIR / "NotoSansCJKsc-Bold.otf", _WIN / "simsun.ttc",
                _LINUX / "opentype/noto/NotoSansCJK-Regular.ttc"],
    "serif": [_WIN / "georgia.ttf", _WIN / "times.ttf", _LINUX / "truetype/dejavu/DejaVuSerif.ttf"],
    "serif_bold": [_WIN / "georgiab.ttf", _WIN / "timesbd.ttf", _LINUX / "truetype/dejavu/DejaVuSerif-Bold.ttf"],
    "serif_italic": [_WIN / "georgiai.ttf", _WIN / "timesi.ttf", _LINUX / "truetype/dejavu/DejaVuSerif-Italic.ttf"],
}


def font_path(role: str) -> Path:
    for p in CANDIDATES[role]:
        if p.exists():
            return p
    if role.startswith("serif"):
        return font_path("bold" if "bold" in role else "regular")
    raise PvmError(f"no font found for '{role}'. Run  pvm fonts  to download Noto Sans CJK.")


@lru_cache(maxsize=256)
def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(role)), max(6, int(size)), index=0)


def has_cjk(text: str) -> bool:
    return any("\u3000" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef" for ch in text)


def download_fonts(force: bool = False) -> bool:
    import httpx

    ok = True
    ensure_dir(FONT_DIR)
    for name, path in DOWNLOADS.items():
        dest = FONT_DIR / name
        if dest.exists() and dest.stat().st_size > 1_000_000 and not force:
            log(f"  font ok: {name}")
            continue
        for mirror in MIRRORS:
            url = mirror.format(path=path)
            try:
                log(f"  downloading {name} from {url.split('/')[2]} ...")
                r = httpx.get(url, follow_redirects=True, timeout=httpx.Timeout(120.0, connect=15.0))
                if r.status_code == 200 and r.content[:4] == b"OTTO":
                    write_bytes(dest, r.content)
                    log(f"  saved {dest.relative_to(ROOT)} ({len(r.content) // 1024} KB)")
                    break
                warn(f"{url}: HTTP {r.status_code}")
            except httpx.HTTPError as e:
                warn(f"{url}: {e}")
        else:
            ok = False
            warn(f"could not download {name}; falling back to system fonts (Microsoft YaHei Bold)")
    font.cache_clear()
    return ok
