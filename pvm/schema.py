"""Data models: paper metadata and the storyboard the agent authors (storyboard.json)."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .script import sentences_hash

# ---------------------------------------------------------------- paper


def _family_name(name: str) -> str:
    name = name.strip()
    if "," in name:
        return name.split(",", 1)[0].strip()
    parts = name.split()
    return parts[-1] if parts else name


def _initials(name: str) -> str:
    name = name.strip()
    if "," in name:
        given = name.split(",", 1)[1]
    else:
        given = " ".join(name.split()[:-1])
    out = []
    for token in re.split(r"[\s.]+", given):
        if token:
            out.append("-".join(p[0].upper() + "." for p in token.split("-") if p))
    return " ".join(out)


class Paper(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_urls: list[str] = Field(default_factory=list)
    abstract: str | None = None
    cited_by: int | None = None
    type: str | None = None
    is_oa: bool | None = None  # from OpenAlex/Unpaywall; a Crossref PDF link is not evidence of open access
    oa_status: str | None = None  # gold / hybrid / green / bronze / closed
    license: str | None = None  # license of the best open-access copy, e.g. "cc-by"
    license_version: str | None = None  # which version that license covers, e.g. "publishedVersion"
    openalex_id: str | None = None
    origin: str | None = None

    @property
    def doi_url(self) -> str | None:
        return f"https://doi.org/{self.doi}" if self.doi else None

    def author_short(self) -> str:
        names = [_family_name(a) for a in self.authors if a.strip()]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} & {names[1]}"
        return f"{names[0]} et al."

    def short_ref(self) -> str:
        who = self.author_short() or "Unknown"
        return f"{who}, {self.year}" if self.year else who

    def citation(self) -> str:
        """APA-like reference string for descriptions and end cards."""
        names = [a for a in self.authors if a.strip()]
        formatted = [f"{_family_name(a)}, {_initials(a)}".strip().rstrip(",") for a in names[:6]]
        if len(names) > 6:
            who = ", ".join(formatted) + ", et al."
        elif len(formatted) > 1:
            who = ", ".join(formatted[:-1]) + ", & " + formatted[-1]
        else:
            who = formatted[0] if formatted else "Unknown"
        parts = [f"{who} ({self.year or 'n.d.'}). {self.title.rstrip('.')}."]
        if self.venue:
            venue = self.venue
            if self.volume:
                venue += f", {self.volume}"
                if self.issue:
                    venue += f"({self.issue})"
            if self.pages:
                venue += f", {self.pages}"
            parts.append(venue + ".")
        if self.doi:
            parts.append(f"https://doi.org/{self.doi}")
        elif self.url:
            parts.append(self.url)
        return " ".join(parts)


# ---------------------------------------------------------------- storyboard

# Soft limits (characters). Longer text still works but reads badly on a phone screen.
LIMITS = {"hook_line": 7, "title": 8, "heading": 7, "label": 7, "labels": 4, "visual": 60}
EXCERPT_MIN_TOKENS = 6  # words or CJK characters; shorter quotes match too easily to count as evidence
EXCERPT_LONG_CHARS = 400

# Research wording in a sentence that is not labeled source_fact is worth a second look (spec §6.4).
_RESEARCH = re.compile(
    r"研究|实验|论文|期刊|学者|科学家|数据显示|数据表明|调查显示|被试|受试者|参与者|样本|显著|证实|元分析|meta分析|"
    r"百分之|\d+(?:\.\d+)?\s*%|\bstud(?:y|ies)\b|\bexperiments?\b|\bparticipants\b|\bfound that\b",
    re.I,
)
_TOKENS = re.compile(r"[A-Za-z0-9]+|[㐀-鿿]")
_LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(_Model):
    heading: str
    visual: str
    labels: list[str] = Field(default_factory=list)
    at: int | None = None  # sentence number where this section becomes the focus


class Highlight(_Model):
    text: str
    at: int | None = None  # sentence number when the marker sweeps in
    page: int | None = None


def _as_range(v):
    if isinstance(v, int):
        return (v, v)
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (int(v[0]), int(v[1]))
    raise ValueError("sentences must be [first, last] (1-based, inclusive)")


# ---------------------------------------------------------------- claims (spec §6.3–6.5)

ClaimType = Literal["source_fact", "interpretation", "advice"]


class Evidence(_Model):
    source: str  # source id, e.g. "src1"
    excerpt: str  # verbatim text from the source; `pvm check` looks it up in the source text
    page: int | None = None


class Claim(_Model):
    sentences: tuple[int, int]
    type: ClaimType
    evidence: list[Evidence] = Field(default_factory=list)
    note: str | None = None

    @field_validator("sentences", mode="before")
    @classmethod
    def _range(cls, v):
        return _as_range(v)


class HookClaim(_Model):
    """The hook sits on top of the paper, so viewers read it as the paper's finding."""

    type: ClaimType
    evidence: list[Evidence] = Field(default_factory=list)
    basis: str | None = None  # interpretation/advice: how the hook follows from the source


class _Scene(_Model):
    id: str
    sentences: tuple[int, int]
    transition: Literal["cut", "fade"] = "cut"

    @field_validator("sentences", mode="before")
    @classmethod
    def _range(cls, v):
        return _as_range(v)


class PaperScene(_Scene):
    type: Literal["paper"]
    paper: str = "src1"  # source id of the paper shown
    # auto follows the license policy (spec §6.6): full page, title region, or citation card.
    source: Literal["auto", "pdf", "landing", "card"] = "auto"
    page: int | None = None  # PDF page; default is the page that carries the title (skips cover sheets)
    highlights: list[Highlight] = Field(default_factory=list)
    highlight_title: bool = True
    zoom: float = 1.06
    rights: Literal["auto", "permitted"] = "auto"  # permitted = the operator holds permission to show pages

    @field_validator("highlights", mode="before")
    @classmethod
    def _hl(cls, v):
        return [{"text": x} if isinstance(x, str) else x for x in (v or [])]


class ScrollScene(_Scene):
    type: Literal["paper_scroll"]
    paper: str = "src1"
    pages: tuple[int, int] = (1, 4)
    speed: float = 45.0  # pixels per second at 1080 px width
    rights: Literal["auto", "permitted"] = "auto"

    @field_validator("pages", mode="before")
    @classmethod
    def _pages(cls, v):
        return _as_range(v)


class PosterScene(_Scene):
    type: Literal["poster"]
    title: str
    sections: list[Section]
    focus: Literal["follow", "none"] = "follow"
    extra: str | None = None  # extra prompt instructions for this image
    image: str | None = None  # use this image file instead of generating one


class SummaryScene(_Scene):
    type: Literal["summary"]
    title: str = "总结"
    label: str = "文献信息"  # heading of the citation block, which code draws from the source metadata
    sections: list[Section]
    focus: Literal["follow", "none"] = "follow"
    extra: str | None = None
    image: str | None = None


class ImageScene(_Scene):
    type: Literal["image"]
    title: str | None = None
    visual: str
    extra: str | None = None
    image: str | None = None


class TextScene(_Scene):
    type: Literal["text"]
    lines: list[str]


Scene = Annotated[
    Union[PaperScene, ScrollScene, PosterScene, SummaryScene, ImageScene, TextScene],
    Field(discriminator="type"),
]
GENERATED_TYPES = ("poster", "summary", "image")


class VoiceOptions(_Model):
    engine: Literal["auto", "ark", "edge"] | None = None
    speaker: str | None = None
    speed: int | None = None


class Storyboard(_Model):
    version: int = 2
    title: str
    hook: list[str]
    hook_until: int | None = None  # sentence number after which the hook text disappears
    hook_claim: HookClaim | None = None
    claims: list[Claim] = Field(default_factory=list)
    scenes: list[Scene]
    voice: VoiceOptions | None = None
    style: str | None = None
    bgm: str | None = None
    notes: str | None = None
    sentences_hash: str | None = None  # written by `pvm check`; detects script edits (spec §11)

    def scene(self, scene_id: str):
        for sc in self.scenes:
            if sc.id == scene_id:
                return sc
        raise KeyError(scene_id)


def parse_storyboard(data: dict) -> Storyboard:
    try:
        return Storyboard.model_validate(data)
    except ValidationError as e:
        lines = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        from .util import PvmError

        raise PvmError("storyboard.json does not match the schema:\n" + "\n".join(lines)) from e


def _check_ranges(items: list[tuple[str, tuple[int, int]]], n: int, what: str, errors: list[str]) -> None:
    """Ranges must cover sentences 1..n in order without gaps; scenes and claims share this rule."""
    expected = 1
    for label, (a, b) in items:
        if a != expected:
            errors.append(f"{label}: starts at sentence {a}, expected {expected} ({what} must cover sentences contiguously)")
        if b < a:
            errors.append(f"{label}: sentence range {a}-{b} is reversed")
        expected = b + 1
    if expected - 1 != n:
        errors.append(f"{what} cover sentences 1-{expected - 1} but the script has {n} sentences")


def _check_evidence_shape(where: str, evidence: list[Evidence], source_ids: set[str] | None,
                          errors: list[str], warnings: list[str]) -> None:
    for i, ev in enumerate(evidence, 1):
        loc = f"{where}.evidence[{i}]"
        if source_ids is not None and ev.source not in source_ids:
            known = ", ".join(sorted(source_ids)) or "none yet; attach one with pvm paper"
            errors.append(f"{loc}: unknown source '{ev.source}' (known: {known})")
        if len(_TOKENS.findall(ev.excerpt)) < EXCERPT_MIN_TOKENS:
            errors.append(f"{loc}: excerpt '{ev.excerpt}' is too short to count as evidence; quote at least "
                          f"{EXCERPT_MIN_TOKENS} words of the source verbatim")
        elif len(ev.excerpt) > EXCERPT_LONG_CHARS:
            warnings.append(f"{loc}: excerpt is {len(ev.excerpt)} characters; quote the specific sentence that "
                            "supports the claim")


def _check_claims(sb: Storyboard, sentences: list[str], source_ids: set[str] | None,
                  errors: list[str], warnings: list[str]) -> None:
    if not sb.claims:
        errors.append("claims missing: every sentence needs a claim type (source_fact / interpretation / advice); "
                      "see AGENTS.md")
    else:
        _check_ranges([(f"claims[{i}]", c.sentences) for i, c in enumerate(sb.claims, 1)], len(sentences),
                      "claims", errors)
        for i, c in enumerate(sb.claims, 1):
            where = f"claims[{i}]"
            if c.type == "source_fact" and not c.evidence:
                errors.append(f"{where} (sentences {c.sentences[0]}-{c.sentences[1]}): source_fact needs evidence; "
                              "quote the source verbatim in evidence[].excerpt")
            _check_evidence_shape(where, c.evidence, source_ids, errors, warnings)

        type_of: dict[int, str] = {}
        for c in sb.claims:
            for k in range(c.sentences[0], c.sentences[1] + 1):
                type_of.setdefault(k, c.type)
        for k, text in enumerate(sentences, 1):
            kind = type_of.get(k)
            m = _RESEARCH.search(text) if kind and kind != "source_fact" else None
            if m:
                warnings.append(f"sentence {k} uses research wording ('{m.group(0)}') but is labeled {kind}; label it "
                                "source_fact with evidence, or phrase it as an interpretation (一种可能的解释是…)")

    hc = sb.hook_claim
    if hc is None:
        errors.append("hook_claim missing: the hook sits on the paper, so viewers read it as the paper's finding; "
                      "give it a type plus evidence (source_fact) or a basis (interpretation/advice)")
        return
    if hc.type == "source_fact" and not hc.evidence:
        errors.append("hook_claim: source_fact needs evidence (a verbatim excerpt from the source)")
    if hc.type != "source_fact" and not (hc.basis or "").strip():
        warnings.append(f"hook_claim: a {hc.type} hook should state its basis, one sentence on how it follows "
                        "from the source")
    _check_evidence_shape("hook_claim", hc.evidence, source_ids, errors, warnings)


def check_storyboard(sb: Storyboard, sentences: list[str], source_ids: set[str] | None = None,
                     *, ignore_anchor: bool = False) -> tuple[list[str], list[str]]:
    """Semantic checks beyond the schema. Returns (errors, warnings).

    `sentences` are the script's sentence texts (numbered from 1 in the storyboard). With `source_ids`,
    references to sources are checked too; the excerpt lookup itself is evidence.check_evidence.
    """
    errors: list[str] = []
    warnings: list[str] = []
    n_sentences = len(sentences)
    if not sb.scenes:
        return ["storyboard has no scenes"], warnings

    if sb.sentences_hash and not ignore_anchor and sb.sentences_hash != sentences_hash(sentences):
        errors.append("script.txt changed after this storyboard was checked, so its sentence numbers may point at "
                      "the wrong sentences. Compare the scene and claim ranges with `pvm sentences`, fix them, then "
                      "run `pvm check --reanchor`.")

    ids = [sc.id for sc in sb.scenes]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate scene ids: {sorted(dupes)}")
    for sc in sb.scenes:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sc.id):
            errors.append(f"scene id '{sc.id}' must be ASCII letters/digits/_/-")

    _check_ranges([(sc.id, sc.sentences) for sc in sb.scenes], n_sentences, "scenes", errors)
    _check_claims(sb, sentences, source_ids, errors, warnings)

    if not 1 <= len(sb.hook) <= 3:
        errors.append("hook must have 1-3 lines")
    for line in sb.hook:
        if len(line) > LIMITS["hook_line"] * 2:
            errors.append(f"hook line '{line}' is too long ({len(line)} chars); keep it <= {LIMITS['hook_line']}")
        elif len(line) > LIMITS["hook_line"]:
            warnings.append(f"hook line '{line}' has {len(line)} chars; <= {LIMITS['hook_line']} reads best")
    if sb.hook_until is not None and not 1 <= sb.hook_until <= n_sentences:
        errors.append(f"hook_until={sb.hook_until} is outside 1-{n_sentences}")

    if sb.scenes[0].type not in ("paper", "paper_scroll"):
        warnings.append("first scene is not a paper scene; the benchmark style opens on the paper page")

    for sc in sb.scenes:
        a, b = sc.sentences
        if sc.type in ("poster", "summary"):
            n = len(sc.sections)
            if n == 0 or n > 4:
                errors.append(f"{sc.id}: {n} sections; use 2-4 (3 is the house style)")
            elif n != 3:
                warnings.append(f"{sc.id}: {n} sections; 3 is the house style")
            if sc.type == "poster" and len(sc.title) > LIMITS["title"]:
                warnings.append(f"{sc.id}: title '{sc.title}' has {len(sc.title)} chars; <= {LIMITS['title']} reads best")
            last_at = a - 1
            for i, sec in enumerate(sc.sections, 1):
                where = f"{sc.id}.sections[{i}]"
                if len(sec.heading) > LIMITS["heading"]:
                    warnings.append(f"{where}: heading '{sec.heading}' is long ({len(sec.heading)} chars)")
                if len(sec.labels) > LIMITS["labels"]:
                    warnings.append(f"{where}: {len(sec.labels)} labels; image models garble crowded text, keep <= {LIMITS['labels']}")
                for label in sec.labels:
                    if _LATIN_OR_DIGIT.search(label):
                        errors.append(f"{where}: label '{label}' contains digits or Latin letters; labels are drawn by "
                                      "the image model, so put numbers and names in the heading or the narration, "
                                      "which code draws")
                    elif len(label) > LIMITS["label"]:
                        warnings.append(f"{where}: label '{label}' is long ({len(label)} chars)")
                if len(sec.visual) > LIMITS["visual"]:
                    warnings.append(f"{where}: visual description is {len(sec.visual)} chars; <= {LIMITS['visual']} keeps prompts focused")
                if sec.at is not None:
                    if not a <= sec.at <= b:
                        errors.append(f"{where}: at={sec.at} is outside the scene's sentences {a}-{b}")
                    elif sec.at <= last_at:
                        errors.append(f"{where}: at={sec.at} must increase across sections")
                    else:
                        last_at = sec.at
        if sc.type == "image" and len(sc.visual) > LIMITS["visual"] * 2:
            warnings.append(f"{sc.id}: visual description is long ({len(sc.visual)} chars)")
        if sc.type in ("paper", "paper_scroll") and source_ids is not None and sc.paper not in source_ids:
            known = ", ".join(sorted(source_ids)) or "none yet; attach one with pvm paper"
            errors.append(f"{sc.id}: paper '{sc.paper}' is not a source of this project (known: {known})")
        if sc.type == "paper":
            if sc.source == "landing":
                errors.append(f"{sc.id}: source 'landing' (publisher page screenshots) is not supported because of "
                              "rights and anti-bot risk; use auto, pdf or card")
            for h in sc.highlights:
                if h.at is not None and not a <= h.at <= b:
                    errors.append(f"{sc.id}: highlight '{h.text}' at={h.at} is outside sentences {a}-{b}")
        if sc.type == "paper_scroll" and (sc.pages[0] < 1 or sc.pages[1] < sc.pages[0]):
            errors.append(f"{sc.id}: pages must be [first, last] starting at 1")
        if sc.type == "text" and not sc.lines:
            errors.append(f"{sc.id}: text scene needs at least one line")
    return errors, warnings
