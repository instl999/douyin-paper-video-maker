"""Poster images (spec §8): deterministic prompt compiler, Seedream behind a provider adapter, content cache,
retry budget with an OCR gate on the model-drawn labels, and an AFP ledger entry for every paid call."""
from __future__ import annotations

import base64
import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from PIL import Image

from . import quota
from .config import Settings, get_settings
from .project import Project
from .render.scenes import Context, generation_box
from .render.style import layout
from .schema import GENERATED_TYPES
from .util import ROOT, PvmError, data_dir, read_json, sha256_file, stable_hash, warn, write_bytes, write_json

PROMPT_VERSION = 1
LONG_SIDE = 2048
_LOCK = threading.Lock()  # one OCR run and one ledger write at a time


# ---------------------------------------------------------------- style pack and prompt (spec §15.2)

def load_style(name: str) -> dict:
    path = ROOT / "assets" / "style" / f"{name}.json"
    data = read_json(path)
    if not data:
        raise PvmError(f"style pack '{name}' not found ({path})")
    return data


def scene_panels(scene) -> list[tuple[str, list[str]]]:
    """(visual brief, labels) for each panel the image has to contain."""
    if scene.type == "image":
        return [(scene.visual, [])]
    return [(sec.visual, list(sec.labels)) for sec in scene.sections]


def compile_prompt(scene, style: dict) -> str:
    panels = scene_panels(scene)
    lines = [f"STYLE: {style['anchor']}.", f"CHARACTER: {style['mascot']}."]
    if style.get("avoid"):
        lines.append(f"AVOID: {style['avoid']}.")
    if len(panels) > 1:
        lines.append(f"LAYOUT: {len(panels)} stacked horizontal panels of equal height, separated by clear empty ivory "
                     "gutters; keep the top-left corner of every panel empty; no panel borders, numbers or titles.")
        for i, (visual, labels) in enumerate(panels, 1):
            tags = "、".join(f"“{label}”" for label in labels)
            lines.append(f"PANEL {i}: {visual}." + (f" Paper tags reading {tags}." if tags else ""))
    else:
        lines.append(f"SCENE: {panels[0][0]}.")
    labels = [label for _, ls in panels for label in ls]
    if labels:
        lines.append("TEXT: the only readable text allowed is these Chinese words on paper tags: " + "、".join(labels)
                     + ". No other characters, no letters, no digits, no logos, no watermarks.")
    else:
        lines.append("TEXT: no readable text at all: no characters, letters, digits, logos or watermarks.")
    if getattr(scene, "extra", None):
        lines.append(scene.extra)
    return "\n".join(lines)


def request_size(box: tuple[int, int], long_side: int = LONG_SIDE) -> tuple[int, int]:
    """Pixel size at the aspect ratio of the area the image fills, long side ~2K, multiples of 16."""
    w, h = box
    if w >= h:
        return long_side, max(512, round(long_side * h / w / 16) * 16)
    return max(512, round(long_side * w / h / 16) * 16), long_side


# ---------------------------------------------------------------- provider adapter (spec §8.1)

@dataclass
class ImageRequest:
    prompt: str
    size: tuple[int, int]
    references: list[Path] = field(default_factory=list)


@dataclass
class GeneratedImage:
    data: bytes
    meta: dict = field(default_factory=dict)


def _data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class ArkImageProvider:
    """Seedream through Volcano Ark (Agent Plan or pay-as-you-go): POST {base}/images/generations."""

    name = "ark"

    def __init__(self, base_url: str, api_key: str, model: str, *, transport: httpx.BaseTransport | None = None):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.transport = transport  # tests pass an httpx.MockTransport

    def generate(self, req: ImageRequest) -> GeneratedImage:
        # watermark off: the video carries its own visible AI label and metadata record (spec §13.2)
        body = {"model": self.model, "prompt": req.prompt, "size": f"{req.size[0]}x{req.size[1]}",
                "response_format": "b64_json", "watermark": False}
        if req.references:
            refs = [_data_url(p) for p in req.references]
            body["image"] = refs[0] if len(refs) == 1 else refs
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0), transport=self.transport) as client:
            for attempt in range(3):
                try:
                    r = client.post(f"{self.base_url}/images/generations", json=body, headers=headers)
                    break
                except httpx.HTTPError as e:
                    if attempt == 2:
                        raise PvmError(f"Seedream network error: {e}") from e
            data = _json(r)
            if r.status_code != 200 or data.get("error"):
                err = data.get("error") or {}
                detail = f"{err.get('code', '')} {err.get('message', '')}".strip() or r.text[:300]
                raise PvmError(f"Seedream HTTP {r.status_code}: {detail}")
            items = data.get("data") or []
            if not items:
                raise PvmError("Seedream returned no image")
            item = items[0]
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
            elif item.get("url"):  # the link expires within a day, so fetch it right away
                raw = client.get(item["url"]).content
            else:
                raise PvmError("Seedream response has neither b64_json nor url")
        return GeneratedImage(raw, {"size": item.get("size"), "usage": data.get("usage"),
                                    "model": data.get("model", self.model)})


def make_provider(settings: Settings):
    if settings.image_provider != "ark":
        raise PvmError(f"unknown image provider '{settings.image_provider}' (supported: ark)")
    if not settings.api_key:
        raise PvmError("image generation needs AGENT_PLAN_API_KEY in .env; use --dry-run to preview prompts and cost")
    return ArkImageProvider(settings.ark_base_url, settings.api_key, settings.image_model)


# ---------------------------------------------------------------- OCR gate (spec §8.3)

_OCR = None
_CJK = re.compile(r"[㐀-鿿]")
_LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9]")


def read_text(data: bytes) -> list[tuple[str, float]]:
    """(text, confidence) for every line OCR finds in an encoded image."""
    global _OCR
    with _LOCK:
        if _OCR is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as e:
                raise PvmError("the OCR gate needs rapidocr_onnxruntime (pip install rapidocr_onnxruntime)") from e
            _OCR = RapidOCR()
        result, _ = _OCR(data)
    return [(str(text), float(score)) for _, text, score in (result or [])]


@dataclass
class OcrCheck:
    ok: bool
    missing: list[str]  # requested labels OCR could not find
    forbidden: list[str]  # lines with letters or digits: the model drew text it must not draw
    extra: list[str]  # other Chinese text (a warning, not a failure)


def check_labels(found: list[tuple[str, float]], labels: list[str], min_score: float = 0.6) -> OcrCheck:
    lines = [text for text, score in found if score >= min_score]
    cjk_lines = ["".join(_CJK.findall(t)) for t in lines]
    joined = "".join(cjk_lines)  # a label may wrap onto two lines
    wanted = ["".join(_CJK.findall(label)) for label in labels]
    missing = [label for label, want in zip(labels, wanted) if want and want not in joined]
    forbidden = [t for t in lines if _LATIN_OR_DIGIT.search(t)]
    extra = []
    for line in cjk_lines:
        rest = line
        for want in wanted:
            if want:
                rest = rest.replace(want, "")
        if len(rest) >= 2:
            extra.append(line)
    return OcrCheck(not missing and not forbidden, missing, forbidden, extra)


# ---------------------------------------------------------------- cache and generation

def _cache_dir() -> Path:
    return data_dir("cache") / "images"


def _to_png(data: bytes) -> bytes:
    buf = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


@dataclass
class SceneResult:
    scene: str
    status: str  # up-to-date | accepted | review | dry-run
    afp: int = 0
    file: str | None = None
    attempts: list[dict] = field(default_factory=list)
    prompt: str = ""
    size: tuple[int, int] = (0, 0)


def _spend_check(settings: Settings) -> None:
    st = quota.status()
    if st.allowance_today < settings.afp_per_image:
        raise PvmError(f"today's AFP allowance ({st.allowance_today:,}) is below the cost of one image "
                       f"({settings.afp_per_image}); the monthly budget is paced over the days left (pvm quota)")
    if st.mode == "approved-only":
        warn("less than 10% of the monthly AFP budget is left; generate only for approved storyboards")


def prompt_fingerprint(prompt: str, size: tuple[int, int], style: dict, refs: list[Path]) -> str:
    return stable_hash({"prompt": prompt, "size": list(size), "style": style.get("version"),
                        "refs": [sha256_file(r) for r in refs], "v": PROMPT_VERSION})[:16]


def generate_scene(p: Project, scene, *, style: dict, box: tuple[int, int], provider, settings: Settings,
                   attempts: int, regenerate: bool = False, dry_run: bool = False) -> SceneResult:
    prompt = compile_prompt(scene, style)
    size = request_size(box)
    refs = [ROOT / r for r in style.get("references", [])]
    labels = [label for _, ls in scene_panels(scene) for label in ls]
    fingerprint = prompt_fingerprint(prompt, size, style, refs)
    out = p.visuals_dir / f"{scene.id}.png"
    meta_path = p.visuals_dir / f"{scene.id}.json"
    meta = read_json(meta_path) or {}
    if not regenerate and out.exists() and meta.get("fingerprint") == fingerprint and meta.get("status") == "accepted":
        return SceneResult(scene.id, "up-to-date", 0, str(out), meta.get("attempts", []), prompt, size)
    if dry_run:
        return SceneResult(scene.id, "dry-run", settings.afp_per_image, None, [], prompt, size)

    tried: list[dict] = []
    best: tuple[int, bytes] | None = None
    spent = 0
    for attempt in range(1, attempts + 1):
        key = stable_hash({"f": fingerprint, "provider": provider.name, "model": provider.model,
                           "attempt": attempt})[:24]
        cached = _cache_dir() / f"{key}.png"
        if cached.exists():
            data, source = cached.read_bytes(), "cache"
        else:
            with _LOCK:
                _spend_check(settings)
            generated = provider.generate(ImageRequest(prompt, size, refs))
            spent += settings.afp_per_image
            with _LOCK:
                quota.record(settings.afp_per_image, kind="image", project=p.slug, model=provider.model,
                             note=f"{scene.id} attempt {attempt}")
            data, source = _to_png(generated.data), "generated"
            write_bytes(cached, data)
            write_json(_cache_dir() / f"{key}.json", {"prompt": prompt, "size": list(size), **generated.meta})
        check = check_labels(read_text(data), labels)
        tried.append({"attempt": attempt, "source": source, "ok": check.ok, "missing": check.missing,
                      "forbidden": check.forbidden, "extra": check.extra})
        score = len(check.missing) + 2 * len(check.forbidden)
        if best is None or score < best[0]:
            best = (score, data)
        if check.ok:
            break

    status = "accepted" if tried[-1]["ok"] else "review"
    target = out if status == "accepted" else p.visuals_dir / f"{scene.id}.candidate.png"
    write_bytes(target, best[1])
    write_json(meta_path, {"scene": scene.id, "status": status, "fingerprint": fingerprint, "prompt": prompt,
                           "size": list(size), "provider": provider.name, "model": provider.model, "labels": labels,
                           "attempts": tried, "afp": spent + (meta.get("afp", 0) if not regenerate else 0)})
    return SceneResult(scene.id, status, spent, str(target), tried, prompt, size)


def accept_candidate(p: Project, scene_id: str) -> Path:
    """Operator override after reviewing a candidate that failed the OCR gate; recorded in the metadata."""
    candidate = p.visuals_dir / f"{scene_id}.candidate.png"
    if not candidate.exists():
        raise PvmError(f"no candidate image for {scene_id} ({candidate})")
    out = p.visuals_dir / f"{scene_id}.png"
    write_bytes(out, candidate.read_bytes())
    candidate.unlink()
    meta = read_json(p.visuals_dir / f"{scene_id}.json") or {}
    meta.update(status="accepted", accepted_by="operator")
    write_json(p.visuals_dir / f"{scene_id}.json", meta)
    return out


def image_scenes(sb, only: list[str] | None = None) -> list:
    """Scenes that need a generated image: posters, summaries and images without an operator-supplied file."""
    return [sc for sc in sb.scenes if sc.type in GENERATED_TYPES and not getattr(sc, "image", None)
            and (not only or sc.id in only)]


def stale_images(p: Project, sb) -> list[str]:
    """Scenes whose accepted image was generated for a different brief, labels, style or size."""
    settings = get_settings()
    style = load_style(sb.style or settings.style)
    refs = [ROOT / r for r in style.get("references", [])]
    ctx = Context(p, layout("3x4"), p.sources(), animatic=False)
    stale = []
    for sc in image_scenes(sb):
        meta = read_json(p.visuals_dir / f"{sc.id}.json")
        if meta and meta.get("fingerprint") != prompt_fingerprint(compile_prompt(sc, style),
                                                                  request_size(generation_box(ctx, sc)), style, refs):
            stale.append(sc.id)
    return stale


def run_images(p: Project, *, only: list[str] | None = None, attempts: int | None = None, regenerate: bool = False,
               dry_run: bool = False, provider=None) -> list[SceneResult]:
    settings = get_settings()
    sb = p.storyboard()
    style = load_style(sb.style or settings.style)
    ctx = Context(p, layout("3x4"), p.sources(), animatic=False)
    targets = image_scenes(sb, only)
    if only and len(targets) != len(set(only)):
        known = [sc.id for sc in image_scenes(sb)]
        raise PvmError(f"unknown or non-image scene in {only}; image scenes: {', '.join(known) or 'none'}")
    boxes = {sc.id: generation_box(ctx, sc) for sc in targets}  # fonts and geometry on this thread
    if provider is None and not dry_run:
        provider = make_provider(settings)

    def one(sc):
        return generate_scene(p, sc, style=style, box=boxes[sc.id], provider=provider, settings=settings,
                              attempts=attempts or settings.image_attempts, regenerate=regenerate, dry_run=dry_run)

    with ThreadPoolExecutor(max_workers=max(1, settings.image_concurrency)) as pool:
        return list(pool.map(one, targets))
