"""Evidence: find claim excerpts in the source text, and decide how much of a paper may be shown.

Spec §6.4 (verification ladder) and §6.6 (showing paper pages).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .schema import Paper, Storyboard
from .util import PvmError, read_text

OPEN_LICENSES = {"cc-by", "cc-by-sa", "cc0", "public-domain"}
Display = Literal["page", "title_crop", "card"]
Status = Literal["found", "not_found", "unverifiable", "unknown_source"]

_PLAIN = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-", " ": " ", "­": "",
})
_LINE_HYPHEN = re.compile(r"(\w)-[ \t]*\r?\n\s*(\w)")  # "behav-\nior" -> "behavior"
_NON_WORD = re.compile(r"[\W_]+")


def normalize(text: str) -> str:
    """Comparable text: NFKC (resolves ligatures such as "ﬁ" and full-width forms), line-break hyphenation
    removed, plain quotes and dashes, whitespace collapsed, lower case."""
    text = unicodedata.normalize("NFKC", text).translate(_PLAIN)
    text = _LINE_HYPHEN.sub(r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def loose(text: str) -> str:
    """Letters and digits only. Tolerates the spacing and punctuation noise of PDF text extraction while
    still requiring the same words in the same order."""
    return _NON_WORD.sub("", normalize(text))


def _mapped(raw: str, letters_only: bool) -> tuple[str, list[int]]:
    """Normalized text plus, for each of its characters, the index of the raw character it came from."""
    out: list[str] = []
    index: list[int] = []
    space = True
    for i, ch in enumerate(raw):
        for c in unicodedata.normalize("NFKC", ch).translate(_PLAIN).lower():
            if letters_only:
                if c.isalnum():
                    out.append(c)
                    index.append(i)
            elif c.isspace():
                if not space:
                    out.append(" ")
                    index.append(i)
                    space = True
            else:
                out.append(c)
                index.append(i)
                space = False
    return "".join(out), index


def locate(raw: str, query: str) -> tuple[int, int] | None:
    """[start, end) of `query` in `raw`, tolerant of thin spaces, ligatures, case and line-break hyphenation.

    PDF page text often differs from the words a person types (e.g. "21\\u2009billion"); indices refer to
    `raw`, so they map straight onto the PDF's character boxes.
    """
    for letters_only in (False, True):
        text, index = _mapped(raw, letters_only)
        q, _ = _mapped(query, letters_only)
        q = q.strip()
        pos = text.find(q) if q else -1
        if pos >= 0:
            return index[pos], index[pos + len(q) - 1] + 1
    return None


# ---------------------------------------------------------------- source text

def pdf_text(path: Path) -> str:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as e:  # pypdfium2 raises PdfiumError for damaged or encrypted files
        raise PvmError(f"could not open {path}: {e}") from e
    try:
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return "\n".join(pages)
    finally:
        pdf.close()


@dataclass
class SourceText:
    """Everything an excerpt may be quoted from: title, abstract, and the full text when available."""

    source_id: str
    parts: dict[str, str] = field(default_factory=dict)  # "title" / "abstract" / "pdf" / "txt" -> raw text
    _norm: dict[str, tuple[str, str]] = field(default_factory=dict, repr=False)

    @property
    def has_pdf(self) -> bool:
        return "pdf" in self.parts

    @property
    def has_full_text(self) -> bool:
        return any(self.parts.get(k, "").strip() for k in ("pdf", "txt"))

    def find(self, excerpt: str) -> tuple[str | None, str | None]:
        """(match, part): match is "exact" or "loose", part is where it was found; (None, None) if absent."""
        exact, rough = normalize(excerpt), loose(excerpt)
        for name, raw in self.parts.items():
            if name not in self._norm:
                self._norm[name] = (normalize(raw), loose(raw))
            norm_text, loose_text = self._norm[name]
            if exact and exact in norm_text:
                return "exact", name
            if rough and rough in loose_text:
                return "loose", name
        return None, None


def load_source_text(source_id: str, paper: Paper | None, sources_dir: Path) -> SourceText:
    parts: dict[str, str] = {}
    if paper is not None:
        parts["title"] = paper.title or ""
        if paper.abstract:
            parts["abstract"] = paper.abstract
    pdf = sources_dir / f"{source_id}.pdf"
    if pdf.exists():
        parts["pdf"] = pdf_text(pdf)
    txt = sources_dir / f"{source_id}.txt"
    if txt.exists():
        parts["txt"] = read_text(txt)
    return SourceText(source_id, parts)


# ---------------------------------------------------------------- verification

@dataclass
class EvidenceResult:
    where: str
    source: str
    excerpt: str
    status: Status
    part: str | None = None  # where the excerpt was found
    match: str | None = None  # "exact" or "loose"


def verify(sb: Storyboard, texts: dict[str, SourceText]) -> list[EvidenceResult]:
    items = [("hook_claim", ev) for ev in (sb.hook_claim.evidence if sb.hook_claim else [])]
    for i, claim in enumerate(sb.claims, 1):
        items += [(f"claims[{i}]", ev) for ev in claim.evidence]
    results = []
    for where, ev in items:
        text = texts.get(ev.source)
        if text is None:
            results.append(EvidenceResult(where, ev.source, ev.excerpt, "unknown_source"))
            continue
        match, part = text.find(ev.excerpt)
        if match:
            status: Status = "found"
        elif text.has_full_text:
            status = "not_found"
        else:
            status = "unverifiable"
        results.append(EvidenceResult(where, ev.source, ev.excerpt, status, part, match))
    return results


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------- showing pages (spec §6.6)

def is_open(paper: Paper | None) -> bool:
    """Openly licensed *published version*: its pages may be shown in full."""
    return bool(paper and (paper.license or "").lower() in OPEN_LICENSES and paper.license_version == "publishedVersion")


def display_policy(paper: Paper | None, has_pdf: bool) -> Display:
    if not has_pdf:
        return "card"
    return "page" if is_open(paper) else "title_crop"


def describe_license(paper: Paper | None) -> str:
    if paper is None:
        return "unknown source"
    if is_open(paper):
        return f"{paper.license}, published version"
    if paper.license:
        return f"{paper.license} ({paper.license_version or 'version unknown'})"
    return paper.oa_status or ("open access" if paper.is_oa else "closed or unknown license")


def check_evidence(sb: Storyboard, texts: dict[str, SourceText], papers: dict[str, Paper], *,
                   strict: bool) -> tuple[list[str], list[str], list[EvidenceResult]]:
    """Excerpt lookup plus page-display rights. Unknown sources are reported by schema.check_storyboard."""
    errors: list[str] = []
    warnings: list[str] = []
    results = verify(sb, texts)
    for r in results:
        if r.status == "not_found":
            errors.append(f"{r.where}: excerpt not found in {r.source} (title, abstract and full text searched); "
                          f"excerpts must be verbatim: '{_short(r.excerpt)}'")
        elif r.status == "unverifiable":
            msg = (f"{r.where}: excerpt is not in {r.source}'s title or abstract, and there is no full text to "
                   f"search; add sources/{r.source}.pdf or sources/{r.source}.txt: '{_short(r.excerpt)}'")
            (errors if strict else warnings).append(msg)
    for sid, text in texts.items():
        if text.has_pdf and not text.parts["pdf"].strip():
            warnings.append(f"sources/{sid}.pdf has no text layer (scanned?); add sources/{sid}.txt with its text "
                            "so excerpts can be verified")

    for sc in sb.scenes:
        if sc.type not in ("paper", "paper_scroll") or sc.rights == "permitted":
            continue
        paper = papers.get(sc.paper)
        text = texts.get(sc.paper)
        policy = display_policy(paper, bool(text and text.has_pdf))
        full_page = sc.type == "paper_scroll" or sc.source == "pdf"
        if full_page and policy != "page":
            what = "paper_scroll shows whole pages" if sc.type == "paper_scroll" else "source 'pdf' shows the full page"
            msg = (f"{sc.id}: {what}, but {sc.paper} is not an openly licensed published version "
                   f"({describe_license(paper)}); use a paper scene with source 'auto' (title region), or set "
                   "\"rights\": \"permitted\" if you hold permission")
            (errors if strict else warnings).append(msg)
    return errors, warnings, results
