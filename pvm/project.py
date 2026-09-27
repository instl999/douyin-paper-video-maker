"""Project folders: projects/<slug>/ holds everything for one video."""
from __future__ import annotations

from pathlib import Path

from .schema import Paper, Storyboard, check_storyboard, parse_storyboard
from .script import Sentence, clean_script, split_sentences
from .util import ROOT, PvmError, ensure_dir, now_iso, read_json, read_text, stable_hash, write_json, write_text

PROJECTS_DIR = ROOT / "projects"
CACHE_DIR = ROOT / "cache"


class Project:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir = PROJECTS_DIR / slug

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
        meta = self.meta()
        meta.update(fields)
        meta["updated"] = now_iso()
        write_json(self.meta_path, meta)
        return meta

    def paper(self) -> Paper | None:
        data = self.meta().get("paper")
        return Paper.model_validate(data) if data else None

    def set_paper(self, paper: Paper) -> None:
        self.update_meta(paper=paper.model_dump(exclude_none=True))

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
            # script.txt was edited by hand: keep sentences.json in sync.
            write_json(self.sentences_path, [s.__dict__ for s in sentences])
        return sentences

    # ------------------------------------------------------------ storyboard
    def storyboard(self, check: bool = True) -> Storyboard:
        data = read_json(self.storyboard_path)
        if data is None:
            raise PvmError(f"no storyboard yet: write {self.storyboard_path.relative_to(ROOT)} "
                           f"(see AGENTS.md) or run  pvm plan {self.slug} --auto")
        sb = parse_storyboard(data)
        if check:
            errors, _ = check_storyboard(sb, len(self.sentences()))
            if errors:
                raise PvmError("storyboard.json has problems:\n" + "\n".join(f"  - {e}" for e in errors)
                               + f"\nRun  pvm check {self.slug}  for details.")
        return sb

    # ------------------------------------------------------------ stage stamps
    def stamp(self, stage: str) -> dict | None:
        return (self.meta().get("stages") or {}).get(stage)

    def set_stamp(self, stage: str, inputs: dict, **extra) -> None:
        meta = self.meta()
        stages = meta.setdefault("stages", {})
        stages[stage] = {"hash": stable_hash(inputs), "at": now_iso(), **extra}
        write_json(self.meta_path, meta)

    def is_fresh(self, stage: str, inputs: dict) -> bool:
        s = self.stamp(stage)
        return bool(s and s.get("hash") == stable_hash(inputs))


def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(d.name for d in PROJECTS_DIR.iterdir() if (d / "project.json").exists())
