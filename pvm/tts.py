"""Text-to-speech, one sentence at a time, with word timestamps and a content cache (spec §10.2).

Engines:
- edge: edge-tts, free, word boundaries included. Used for drafts and animatics.
- ark: Volcano Ark TTS through Agent Plan (V3 HTTP unidirectional stream: X-Api-Key + X-Api-Resource-Id,
  newline-delimited JSON with base64 audio, final code 20000000). Verified against the plan endpoint on
  2026-09-28: word timestamps come back only with audio_params.enable_subtitle, per character, in seconds,
  as sentence.words[{word, startTime, endTime}] with punctuation attached to the preceding character.
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

import httpx

from .config import Settings
from .schema import VoiceOptions
from .util import PvmError, data_dir, read_json, stable_hash, warn, write_bytes, write_json

CACHE_VERSION = 1


@dataclass
class Word:
    start: float  # seconds from the start of the clip
    end: float
    text: str


@dataclass
class Clip:
    audio: bytes
    words: list[Word] = field(default_factory=list)
    fmt: str = "mp3"


# ---------------------------------------------------------------- edge-tts

class EdgeEngine:
    name = "edge"

    def __init__(self, voice: str, rate: str):
        self.voice, self.rate = voice, rate

    def params(self) -> dict:
        return {"engine": self.name, "voice": self.voice, "rate": self.rate}

    async def _one(self, text: str) -> Clip:
        import edge_tts

        comm = edge_tts.Communicate(text, self.voice, rate=self.rate, boundary="WordBoundary")
        audio = bytearray()
        words: list[Word] = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # edge-tts reports 100-ns ticks
                words.append(Word(start, start + chunk["duration"] / 1e7, chunk["text"]))
        if not audio:
            raise PvmError(f"edge-tts returned no audio for: {text}")
        return Clip(bytes(audio), words)

    async def _retry(self, text: str, tries: int = 3) -> Clip:
        delay = 1.0
        for attempt in range(tries):
            try:
                return await self._one(text)
            except Exception as e:  # network, websocket and "no audio" errors are all worth a retry
                if attempt == tries - 1:
                    raise PvmError(f"edge-tts failed after {tries} tries: {e}") from e
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    def synthesize_many(self, texts: list[str], concurrency: int = 4) -> list[Clip]:
        async def run():
            gate = asyncio.Semaphore(concurrency)

            async def one(text):
                async with gate:
                    return await self._retry(text)

            return await asyncio.gather(*(one(t) for t in texts))

        return list(asyncio.run(run()))


# ---------------------------------------------------------------- Ark (Agent Plan)

def ark_resource_id(speaker: str) -> str:
    """The resource id must match the speaker family, or the API answers "resource ID is mismatched"."""
    if speaker.startswith("S_"):
        return "seed-icl-2.0"  # cloned voice
    if "_uranus_" in speaker or speaker.startswith("saturn_"):
        return "seed-tts-2.0"
    return "seed-tts-1.0"


def _ark_words(msg: dict) -> list[Word]:
    """Word timestamps from one response line, wherever this API version puts them."""
    holders = [msg.get("sentence"), msg.get("addition"), msg]
    items = None
    for h in holders:
        if isinstance(h, dict):
            frontend = h.get("frontend")
            if isinstance(frontend, str):
                try:
                    h = json.loads(frontend)
                except json.JSONDecodeError:
                    pass
            if isinstance(h, dict) and isinstance(h.get("words"), list):
                items = h["words"]
                break
    if not items:
        return []
    out = []
    for w in items:
        text = w.get("word") or w.get("text") or ""
        start = w.get("startTime", w.get("start_time", w.get("begin_time")))
        end = w.get("endTime", w.get("end_time"))
        if text and isinstance(start, (int, float)) and isinstance(end, (int, float)):
            out.append(Word(float(start), float(end), text))
    if out and max(w.end for w in out) > 120:  # milliseconds, not seconds
        out = [Word(w.start / 1000, w.end / 1000, w.text) for w in out]
    return out


class ArkEngine:
    name = "ark"

    def __init__(self, url: str, api_key: str, speaker: str, speed: int, instruction: str = ""):
        self.url, self.api_key, self.speaker, self.speed, self.instruction = url, api_key, speaker, speed, instruction

    def params(self) -> dict:
        return {"engine": self.name, "voice": self.speaker, "rate": self.speed, "instruction": self.instruction}

    def _one(self, client: httpx.Client, text: str) -> Clip:
        req = {"text": text, "speaker": self.speaker,
               "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": self.speed,
                                "enable_subtitle": True}}  # enable_timestamp returns empty words on this API
        if self.instruction:
            req["additions"] = json.dumps({"context_texts": [self.instruction]}, ensure_ascii=False)
        headers = {"X-Api-Key": self.api_key, "X-Api-Resource-Id": ark_resource_id(self.speaker),
                   "X-Api-Request-Id": str(uuid.uuid4())}
        audio = bytearray()
        words: list[Word] = []
        with client.stream("POST", self.url, json={"user": {"uid": "pvm"}, "req_params": req}, headers=headers) as r:
            if r.status_code != 200:
                body = r.read().decode("utf-8", "replace")[:300]
                raise PvmError(f"Ark TTS HTTP {r.status_code}: {body}")
            for line in r.iter_lines():
                line = line.strip()
                if line.startswith("data:"):  # the SSE flavour of the same stream
                    line = line[5:].strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                code = msg.get("code", 0)
                if code not in (0, 20000000):
                    raise PvmError(f"Ark TTS error {code}: {msg.get('message')}")
                if msg.get("data"):
                    audio += base64.b64decode(msg["data"])
                words += _ark_words(msg)
        if not audio:
            raise PvmError("Ark TTS returned no audio")
        return Clip(bytes(audio), words)

    def _retry(self, client: httpx.Client, text: str, tries: int = 3) -> Clip:
        for attempt in range(tries):
            try:
                return self._one(client, text)
            except httpx.HTTPError as e:
                if attempt == tries - 1:
                    raise PvmError(f"Ark TTS network error: {e}") from e
        raise AssertionError("unreachable")

    def synthesize_many(self, texts: list[str], concurrency: int = 3) -> list[Clip]:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                return list(pool.map(lambda t: self._retry(client, t), texts))


# ---------------------------------------------------------------- engine choice and cache

def make_engine(settings: Settings, opts: VoiceOptions | None = None, override: str | None = None):
    choice = override or (opts.engine if opts and opts.engine not in (None, "auto") else None) \
        or settings.resolved_tts_engine()
    speed = opts.speed if opts and opts.speed is not None else None
    speaker = opts.speaker if opts and opts.speaker else None
    if choice == "edge":
        voice = speaker if speaker and speaker.endswith("Neural") else settings.edge_voice
        return EdgeEngine(voice, f"{speed:+d}%" if speed is not None else settings.edge_rate)
    if choice == "ark":
        if not settings.api_key:
            raise PvmError("Ark TTS needs AGENT_PLAN_API_KEY in .env (or use PVM_TTS_ENGINE=edge)")
        voice = speaker if speaker and not speaker.endswith("Neural") else settings.tts_speaker
        return ArkEngine(settings.tts_url, settings.api_key, voice,
                         speed if speed is not None else settings.tts_speed, settings.tts_instruction)
    raise PvmError(f"unknown TTS engine '{choice}' (use edge or ark)")


def _cache_dir():
    return data_dir("cache") / "tts"


def cache_key(params: dict, text: str) -> str:
    return stable_hash({**params, "text": text, "v": CACHE_VERSION})[:24]


def _load(key: str) -> Clip | None:
    meta = read_json(_cache_dir() / f"{key}.json")
    if not meta:
        return None
    audio_path = _cache_dir() / f"{key}.{meta.get('fmt', 'mp3')}"
    if not audio_path.exists():
        return None
    return Clip(audio_path.read_bytes(), [Word(**w) for w in meta.get("words", [])], meta.get("fmt", "mp3"))


def _store(key: str, clip: Clip, params: dict, text: str) -> None:
    write_bytes(_cache_dir() / f"{key}.{clip.fmt}", clip.audio)
    write_json(_cache_dir() / f"{key}.json", {"fmt": clip.fmt, "params": params, "text": text,
                                              "words": [asdict(w) for w in clip.words]})


def synthesize(engine, texts: list[str]) -> tuple[list[Clip], int]:
    """Clips for every text, from the cache where possible. Returns (clips, number newly synthesized)."""
    params = engine.params()
    keys = [cache_key(params, t) for t in texts]
    clips: list[Clip | None] = [_load(k) for k in keys]
    todo = [i for i, c in enumerate(clips) if c is None]
    if todo:
        fresh = engine.synthesize_many([texts[i] for i in todo])
        for i, clip in zip(todo, fresh):
            _store(keys[i], clip, params, texts[i])
            clips[i] = clip
    return [c for c in clips if c is not None], len(todo)


def synthesize_with_fallback(settings: Settings, opts: VoiceOptions | None, texts: list[str],
                             override: str | None = None):
    """Synthesize with the configured engine. In auto mode, if Ark fails outright, redo everything with
    edge-tts: one video must never mix two voices."""
    engine = make_engine(settings, opts, override)
    auto = override is None and (opts is None or opts.engine in (None, "auto")) and settings.tts_engine == "auto"
    try:
        clips, n = synthesize(engine, texts)
        return engine, clips, n
    except PvmError as e:
        if not (auto and engine.name == "ark"):
            raise
        warn(f"Ark TTS failed ({e}); using edge-tts for this video instead")
        engine = make_engine(settings, opts, "edge")
        clips, n = synthesize(engine, texts)
        return engine, clips, n
