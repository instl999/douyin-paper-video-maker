"""Voice track: per-sentence TTS clips, trimmed and joined with pauses into audio/voice.wav (spec §10.2).

Every sentence keeps its own start/end time and word timings mapped to character offsets, which the
timeline uses for subtitle cues, scene cuts, panel focus and highlights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .config import get_settings
from .project import Project
from .schema import VoiceOptions
from .tts import Word, synthesize_with_fallback
from .util import decode_audio_bytes, log, read_json, write_json, write_wav

SAMPLE_RATE = 44100
LEAD_IN = 0.3  # silence before the first word
TAIL = 1.0  # silence after the last word
GAP = 0.25  # between sentences
PARA_GAP = 0.5  # after a paragraph
SILENCE_DB = -45.0
KEEP_BEFORE, KEEP_AFTER = 0.04, 0.06  # seconds of silence kept around trimmed speech
PUNCTUATION = "，。、；：！？…—“”‘’「」『』（）《》〈〉·,.;:!?\"'()[] "


@dataclass
class SentenceAudio:
    n: int
    text: str
    start: float
    end: float
    para_end: bool
    words: list[list] = field(default_factory=list)  # [t0, t1, char_start, char_end], absolute seconds


@dataclass
class VoiceTrack:
    path: str
    duration: float
    engine: dict
    sentences: list[SentenceAudio]

    @classmethod
    def from_json(cls, data: dict) -> "VoiceTrack":
        return cls(data["path"], data["duration"], data["engine"], [SentenceAudio(**s) for s in data["sentences"]])


def trim_silence(samples: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[np.ndarray, float]:
    """Cut leading/trailing silence (TTS engines pad clips unevenly). Returns (samples, seconds cut at start)."""
    if not len(samples):
        return samples, 0.0
    loud = np.flatnonzero(np.abs(samples) > 10 ** (SILENCE_DB / 20))
    if not len(loud):
        return samples, 0.0
    a = max(0, int(loud[0]) - int(KEEP_BEFORE * sr))
    b = min(len(samples), int(loud[-1]) + int(KEEP_AFTER * sr))
    return samples[a:b], a / sr


def align_words(text: str, words: list[Word], offset: float, duration: float) -> list[list]:
    """Map engine word tokens onto character offsets of the sentence, in order.

    Tokens the engine normalized (e.g. digits read out) are skipped; the timeline interpolates over gaps.
    """
    out: list[list] = []
    cursor = 0
    for w in words:
        # Engines attach punctuation to the word before it ("好，"); match the spoken characters only.
        token = w.text.strip().strip(PUNCTUATION)
        if not token:
            continue
        i = text.find(token, cursor, cursor + len(token) + 8)
        if i < 0:
            continue
        t0 = min(max(w.start - offset, 0.0), duration)
        t1 = min(max(w.end - offset, t0), duration)
        out.append([round(t0, 3), round(t1, 3), i, i + len(token)])
        cursor = i + len(token)
    return out


def build_voice(p: Project, opts: VoiceOptions | None = None, engine: str | None = None,
                force: bool = False) -> VoiceTrack:
    """Synthesize (cached) and assemble audio/voice.wav; skipped when nothing changed."""
    settings = get_settings()
    sentences = p.sentences()
    texts = [s.text for s in sentences]
    track_path = p.audio_dir / "voice.json"
    wav = p.audio_dir / "voice.wav"

    eng, clips, fresh = synthesize_with_fallback(settings, opts, texts, engine, project=p.slug)
    inputs = {"engine": eng.params(), "sentences": [[s.text, s.para_end] for s in sentences],
              "timing": [LEAD_IN, TAIL, GAP, PARA_GAP, SILENCE_DB, SAMPLE_RATE]}
    cached = read_json(track_path)
    if not force and cached and wav.exists() and p.is_fresh("voice", inputs):
        return VoiceTrack.from_json(cached)

    pieces = [np.zeros(int(LEAD_IN * SAMPLE_RATE), dtype=np.float32)]
    t = LEAD_IN
    out: list[SentenceAudio] = []
    for k, (s, clip) in enumerate(zip(sentences, clips)):
        samples, cut = trim_silence(decode_audio_bytes(clip.audio, SAMPLE_RATE))
        dur = len(samples) / SAMPLE_RATE
        words = [[t + a, t + b, c0, c1] for a, b, c0, c1 in align_words(s.text, clip.words, cut, dur)]
        out.append(SentenceAudio(s.n, s.text, round(t, 3), round(t + dur, 3), s.para_end,
                                 [[round(a, 3), round(b, 3), c0, c1] for a, b, c0, c1 in words]))
        pieces.append(samples.astype(np.float32))
        t += dur
        if k < len(sentences) - 1:
            gap = PARA_GAP if s.para_end else GAP
            pieces.append(np.zeros(int(round(gap * SAMPLE_RATE)), dtype=np.float32))
            t += gap
    pieces.append(np.zeros(int(TAIL * SAMPLE_RATE), dtype=np.float32))
    audio = np.concatenate(pieces)
    write_wav(wav, audio, SAMPLE_RATE)
    track = VoiceTrack(str(wav.relative_to(p.dir)), round(len(audio) / SAMPLE_RATE, 3), eng.params(), out)
    write_json(track_path, asdict(track))
    p.set_stamp("voice", inputs, engine=eng.name, synthesized=fresh)
    log(f"voice: {len(out)} sentences, {track.duration:.1f} s ({eng.name}, {fresh} newly synthesized)")
    return track
