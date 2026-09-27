"""Shared helpers: console encoding, JSON/text IO, hashing, ffmpeg and subprocess wrappers."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


class PvmError(RuntimeError):
    """Expected, user-facing failure: the CLI prints the message without a traceback."""


def setup_console() -> None:
    # Windows consoles default to a legacy code page; Chinese output would crash print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def log(msg: str = "") -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"[warn] {msg}", flush=True)


# ---------------------------------------------------------------- files

def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path) -> str:
    # utf-8-sig tolerates the BOM that Windows PowerShell 5.1 writes.
    return Path(path).read_text(encoding="utf-8-sig")


def write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise PvmError(f"{path} is not valid JSON: {e}") from e


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- hashing / naming

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(obj: Any) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(text: str, fallback: str = "item") -> str:
    """ASCII-only folder-safe slug. Chinese-only input falls back to a short hash."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)[:48].strip("-")
    if len(s) < 3:
        s = f"{fallback}-{sha256_bytes(text.encode('utf-8'))[:6]}"
    return s


def fmt_seconds(sec: float) -> str:
    sec = max(0.0, sec)
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


# ---------------------------------------------------------------- ffmpeg / processes

def ffmpeg_exe() -> str:
    env = os.environ.get("FFMPEG_PATH")
    if env and Path(env).exists():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover - depends on install
        raise PvmError("FFmpeg not found. Run setup.ps1 (installs imageio-ffmpeg) or set FFMPEG_PATH.") from e


def run(cmd: list[str], *, input: bytes | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, input=input, capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise PvmError(f"Command not found: {cmd[0]}") from e
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-12:]
        raise PvmError(f"Command failed ({Path(cmd[0]).name}):\n" + "\n".join(err))
    return proc


def decode_audio(path: Path, sample_rate: int = 44100):
    """Decode any audio file to mono float32 numpy samples via ffmpeg."""
    import numpy as np

    proc = run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path),
                "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"])
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def write_wav(path: Path, samples, sample_rate: int = 44100) -> None:
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    ensure_dir(Path(path).parent)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def media_duration(path: Path) -> float:
    """Container duration in seconds (parsed from ffmpeg's stream summary)."""
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr.decode("utf-8", "replace"))
    if not m:
        raise PvmError(f"Could not read duration of {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)
