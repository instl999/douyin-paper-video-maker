"""Script handling: sentence splitting (the storyboard's unit) and subtitle chunking."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

SENT_END = "。！？!?…"
CLOSERS = "”’」』）)】》\"'"
CLAUSE_BREAKS = "，,、；;：:—"
# Never shown in subtitles (the benchmark videos show bare text).
STRIP_CHARS = set("，,。.、；;：:！!？?…—“”‘’\"'「」『』（）()【】《》〈〉·~～")
_DIGIT_PUNCT = re.compile(r"(?<=\d)[.,:](?=\d)")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]")


@dataclass
class Sentence:
    n: int  # 1-based
    text: str
    para_end: bool  # last sentence of a paragraph (longer pause after it)


def clean_script(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for ch in ("​", "﻿", " "):
        text = text.replace(ch, " " if ch == " " else "")
    out: list[str] = []
    for line in (ln.strip() for ln in text.split("\n")):
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def speakable_len(s: str) -> int:
    return sum(1 for ch in s if ch.isalnum())


def split_sentences(text: str) -> list[Sentence]:
    raw: list[tuple[str, bool]] = []
    for para in clean_script(text).split("\n"):
        para = para.strip()
        if not para:
            continue
        parts: list[str] = []
        buf = ""
        i = 0
        while i < len(para):
            buf += para[i]
            if para[i] in SENT_END:
                while i + 1 < len(para) and (para[i + 1] in SENT_END or para[i + 1] in CLOSERS):
                    i += 1
                    buf += para[i]
                parts.append(buf.strip())
                buf = ""
            i += 1
        if buf.strip():
            parts.append(buf.strip())
        # A fragment without speakable characters (e.g. a lone quote) joins its neighbour.
        merged: list[str] = []
        for p in parts:
            if merged and speakable_len(p) < 2:
                merged[-1] += p
            else:
                merged.append(p)
        raw.extend((p, i == len(merged) - 1) for i, p in enumerate(merged))
    return [Sentence(n=i + 1, text=t, para_end=end) for i, (t, end) in enumerate(raw)]


def display_text(s: str) -> str:
    protected = _DIGIT_PUNCT.sub(lambda m: {".": "\x01", ",": "\x02", ":": "\x03"}[m.group()], s)
    out = "".join(ch for ch in protected if ch not in STRIP_CHARS)
    out = out.replace("\x01", ".").replace("\x02", ",").replace("\x03", ":")
    return re.sub(r"\s{2,}", " ", out).strip()


def _width(s: str) -> float:
    """Visual width in CJK character units (Latin letters are narrower)."""
    return sum(0.55 if ch.isascii() else 1.0 for ch in s if not ch.isspace()) + 0.3 * sum(ch.isspace() for ch in s)


def subtitle_chunks(sentence: str, max_chars: int = 14, boundaries: set[int] | None = None) -> list[tuple[int, int, str]]:
    """Split a sentence into subtitle chunks.

    Returns (start, end, display) with char offsets into `sentence`. `boundaries` holds char offsets
    where TTS word tokens start; long clauses are cut there so Chinese words stay intact.
    """
    clauses: list[tuple[int, int]] = []
    start = 0
    for i, ch in enumerate(sentence):
        if ch in CLAUSE_BREAKS or ch in SENT_END:
            if display_text(sentence[start:i]):
                clauses.append((start, i))
            start = i + 1
    if display_text(sentence[start:]):
        clauses.append((start, len(sentence)))
    if not clauses:
        return []

    # Very short clauses ("那么，") read better merged with the following one.
    merged: list[tuple[int, int]] = []
    for a, b in clauses:
        if merged:
            pa, pb = merged[-1]
            short_prev = _width(display_text(sentence[pa:pb])) <= 3
            fits = _width(display_text(sentence[pa:b])) <= max_chars
            if short_prev and fits:
                merged[-1] = (pa, b)
                continue
        merged.append((a, b))

    chunks: list[tuple[int, int, str]] = []
    for a, b in merged:
        for ca, cb in _split_long(sentence, a, b, max_chars, boundaries):
            text = display_text(sentence[ca:cb])
            if text:
                chunks.append((ca, cb, text))
    return chunks


def _split_long(s: str, a: int, b: int, max_chars: int, boundaries: set[int] | None) -> list[tuple[int, int]]:
    width = _width(display_text(s[a:b]))
    if width <= max_chars:
        return [(a, b)]
    pieces = math.ceil(width / max_chars)
    cuts = [a]
    for k in range(1, pieces):
        target = a + (b - a) * k / pieces
        best, best_cost = None, float("inf")
        for pos in range(max(cuts[-1] + 2, a + 1), b - 1):
            if _ASCII_WORD.match(s[pos - 1]) and _ASCII_WORD.match(s[pos]):
                continue  # never split inside a Latin word or number
            cost = abs(pos - target)
            if boundaries is not None and pos not in boundaries:
                cost += 2.5
            if cost < best_cost:
                best, best_cost = pos, cost
        if best is not None:
            cuts.append(best)
    cuts.append(b)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
