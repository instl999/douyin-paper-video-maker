"""Render: composed frames -> x264, voice with two-pass loudness normalization, AIGC metadata, cover, manifest.

Frames are pure functions of time, so chunks render in parallel worker processes and are concatenated.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

from .. import quota
from ..config import get_settings
from ..evidence import describe_license
from ..project import Project
from ..schema import GENERATED_TYPES, Storyboard
from ..script import sentences_hash
from ..timeline import Timeline
from ..util import PvmError, ensure_dir, ffmpeg_exe, fmt_seconds, log, now_iso, read_json, run, stable_hash, write_json, write_text
from .assets import paper_texture, ramp
from .overlay import Overlays
from .scenes import Context, make_renderer
from .style import STYLE_VERSION, Layout, layout

LOUDNESS = {"I": -12.0, "TP": -1.0}  # spec §10.5
FADE = 0.35


class Composer:
    """Everything needed to draw the frame at time t."""

    def __init__(self, p: Project, sb: Storyboard, tl: Timeline, L: Layout, *, animatic: bool, strict: bool):
        self.ctx = Context(p, L, p.sources(), animatic, strict)
        self.sb, self.tl, self.L = sb, tl, L
        self.renderers: dict[int, object] = {}
        self.overlays = Overlays(self.ctx, sb, tl)
        full = L.content == (0, 0, L.width, L.height)
        self.canvas = None if full else paper_texture(L.width, L.height)

    def renderer(self, k: int):
        if k not in self.renderers:
            self.renderers[k] = make_renderer(self.ctx, self.sb.scenes[k], self.tl.scenes[k])
        return self.renderers[k]

    def scene_index(self, t: float) -> int:
        for k, sc in enumerate(self.tl.scenes):
            if t < sc.end:
                return k
        return len(self.tl.scenes) - 1

    def frame(self, t: float) -> Image.Image:
        k = self.scene_index(t)
        img = self.renderer(k).frame(t)
        timing = self.tl.scenes[k]
        if self.sb.scenes[k].transition == "fade" and k > 0 and t < timing.start + FADE:
            img = Image.blend(self.renderer(k - 1).frame(t), img, ramp(t, timing.start, FADE))
        if self.canvas is not None:
            canvas = self.canvas.copy()
            canvas.paste(img, self.L.content[:2])
            img = canvas
        self.overlays.apply(img, t, timing.id)
        return img


def _encoder_args(L: Layout) -> list[str]:
    s = get_settings()
    return ["-c:v", "libx264", "-preset", s.x264_preset, "-crf", str(s.crf), "-pix_fmt", "yuv420p",
            "-g", str(L.fps * 2)]


def _render_chunk(job: dict) -> dict:
    """Worker: render frames [first, last) of one video into a video-only file."""
    if job.get("home"):
        os.environ["PVM_HOME"] = job["home"]
    p = Project.load(job["slug"])
    sb = p.storyboard(check=False)
    tl = Timeline.from_json(read_json(p.audio_dir / "timeline.json"))
    L = layout(job["ratio"], animatic=job["animatic"])
    comp = Composer(p, sb, tl, L, animatic=job["animatic"], strict=job["strict"])
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{L.width}x{L.height}", "-r", str(L.fps), "-i", "-", "-an", *_encoder_args(L), job["out"]]
    first, last = job["frames"]
    step = max(1, (last - first) // 4)
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:  # closes the pipes on exit
        try:
            for f in range(first, last):
                proc.stdin.write(comp.frame(f / L.fps).tobytes())
                if job["verbose"] and (f - first) % step == 0 and f > first:
                    log(f"  part {job['index'] + 1}/{job['parts']}: {100 * (f - first) // (last - first)}%")
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read().decode("utf-8", "replace")
        code = proc.wait()
    if code != 0:
        raise PvmError(f"ffmpeg failed while encoding part {job['index'] + 1}:\n{err[-800:]}")
    return {"warnings": comp.ctx.warnings, "visuals": comp.ctx.visuals, "displays": comp.ctx.displays}


COMPRESSOR = "acompressor=threshold=0.063:ratio=4:attack=3:release=100"  # -24 dB threshold, 4:1
CEILING = 0.8414  # -1.5 dBFS on 4x-oversampled audio keeps true peaks under -1 dBTP after AAC encoding


def _voice_chain(gain_db: float) -> str:
    return (f"{COMPRESSOR},volume={gain_db:.2f}dB,aresample=192000,"
            f"alimiter=limit={CEILING}:attack=2:release=60:level=false,aresample=48000")


def _integrated(path: Path, chain: str) -> float:
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af",
                           f"{chain},ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True)
    found = re.findall(r"^\s+I:\s+(-?[\d.]+) LUFS", proc.stderr.decode("utf-8", "replace"), re.M)
    if not found:
        raise PvmError(f"could not measure the loudness of {path}")
    return float(found[-1])


def voice_filter(path: Path) -> tuple[str, dict]:
    """Loudness processing (spec §10.5): gentle compression, gain to the target, oversampled peak limiting.

    Speech peaks sit 15-20 dB above its loudness, so -12 LUFS under a -1 dBTP ceiling is impossible with gain
    alone (loudnorm stalls near -15 LUFS). The limiter takes back about a decibel, so the gain is re-measured.
    """
    measured = _integrated(path, COMPRESSOR)
    gain = LOUDNESS["I"] - measured
    for _ in range(2):
        gain += LOUDNESS["I"] - _integrated(path, _voice_chain(gain))
    return _voice_chain(gain), {"input_lufs": measured, "gain_db": round(gain, 2)}


def aigc_record(p: Project, produce_id: str) -> dict:
    """Implicit AI-content label (spec §13.2, GB 45438-2025): this object is the value of the file's AIGC metadata
    field. Label "1" marks the content as AI-generated; the propagator fields are for the publishing platform."""
    return {"Label": "1", "ContentProducer": get_settings().aigc_producer, "ProduceID": produce_id,
            "ReservedCode1": "", "ContentPropagator": "", "PropagateID": "", "ReservedCode2": ""}


def _xmp(record: dict) -> str:
    """XMP packet carrying the AIGC record in the TC260 namespace, the image form of the implicit label."""
    value = json.dumps(record, ensure_ascii=False).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:TC260="http://www.tc260.org.cn/ns/AIGC/1.0/">'
            f'<TC260:AIGC>{value}</TC260:AIGC></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')


def default_jobs(n_frames: int) -> int:
    if n_frames < 300:  # below this, starting worker processes costs more than it saves
        return 1
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def output_name(kind: str, ratio: str) -> str:
    """animatic.mp4, draft_3x4.mp4 (placeholders allowed) or final_3x4.mp4 (strict checks)."""
    return "animatic" if kind == "animatic" else f"{kind}_{ratio}"


def render(p: Project, sb: Storyboard, tl: Timeline, *, ratio: str = "3x4", kind: str = "final",
           jobs: int | None = None, verbose: bool = True) -> dict:
    """Render one output file (kind: animatic, draft or final). Returns a summary used by the manifest."""
    started = time.perf_counter()
    animatic, strict = kind == "animatic", kind == "final"
    L = layout(ratio, animatic=animatic)
    n_frames = math.ceil(tl.duration * L.fps)
    jobs = max(1, min(jobs or default_jobs(n_frames), 8))
    name = output_name(kind, ratio)
    out_dir = ensure_dir(p.output_dir)
    parts_dir = ensure_dir(out_dir / f".parts-{name}")
    bounds = [round(n_frames * i / jobs) for i in range(jobs + 1)]
    work = [{"slug": p.slug, "home": os.environ.get("PVM_HOME"), "ratio": ratio, "animatic": animatic,
             "strict": strict, "frames": (bounds[i], bounds[i + 1]), "index": i, "parts": jobs, "verbose": verbose,
             "out": str(parts_dir / f"part{i:02d}.mp4")} for i in range(jobs) if bounds[i + 1] > bounds[i]]
    if verbose:
        log(f"rendering {name}: {L.width}x{L.height} @ {L.fps} fps, {n_frames} frames, {len(work)} part(s)")
    if len(work) == 1:
        results = [_render_chunk(work[0])]
    else:
        with mp.get_context("spawn").Pool(len(work)) as pool:
            results = pool.map(_render_chunk, work)

    listing = parts_dir / "parts.txt"
    write_text(listing, "".join(f"file '{Path(w['out']).name}'\n" for w in work))
    wav = p.audio_dir / "voice.wav"
    audio_filter, audio_info = voice_filter(wav)
    produce_id = f"{p.slug}-{stable_hash([sb.model_dump(), tl.to_json(), ratio, animatic])[:12]}"
    settings = get_settings()
    meta = ["-metadata", f"title={sb.title}",
            "-metadata", "comment=Made with pvm. Contains AI-generated images and synthetic voice.",
            "-metadata", "AIGC=" + json.dumps(aigc_record(p, produce_id), ensure_ascii=False)]
    final = out_dir / f"{name}.mp4"
    tmp = out_dir / f".{name}.tmp.mp4"
    run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", audio_filter,
         "-c:a", "aac", "-b:a", "192k", "-shortest",
         "-movflags", "+faststart+use_metadata_tags", *meta, str(tmp)])
    os.replace(tmp, final)
    shutil.rmtree(parts_dir, ignore_errors=True)

    warnings, visuals, displays = [], {}, {}
    for r in results:
        warnings += [w for w in r["warnings"] if w not in warnings]
        visuals.update(r["visuals"])
        displays.update(r["displays"])
    elapsed = time.perf_counter() - started
    if verbose:
        log(f"  -> {final} ({fmt_seconds(tl.duration)}, rendered in {elapsed:.0f} s)")
    return {"file": str(final.relative_to(p.dir)), "kind": kind, "ratio": ratio, "width": L.width, "height": L.height,
            "fps": L.fps, "frames": n_frames, "seconds": round(elapsed, 1), "warnings": warnings, "visuals": visuals,
            "displays": displays, "audio": audio_info, "produce_id": produce_id,
            "ai_label": settings.ai_label if settings.ai_label.lower() != "none" else None}


def save_cover(p: Project, sb: Storyboard, tl: Timeline, ratio: str = "3x4") -> Path:
    """The cover is the opening frame once the hook has popped in: paper evidence plus hook."""
    from PIL.PngImagePlugin import PngInfo

    comp = Composer(p, sb, tl, layout(ratio), animatic=False, strict=False)
    path = p.output_dir / "cover.png"
    img = comp.frame(min(tl.hook[0] + 0.5, max(0.0, tl.hook[1] - 0.3)))  # includes the visible AI label
    record = aigc_record(p, f"{p.slug}-cover-{stable_hash([sb.model_dump(), ratio])[:12]}")
    info = PngInfo()
    info.add_itxt("XML:com.adobe.xmp", _xmp(record))
    info.add_text("AIGC", json.dumps(record, ensure_ascii=False))
    img.save(path, pnginfo=info)
    return path


def write_description(p: Project, sb: Storyboard) -> Path:
    papers = p.sources()
    lines = [sb.title, "", "参考文献："] + [f"- {paper.citation()}" for paper in papers.values()]
    lines += ["", "—— 发布前检查（不要粘贴到简介里）——",
              "[ ] 抖音发布页勾选“内容由AI生成”声明",
              f"[ ] 画面内可见标识：{get_settings().ai_label}",
              "[ ] 背景音乐在抖音内添加（视频内未内置）",
              "[ ] 看一遍成片：论点与文献是否一致、字幕是否被界面遮挡"]
    path = p.output_dir / "description.txt"
    write_text(path, "\n".join(lines) + "\n")
    return path


def visuals_record(p: Project, sb: Storyboard) -> list[dict]:
    """Each generated image: model, attempts (and how many came from the cache), OCR outcome and AFP."""
    out = []
    for sc in sb.scenes:
        if sc.type not in GENERATED_TYPES:
            continue
        meta = read_json(p.visuals_dir / f"{sc.id}.json") or {}
        tried = meta.get("attempts", [])
        if meta.get("accepted_by") == "operator":
            ocr = "operator"
        else:
            ocr = ("pass" if tried[-1].get("ok") else "review") if tried else None
        out.append({"scene": sc.id, "file": f"visuals/{sc.id}.png", "provider": meta.get("provider"),
                    "model": meta.get("model"), "prompt_hash": meta.get("fingerprint"), "attempts": len(tried),
                    "cached": sum(a.get("source") == "cache" for a in tried), "ocr": ocr, "afp": meta.get("afp", 0)})
    return out


def write_manifest(p: Project, sb: Storyboard, tl: Timeline, renders: list[dict], kind: str) -> Path:
    report = p.check()
    per_type: dict[str, int] = {}
    for c in sb.claims:
        per_type[c.type] = per_type.get(c.type, 0) + c.sentences[1] - c.sentences[0] + 1
    papers = p.sources()
    displays = {}
    for r in renders:
        displays.update(r["displays"])
    manifest = {
        "project": p.slug, "kind": kind, "rendered_at": now_iso(), "duration": tl.duration,
        "inputs": {"script_hash": sentences_hash([s.text for s in p.sentences()]),
                   "storyboard_hash": stable_hash(p.storyboard_data())[:16], "style_pack": STYLE_VERSION,
                   "voice": read_json(p.audio_dir / "voice.json", {}).get("engine")},
        "sources": [{"id": sid, "doi": paper.doi, "license": paper.license, "license_version": paper.license_version,
                     "license_note": describe_license(paper),
                     "display": {sc.id: displays.get(sc.id) for sc in sb.scenes
                                 if getattr(sc, "paper", None) == sid and sc.id in displays}}
                    for sid, paper in papers.items()],
        "scenes": [{"id": s.id, "type": s.type, "start": s.start, "end": s.end} for s in tl.scenes],
        "claims": {"sentences": len(tl.sentences), "by_type": per_type,
                   "excerpts_found": sum(r.status == "found" for r in report.evidence),
                   "excerpts": len(report.evidence)},
        "renders": renders,
        "labels": {"visible": renders[0]["ai_label"] if renders else None, "metadata": "AIGC"},
        "visuals": visuals_record(p, sb),
        "afp": quota.project_spend(p.slug),  # actual spend from the ledger: images, voice and text calls
    }
    path = p.output_dir / ("manifest.json" if kind == "final" else f"{kind}.manifest.json")
    write_json(path, manifest)
    return path
