"""Automated output QA against the spec's acceptance criteria (§13.1, §17)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .project import Project
from .render.style import layout
from .util import PvmError, ffmpeg_exe, now_iso, read_json, write_json

MAX_FROZEN = 5.0  # seconds with nothing moving above the subtitle band
LOUDNESS_RANGE = (-13.0, -11.0)  # integrated LUFS
MAX_TRUE_PEAK = -0.5  # dBTP after AAC encoding (the target is -1)


def _ffmpeg(args: list[str]) -> str:
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", *args], capture_output=True)
    return proc.stderr.decode("utf-8", "replace")


def probe(path: Path) -> dict:
    text = _ffmpeg(["-i", str(path)])
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if not m:
        raise PvmError(f"cannot read {path}")
    video = re.search(r"Video: (\w+).*?, (\d+)x(\d+)", text)
    meta = {k.strip(): v.strip() for k, v in re.findall(r"^\s{4}(\w+)\s*:\s(.*)$", text, re.M)}
    return {"duration": int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)),
            "video": {"codec": video.group(1), "width": int(video.group(2)), "height": int(video.group(3))} if video else None,
            "audio": bool(re.search(r"Stream #\d+:\d+.*Audio:", text)), "metadata": meta}


def loudness(path: Path) -> dict:
    text = _ffmpeg(["-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", text)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", text)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbtp": float(tp[-1]) if tp else None}


def motion(path: Path, ratio: str, duration: float) -> dict:
    """Frozen stretches and black gaps, measured above the subtitle band (same method as spec §2.5)."""
    L = layout(ratio)
    x, y, w, h = L.content
    band_top = L.subtitle_cy - L.s(70)
    crop = f"crop={w}:{band_top - y}:{x}:{y}"
    text = _ffmpeg(["-i", str(path), "-an", "-vf",
                    f"{crop},scale=270:-2,freezedetect=n=0.001:d=2,blackdetect=d=0.2:pix_th=0.10", "-f", "null", "-"])
    starts = [float(v) for v in re.findall(r"freeze_start: ([\d.]+)", text)]
    ends = [float(v) for v in re.findall(r"freeze_end: ([\d.]+)", text)]
    if len(ends) < len(starts):
        ends.append(duration)
    frozen = [(a, b) for a, b in zip(starts, ends)]
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", text)]
    longest = max((b - a for a, b in frozen), default=0.0)
    return {"longest_frozen_s": round(longest, 2), "frozen": [[round(a, 2), round(b, 2)] for a, b in frozen],
            "black": [[round(a, 2), round(b, 2)] for a, b in blacks]}


def run_qa(p: Project, ratio: str = "3x4", kind: str = "final", path: Path | None = None) -> dict:
    path = path or p.output_dir / f"{kind}_{ratio}.mp4"
    if not path.exists():
        raise PvmError(f"{path} does not exist; render it first")
    timeline = read_json(p.audio_dir / "timeline.json") or {}
    expected = timeline.get("duration")
    info = probe(path)
    loud = loudness(path)
    mov = motion(path, ratio, info["duration"])
    L = layout(ratio)
    checks = [
        ("duration", expected is not None and abs(info["duration"] - expected) <= 0.35,
         f"{info['duration']:.2f} s (timeline {expected} s)"),
        ("streams", bool(info["video"]) and info["audio"]
         and (info["video"]["width"], info["video"]["height"]) == (L.width, L.height),
         f"video {info['video']}, audio {info['audio']}"),
        ("loudness", loud["integrated_lufs"] is not None
         and LOUDNESS_RANGE[0] <= loud["integrated_lufs"] <= LOUDNESS_RANGE[1],
         f"{loud['integrated_lufs']} LUFS (target -12)"),
        ("true_peak", loud["true_peak_dbtp"] is not None and loud["true_peak_dbtp"] <= MAX_TRUE_PEAK,
         f"{loud['true_peak_dbtp']} dBTP (target -1)"),
        ("motion", mov["longest_frozen_s"] <= MAX_FROZEN, f"longest frozen stretch {mov['longest_frozen_s']} s"),
        ("black_frames", not mov["black"], f"{len(mov['black'])} black gap(s)"),
        ("aigc_metadata", "AIGC" in info["metadata"], "AIGC record in the MP4 metadata"),
    ]
    result = {"file": str(path), "checked_at": now_iso(), "passed": all(ok for _, ok, _ in checks),
              "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
              "probe": info, "loudness": loud, "motion": mov}
    write_json(p.output_dir / f"qa_{kind}_{ratio}.json", result)
    manifest_path = p.output_dir / ("manifest.json" if kind == "final" else f"{kind}.manifest.json")
    manifest = read_json(manifest_path)
    if manifest is not None:
        manifest.setdefault("qa", {})[ratio] = {"passed": result["passed"],
                                                "checks": {c["name"]: c["ok"] for c in result["checks"]}}
        write_json(manifest_path, manifest)
    return result
