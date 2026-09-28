"""Timeline: when each sentence, subtitle cue, scene, panel focus, highlight, hook and source chip happens.

Everything is derived from the real voice timing (spec §10.1); nothing is scheduled before the voice exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .schema import Storyboard
from .script import subtitle_chunks, word_starts
from .voice import SentenceAudio, VoiceTrack

SUBTITLE_CHARS = 14  # spec §10.3
HOLD_AFTER_SENTENCE = 0.4  # a cue stays up this long into the pause, unless the next sentence starts sooner
HOOK_DEFAULT_SENTENCES = 2
FOCUS_LEAD = 0.15  # panel focus moves slightly before the narration reaches it


@dataclass
class Cue:
    start: float
    end: float
    text: str
    sentence: int


@dataclass
class SceneTiming:
    id: str
    type: str
    start: float
    end: float
    focus: list[list] = field(default_factory=list)  # [[section_index, start_time], ...]
    highlights: list[list] = field(default_factory=list)  # [[text, start_time], ...]
    title_highlight: float | None = None


@dataclass
class Timeline:
    duration: float
    sentences: list[SentenceAudio]
    cues: list[Cue]
    scenes: list[SceneTiming]
    hook: list[float]  # [start, end]
    facts: list[dict]  # source_fact spans: {"start", "end", "sources"}

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Timeline":
        return cls(d["duration"], [SentenceAudio(**s) for s in d["sentences"]], [Cue(**c) for c in d["cues"]],
                   [SceneTiming(**s) for s in d["scenes"]], d["hook"], d["facts"])

    def scene_at(self, t: float) -> SceneTiming:
        for sc in self.scenes:
            if sc.start <= t < sc.end:
                return sc
        return self.scenes[-1]

    def cue_at(self, t: float) -> Cue | None:
        for c in self.cues:
            if c.start <= t < c.end:
                return c
        return None


def char_time(s: SentenceAudio, offset: int) -> float:
    """Time at which the voice reaches character `offset`: piecewise-linear over the word timings,
    proportional to characters where the engine gave none."""
    anchors = [(0, s.start)]
    for t0, t1, c0, c1 in s.words:
        anchors += [(c0, t0), (c1, t1)]
    anchors.append((len(s.text), s.end))
    anchors.sort(key=lambda a: a[0])
    fixed, latest = [], s.start
    for c, t in anchors:  # times must never run backwards
        latest = max(latest, min(t, s.end))
        fixed.append((c, latest))
    for (c0, t0), (c1, t1) in zip(fixed, fixed[1:]):
        if c0 <= offset <= c1:
            return t0 if c1 == c0 else t0 + (t1 - t0) * (offset - c0) / (c1 - c0)
    return s.end


def build_cues(sentences: list[SentenceAudio], max_chars: int = SUBTITLE_CHARS) -> list[Cue]:
    cues: list[Cue] = []
    for i, s in enumerate(sentences):
        bounds = word_starts(s.text) or ({w[2] for w in s.words} or None)
        chunks = subtitle_chunks(s.text, max_chars, bounds)
        if not chunks:
            continue
        starts = [s.start] + [char_time(s, a) for a, _, _ in chunks[1:]]
        nxt = sentences[i + 1].start if i + 1 < len(sentences) else s.end + 0.8
        last_end = min(nxt, s.end + HOLD_AFTER_SENTENCE)
        for k, (_, _, text) in enumerate(chunks):
            end = starts[k + 1] if k + 1 < len(chunks) else last_end
            cues.append(Cue(round(starts[k], 3), round(max(end, starts[k] + 0.05), 3), text, s.n))
    return cues


def _sentence(sentences: list[SentenceAudio], n: int) -> SentenceAudio:
    return sentences[min(max(n, 1), len(sentences)) - 1]


def build_timeline(sb: Storyboard, track: VoiceTrack) -> Timeline:
    ss = track.sentences
    scenes: list[SceneTiming] = []
    for k, sc in enumerate(sb.scenes):
        a, b = sc.sentences
        start = 0.0 if k == 0 else round((_sentence(ss, a - 1).end + _sentence(ss, a).start) / 2, 3)
        scenes.append(SceneTiming(sc.id, sc.type, start, 0.0))
    for k, timing in enumerate(scenes):
        timing.end = scenes[k + 1].start if k + 1 < len(scenes) else track.duration

    for sc, timing in zip(sb.scenes, scenes):
        if sc.type in ("poster", "summary"):
            n = len(sc.sections)
            for i, sec in enumerate(sc.sections):
                if sec.at:
                    t = _sentence(ss, sec.at).start - FOCUS_LEAD
                else:
                    t = timing.start + (timing.end - timing.start) * i / n
                timing.focus.append([i, round(max(timing.start, t), 3)])
        elif sc.type == "paper":
            if sc.highlight_title:
                timing.title_highlight = round(timing.start + 0.6, 3)
            for i, h in enumerate(sc.highlights):
                t = _sentence(ss, h.at).start if h.at else timing.start + 1.4 + 1.2 * i
                timing.highlights.append([h.text, round(max(timing.start, t), 3)])

    hook_n = sb.hook_until or min(HOOK_DEFAULT_SENTENCES, len(ss))
    hook_end = min(_sentence(ss, hook_n).end + 0.3, scenes[0].end)
    first_marks = [t for _, t in scenes[0].highlights]
    if first_marks:  # the hook sits over the page, so it gives way to the first highlighted evidence
        hook_end = min(hook_end, max(min(first_marks), 1.5))

    facts = []
    for c in sb.claims:
        if c.type == "source_fact":
            facts.append({"start": _sentence(ss, c.sentences[0]).start, "end": _sentence(ss, c.sentences[1]).end,
                          "sources": sorted({ev.source for ev in c.evidence})})
    return Timeline(track.duration, ss, build_cues(ss), scenes, [0.0, round(hook_end, 3)], facts)


def srt(cues: list[Cue]) -> str:
    def stamp(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = [f"{i}\n{stamp(c.start)} --> {stamp(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)]
    return "\n".join(blocks)
