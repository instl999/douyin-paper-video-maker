"""Project folders: projects/<slug>/ holds everything for one video."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from .evidence import EvidenceResult, SourceText, check_evidence, load_source_text
from .schema import Paper, Storyboard, check_storyboard, parse_storyboard
from .script import Sentence, clean_script, sentences_hash, split_sentences
from .util import PvmError, data_dir, ensure_dir, now_iso, read_json, read_text, stable_hash, write_json, write_text

# project.json is read-modify-written by several stages; image generation runs them on threads.
_META_LOCK = threading.RLock()


def projects_dir() -> Path:
    return data_dir("projects")


def cache_dir() -> Path:
    return data_dir("cache")


@dataclass
class CheckReport:
    storyboard: Storyboard
    errors: list[str]
    warnings: list[str]
    evidence: list[EvidenceResult] = field(default_factory=list)
    sentences_hash: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


class Project:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir = projects_dir() / slug

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def load(cls, slug: str) -> "Project":
        p = cls(slug)
        if not p.meta_path.exists():
            known = ", ".join(list_projects()) or "(none yet)"
            raise PvmError(f"project '{slug}' not found. Existing projects: {known}")
        return p

    @classmethod
    def open_or_create(cls, slug: str) -> tuple["Project", bool]:
        p = cls(slug)
        created = not p.meta_path.exists()
        if created:
            ensure_dir(p.dir)
            write_json(p.meta_path, {"slug": slug, "created": now_iso(), "stages": {}})
        return p, created

    # ------------------------------------------------------------ paths
    @property
    def meta_path(self) -> Path:
        return self.dir / "project.json"

    @property
    def script_path(self) -> Path:
        return self.dir / "script.txt"

    @property
    def sentences_path(self) -> Path:
        return self.dir / "sentences.json"

    @property
    def storyboard_path(self) -> Path:
        return self.dir / "storyboard.json"

    @property
    def sources_dir(self) -> Path:
        return self.dir / "sources"

    @property
    def visuals_dir(self) -> Path:
        return self.dir / "visuals"

    @property
    def audio_dir(self) -> Path:
        return self.dir / "audio"

    @property
    def output_dir(self) -> Path:
        return self.dir / "output"

    # ------------------------------------------------------------ metadata
    def meta(self) -> dict:
        return read_json(self.meta_path, {}) or {}

    def update_meta(self, **fields) -> dict:
        with _META_LOCK:
            meta = self.meta()
            meta.update(fields)
            meta["updated"] = now_iso()
            write_json(self.meta_path, meta)
            return meta

    # ------------------------------------------------------------ sources
    def sources(self) -> dict[str, Paper]:
        meta = self.meta()
        raw = meta.get("sources")
        if raw is None and meta.get("paper"):  # projects created before multi-source support
            raw = {"src1": meta["paper"]}
        return {sid: Paper.model_validate(data) for sid, data in (raw or {}).items()}

    def paper(self, source_id: str = "src1") -> Paper | None:
        return self.sources().get(source_id)

    def set_paper(self, paper: Paper, source_id: str = "src1") -> None:
        with _META_LOCK:
            meta = self.meta()
            sources = meta.get("sources") or ({"src1": meta["paper"]} if meta.get("paper") else {})
            sources[source_id] = paper.model_dump(exclude_none=True)
            meta["sources"] = sources
            meta.pop("paper", None)
            meta["updated"] = now_iso()
            write_json(self.meta_path, meta)

    def source_pdf(self, source_id: str = "src1") -> Path:
        return self.sources_dir / f"{source_id}.pdf"

    def source_texts(self) -> dict[str, SourceText]:
        return {sid: load_source_text(sid, paper, self.sources_dir) for sid, paper in self.sources().items()}

    # ------------------------------------------------------------ script
    def set_script(self, text: str) -> list[Sentence]:
        text = clean_script(text)
        if not text:
            raise PvmError("script is empty")
        write_text(self.script_path, text + "\n")
        sentences = split_sentences(text)
        write_json(self.sentences_path, [s.__dict__ for s in sentences])
        return sentences

    def script(self) -> str:
        if not self.script_path.exists():
            raise PvmError(f"no script yet: run  pvm script {self.slug} --file <script.txt>")
        return clean_script(read_text(self.script_path))

    def sentences(self) -> list[Sentence]:
        text = self.script()
        cached = read_json(self.sentences_path)
        sentences = split_sentences(text)
        if cached != [s.__dict__ for s in sentences]:
            # script.txt was edited by hand. The storyboard's sentences_hash catches any shift in numbering.
            write_json(self.sentences_path, [s.__dict__ for s in sentences])
        return sentences

    # ------------------------------------------------------------ storyboard
    def storyboard_data(self) -> dict:
        data = read_json(self.storyboard_path)
        if data is None:
            raise PvmError(f"no storyboard yet: write {self.storyboard_path} (format: AGENTS.md), "
                           f"then run  pvm check {self.slug}")
        return data

    def check(self, *, strict: bool = False, ignore_anchor: bool = False) -> CheckReport:
        """All storyboard checks: schema, ranges, claims, anchor, excerpts, page rights."""
        sb = parse_storyboard(self.storyboard_data())
        texts = [s.text for s in self.sentences()]
        papers = self.sources()
        errors, warnings = check_storyboard(sb, texts, set(papers), ignore_anchor=ignore_anchor)
        ev_errors, ev_warnings, results = check_evidence(sb, self.source_texts(), papers, strict=strict)
        return CheckReport(sb, errors + ev_errors, warnings + ev_warnings, results, sentences_hash(texts))

    def storyboard(self, check: bool = True, strict: bool = False) -> Storyboard:
        if not check:
            return parse_storyboard(self.storyboard_data())
        report = self.check(strict=strict)
        if report.errors:
            raise PvmError("storyboard.json has problems:\n" + "\n".join(f"  - {e}" for e in report.errors)
                           + f"\nRun  pvm check {self.slug}  for details.")
        return report.storyboard

    def anchor_storyboard(self, digest: str) -> None:
        """Record which sentence list the storyboard's numbers refer to (spec §11)."""
        data = self.storyboard_data()
        data["sentences_hash"] = digest
        write_json(self.storyboard_path, data)

    # ------------------------------------------------------------ stage stamps
    def stamp(self, stage: str) -> dict | None:
        return (self.meta().get("stages") or {}).get(stage)

    def set_stamp(self, stage: str, inputs: dict, **extra) -> None:
        with _META_LOCK:
            meta = self.meta()
            stages = meta.setdefault("stages", {})
            stages[stage] = {"hash": stable_hash(inputs), "at": now_iso(), **extra}
            write_json(self.meta_path, meta)

    def is_fresh(self, stage: str, inputs: dict) -> bool:
        s = self.stamp(stage)
        return bool(s and s.get("hash") == stable_hash(inputs))


def list_projects() -> list[str]:
    root = projects_dir()
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "project.json").exists())
