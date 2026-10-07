"""Mascot model sheet and pose library (spec §9.1): generated once, reused in every video.

The model sheet comes first; every pose is then generated with the sheet as its reference image, so the same
character appears everywhere. Each image must be free of text (OCR) and is cut out onto transparency.
"""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import quota
from .config import Settings, get_settings
from .images import (_LOCK, ImageRequest, _spend_check, _to_png, image_cost, image_model, make_provider,
                     meaningful_text, read_text, request_size)
from .render.style import IVORY
from .util import ROOT, PvmError, data_dir, read_json, sha256_file, stable_hash, write_bytes, write_json

MASCOT_DIR = ROOT / "assets" / "mascot"
SHEET_SHAPE = (16, 9)  # the pixel size follows the image model (images.request_size)
POSE_SHAPE = (3, 4)
POSE_MAX_HEIGHT = 1400  # stored cut-outs; plenty for a 1080-px frame
PROMPT_VERSION = 2  # 2: fingerprints record the shape, not the pixel size


def load_design(path: Path | None = None) -> dict:
    data = read_json(path or MASCOT_DIR / "mascot.json")
    if not data:
        raise PvmError(f"no mascot design at {path or MASCOT_DIR / 'mascot.json'}")
    return data


def pose_names(design: dict | None = None) -> list[str]:
    return list((design or load_design())["poses"])


def pose_path(name: str) -> Path:
    return MASCOT_DIR / "poses" / f"{name}.png"


def sheet_prompt(d: dict) -> str:
    return "\n".join([f"CHARACTER: {d['description']}.", f"IMAGE: {d['sheet']}.",
                      f"BACKGROUND: {d['background']}.", f"AVOID: {d['avoid']}."])


def pose_prompt(d: dict, name: str) -> str:
    return "\n".join([
        "REFERENCE: the attached model sheet shows the character; keep its face, hair, hair clip, glasses, clothes, "
        "colors, proportions and paper-cut style exactly the same.",
        f"CHARACTER: {d['description']}.",
        f"POSE: {d['poses'][name]}. Exactly one character, full body.",
        f"BACKGROUND: {d['background']}.",
        f"AVOID: {d['avoid']}."])


# ---------------------------------------------------------------- cut-out

def _background(near: np.ndarray, block: int = 4) -> np.ndarray:
    """Pixels that look like background AND connect to the image border.

    Flood fill runs on a coarse grid (a block counts as background only if all its pixels do, so thin outlines
    still stop the fill), then the edge is decided at full resolution. Enclosed light areas such as a cream
    shirt stay opaque.
    """
    h, w = near.shape
    hh, ww = h // block, w // block
    coarse = near[:hh * block, :ww * block].reshape(hh, block, ww, block).all(axis=(1, 3))
    # .copy(): fromarray images share numpy's buffer read-only, and floodfill then drops its writes silently
    grid = Image.fromarray(np.pad(coarse, 1, constant_values=True).astype(np.uint8) * 255).copy()
    ImageDraw.floodfill(grid, (0, 0), 128)
    reached = np.asarray(grid)[1:-1, 1:-1] == 128
    big = np.repeat(np.repeat(reached, block, axis=0), block, axis=1)
    big = np.pad(big, ((0, h - big.shape[0]), (0, w - big.shape[1])), constant_values=True)
    grown = np.asarray(Image.fromarray(big.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * block + 1))) > 0
    return grown & near


def _components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected labels of a boolean mask. Plain BFS: meant for coarse grids of a few hundred thousand cells."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    count = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if labels[y0, x0]:
            continue
        count += 1
        labels[y0, x0] = count
        stack = [(y0, x0)]
        while stack:
            y, x = stack.pop()
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not labels[yy, xx]:
                    labels[yy, xx] = count
                    stack.append((yy, xx))
    return labels, count


def _drop_fragments(solid: np.ndarray, chroma: np.ndarray, block: int = 4) -> np.ndarray:
    """Keep the character and any colorful detached pieces (confetti, a lightbulb); drop pale fragments that are
    leftovers of the background (lighting patches, specks)."""
    h, w = solid.shape
    hh, ww = h // block, w // block
    grid = solid[:hh * block, :ww * block].reshape(hh, block, ww, block).mean(axis=(1, 3)) >= 0.5
    color = chroma[:hh * block, :ww * block].reshape(hh, block, ww, block).mean(axis=(1, 3))
    labels, count = _components(grid)
    if count <= 1:
        return solid
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    sizes[0] = 0
    main = int(sizes.argmax())
    keep = np.zeros(count + 1, dtype=bool)
    keep[main] = True
    for k in range(1, count + 1):
        if k != main and (sizes[k] >= 0.02 * sizes[main] or color[labels == k].mean() >= 35):
            keep[k] = True
    kept = np.repeat(np.repeat(keep[labels], block, axis=0), block, axis=1)
    kept = np.pad(kept, ((0, h - kept.shape[0]), (0, w - kept.shape[1])), constant_values=False)
    return solid & kept


def cut_out(img: Image.Image, tolerance: float = 24.0) -> tuple[Image.Image, float]:
    """RGBA cut-out on transparency, cropped to the character. Returns (image, foreground fraction).

    Generated backgrounds are not flat (soft lighting, pale floor shadows), so light low-saturation pixels count as
    background with a wider tolerance; connectivity keeps enclosed light areas such as the cream shirt opaque.
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.int16)
    edge = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                           rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    background_color = np.median(edge, axis=0)
    distance = np.sqrt(((rgb - background_color) ** 2).sum(axis=2))
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    luma = rgb @ np.array([0.299, 0.587, 0.114])
    near = (distance < tolerance) | ((luma > 150) & (chroma < 24) & (distance < 70))
    solid = ~_background(near)
    # opening removes specks narrower than 7 px; fingers, hair strands and glasses are far wider at this size
    solid = np.asarray(Image.fromarray(solid.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(7))
                       .filter(ImageFilter.MaxFilter(7))) > 0
    solid = _drop_fragments(solid, chroma)
    alpha = Image.fromarray(np.where(solid, 255, 0).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0))  # no pale halo, soft edge
    out = img.convert("RGBA")
    out.putalpha(alpha)
    solid = np.asarray(alpha) > 128
    fraction = float(solid.mean())
    bbox = alpha.point(lambda v: 255 if v > 16 else 0).getbbox()
    if bbox:
        pad = 12
        out = out.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                        min(out.width, bbox[2] + pad), min(out.height, bbox[3] + pad)))
    if out.height > POSE_MAX_HEIGHT:
        out = out.resize((round(out.width * POSE_MAX_HEIGHT / out.height), POSE_MAX_HEIGHT), Image.LANCZOS)
    return out, fraction


def contact_sheet(paths: list[Path], cell: int = 360, columns: int = 6) -> Image.Image:
    """Review grid of the cut-out poses on ivory, one cell per pose."""
    rows = max(1, -(-len(paths) // columns))
    sheet = Image.new("RGB", (columns * cell, rows * cell), IVORY)
    for i, path in enumerate(paths):
        pose = Image.open(path).convert("RGBA")
        pose.thumbnail((cell - 20, cell - 20), Image.LANCZOS)
        x = (i % columns) * cell + (cell - pose.width) // 2
        y = (i // columns) * cell + (cell - pose.height) // 2
        sheet.paste(pose, (x, y), pose)
    return sheet


# ---------------------------------------------------------------- generation

@dataclass
class MascotResult:
    name: str
    status: str  # up-to-date | accepted | review | dry-run
    afp: int = 0
    attempts: list[dict] = field(default_factory=list)
    prompt: str = ""


def _cache_key(fingerprint: str, model: str, attempt: int) -> str:
    return stable_hash({"f": fingerprint, "model": model, "attempt": attempt, "kind": "mascot"})[:24]


def _save_original(name: str, img: Image.Image) -> None:
    """Keep the uncut image with the assets (compact JPEG) so cut-outs can be redone on any machine."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    write_bytes(MASCOT_DIR / "originals" / f"{name}.jpg", buf.getvalue())


def _original(name: str, meta: dict) -> Image.Image | None:
    stored = MASCOT_DIR / "originals" / f"{name}.jpg"
    if stored.exists():
        return Image.open(stored).convert("RGB")
    ok = [a for a in meta.get("attempts", []) if a.get("ok")]
    if not ok:
        return None
    cached = data_dir("cache") / "images" / f"{_cache_key(meta['fingerprint'], meta['model'], ok[-1]['attempt'])}.png"
    if not cached.exists():
        return None
    img = Image.open(cached).convert("RGB")
    _save_original(name, img)
    return img


def write_contact_sheet() -> Path | None:
    done = [pose_path(n) for n in pose_names() if pose_path(n).exists()]
    if not done:
        return None
    buf = io.BytesIO()
    contact_sheet(done).save(buf, "PNG", optimize=True)
    write_bytes(MASCOT_DIR / "contact.png", buf.getvalue())
    return MASCOT_DIR / "contact.png"


def recut_poses() -> list[str]:
    """Redo the cut-outs from the originals after cut_out improves: no generation, no quota."""
    names = []
    for name in pose_names():
        meta_path = pose_path(name).with_suffix(".json")
        meta = read_json(meta_path)
        if not meta or meta.get("status") != "accepted":
            continue
        original = _original(name, meta)
        if original is None:
            continue
        out, fraction = cut_out(original)
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        write_bytes(pose_path(name), buf.getvalue())
        meta["foreground"] = round(fraction, 3)
        write_json(meta_path, meta)
        names.append(name)
    write_contact_sheet()
    return names


def fingerprint(prompt: str, shape: tuple[int, int], refs: list[Path], cut: bool) -> str:
    return stable_hash({"prompt": prompt, "shape": list(shape), "refs": [sha256_file(r) for r in refs], "cut": cut,
                        "v": PROMPT_VERSION})[:16]


def _generate(name: str, prompt: str, shape: tuple[int, int], refs: list[Path], *, provider, settings: Settings,
              attempts: int, regenerate: bool, dry_run: bool, target: Path, cut: bool) -> MascotResult:
    size = request_size(shape, image_model(settings.image_model))
    cost = image_cost(settings, size, len(refs))
    fp = fingerprint(prompt, shape, refs, cut)
    meta_path = target.with_suffix(".json")
    meta = read_json(meta_path) or {}
    if not regenerate and target.exists() and meta.get("fingerprint") == fp and meta.get("status") == "accepted":
        return MascotResult(name, "up-to-date", 0, meta.get("attempts", []), prompt)
    if dry_run:
        return MascotResult(name, "dry-run", cost, [], prompt)
    tried, spent, best = [], 0, None
    for attempt in range(1, attempts + 1):
        cached = data_dir("cache") / "images" / f"{_cache_key(fp, provider.model, attempt)}.png"
        if cached.exists():
            data, source = cached.read_bytes(), "cache"
        else:
            with _LOCK:
                _spend_check(cost)
            generated = provider.generate(ImageRequest(prompt, size, refs))
            spent += cost
            with _LOCK:
                quota.record(cost, kind="mascot", model=provider.model, note=f"{name} attempt {attempt}")
            data, source = _to_png(generated.data), "generated"
            write_bytes(cached, data)
        text = meaningful_text(read_text(data))
        image = Image.open(io.BytesIO(data))
        result, fraction = cut_out(image) if cut else (image.convert("RGB"), 0.5)
        problems = []
        if text:
            problems.append("text in the image: " + " / ".join(text))
        if cut and not 0.03 <= fraction <= 0.7:
            problems.append(f"cut-out covers {fraction:.0%} of the image (expected 3-70%)")
        tried.append({"attempt": attempt, "source": source, "ok": not problems, "problems": problems,
                      "foreground": round(fraction, 3)})
        if best is None or len(problems) < best[0]:
            best = (len(problems), result, image)
        if not problems:
            break
    status = "accepted" if tried[-1]["ok"] else "review"
    candidate = target.with_name(target.stem + ".candidate.png")
    out = target if status == "accepted" else candidate
    if status == "accepted":
        candidate.unlink(missing_ok=True)  # an earlier review is settled
        if cut:
            _save_original(name, best[2])
    buf = io.BytesIO()
    best[1].save(buf, "PNG", optimize=True)
    write_bytes(out, buf.getvalue())
    write_json(meta_path, {"name": name, "status": status, "fingerprint": fp, "prompt": prompt,
                           "size": list(size), "model": provider.model, "attempts": tried,
                           "afp": spent + (0 if regenerate else meta.get("afp", 0))})
    return MascotResult(name, status, spent, tried, prompt)


def run_mascot(*, poses: list[str] | None = None, sheet_only: bool = False, regenerate: bool = False,
               dry_run: bool = False, attempts: int | None = None, provider=None) -> list[MascotResult]:
    settings = get_settings()
    design = load_design()
    unknown = [p for p in poses or [] if p not in design["poses"]]
    if unknown:
        raise PvmError(f"unknown pose(s) {unknown}; the design defines: {', '.join(design['poses'])}")
    if provider is None and not dry_run:
        provider = make_provider(settings)
    budget = attempts or settings.image_attempts
    sheet = MASCOT_DIR / "sheet.png"
    results = [_generate("sheet", sheet_prompt(design), SHEET_SHAPE, [], provider=provider, settings=settings,
                         attempts=budget, regenerate=regenerate and (sheet_only or not poses), dry_run=dry_run,
                         target=sheet, cut=False)]
    if sheet_only:
        return results
    if not sheet.exists():
        if dry_run:  # poses need the sheet as their reference; estimate them anyway
            cost = image_cost(settings, request_size(POSE_SHAPE, image_model(settings.image_model)), 1)
            return results + [MascotResult(n, "dry-run", cost, [], pose_prompt(design, n))
                              for n in poses or design["poses"]]
        raise PvmError("the model sheet is not accepted yet; review assets/mascot/sheet.candidate.png")
    def one(name: str) -> MascotResult:
        return _generate(name, pose_prompt(design, name), POSE_SHAPE, [sheet], provider=provider, settings=settings,
                         attempts=budget, regenerate=regenerate, dry_run=dry_run, target=pose_path(name), cut=True)

    with ThreadPoolExecutor(max_workers=max(1, getattr(settings, "image_concurrency", 1))) as pool:
        results += list(pool.map(one, poses or design["poses"]))
    if not dry_run:
        write_contact_sheet()
    return results
