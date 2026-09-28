"""pvm command line. Spec: docs/spec.md. Storyboard format for authors and agents: AGENTS.md."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .util import PvmError, log, read_text, setup_console, warn

POLICY_TEXT = {
    "page": "the full page (openly licensed published version)",
    "title_crop": "the title region of page 1 (not openly licensed)",
    "card": "a citation card (no PDF yet)",
}


# ---------------------------------------------------------------- research and sources

def cmd_research(a) -> None:
    from .research import run_research

    sources = tuple(s.strip() for s in a.sources.split(",") if s.strip())
    out_dir, cands = run_research(a.topic, a.query or [], slug=a.slug, limit=a.limit, per_query=a.per_query,
                                  since=a.since, sources=sources, oa_only=a.oa_only)
    log(f"\n{len(cands)} candidates -> {out_dir / 'candidates.md'}")
    for c in cands[:12]:
        p = c.paper
        log(f"  {c.id}  {p.year or '----'}  {(p.venue or '')[:26]:<26}  {' '.join(c.badges)[:34]:<34}  {p.title[:70]}")
    if cands:
        log(f"\nAttach one:  pvm paper <project> --pick {out_dir.name}:{cands[0].id}")


def cmd_paper(a) -> None:
    from .evidence import describe_license, display_policy
    from .project import Project
    from .research import download_pdf, lookup_doi, pick_candidate

    if bool(a.doi) == bool(a.pick):
        raise PvmError("give exactly one of --doi or --pick")
    paper = lookup_doi(a.doi) if a.doi else pick_candidate(a.pick)
    p, _ = Project.open_or_create(a.slug)
    p.set_paper(paper, a.id)
    pdf = p.source_pdf(a.id)
    log(f"[{a.id}] {paper.citation()}")
    if not pdf.exists() and not a.no_download:
        url = download_pdf(paper, pdf)
        if url:
            log(f"  downloaded the open-access PDF from {url}")
    log(f"  open access: {paper.oa_status or ('yes' if paper.is_oa else 'no or unknown')}; "
        f"license: {describe_license(paper)}")
    log(f"  the opening will show {POLICY_TEXT[display_policy(paper, pdf.exists())]}")
    if not pdf.exists():
        log(f"  no PDF yet: save it as {pdf} so excerpts can be checked against the full text")


def _find_in(raw: str, query: str, width: int = 90) -> list[str]:
    flat = re.sub(r"\s+", " ", raw)
    out = []
    for m in re.finditer(re.escape(query), flat, re.I):
        a, b = max(0, m.start() - width), min(len(flat), m.end() + width)
        out.append(flat[a:b])
    return out


def cmd_source(a) -> None:
    from .evidence import describe_license, display_policy, load_source_text
    from .project import Project

    p = Project.load(a.slug)
    papers = p.sources()
    if not papers:
        raise PvmError(f"no sources yet: run  pvm paper {a.slug} --doi <doi>")
    for sid in [a.id] if a.id else list(papers):
        if sid not in papers:
            raise PvmError(f"unknown source '{sid}'; this project has: {', '.join(papers)}")
        paper = papers[sid]
        text = load_source_text(sid, paper, p.sources_dir)
        log(f"[{sid}] {paper.citation()}")
        log(f"  license: {describe_license(paper)}; the opening shows "
            f"{POLICY_TEXT[display_policy(paper, text.has_pdf)]}")
        parts = ", ".join(f"{k} ({len(v):,} chars)" for k, v in text.parts.items())
        log(f"  text for excerpts: {parts}")
        if not text.has_full_text:
            log(f"  title and abstract only: save the PDF as {p.source_pdf(sid)} to quote from the body")
        if a.find:
            hits = [(name, line) for name, raw in text.parts.items() for line in _find_in(raw, a.find)]
            for name, line in hits:
                log(f"  [{name}] …{line}…")
            if not hits:
                log(f"  '{a.find}' does not occur in {sid}")
        elif a.full:
            for name, raw in text.parts.items():
                log(f"\n--- {name} ---\n{raw}")
        elif paper.abstract:
            log(f"\n  Abstract: {paper.abstract}\n")


# ---------------------------------------------------------------- project and storyboard

def cmd_script(a) -> None:
    from .project import Project

    text = read_text(Path(a.file)) if a.file else a.text
    if not text:
        raise PvmError("give --file <script.txt> or --text '<script>'")
    p, created = Project.open_or_create(a.slug)
    had_storyboard = p.storyboard_path.exists()
    sentences = p.set_script(text)
    log(f"{'created' if created else 'updated'} project {a.slug}: {len(sentences)} sentences "
        f"({sum(s.para_end for s in sentences)} paragraphs)")
    if had_storyboard:
        warn(f"a storyboard already exists; run  pvm check {a.slug}  to see whether its sentence ranges still fit")
    log(f"next:  pvm sentences {a.slug}  (numbered sentences for storyboard.json)")


def cmd_sentences(a) -> None:
    from .project import Project

    for s in Project.load(a.slug).sentences():
        log(f"{s.n:>3}  {s.text}{'  ¶' if s.para_end else ''}")


def cmd_check(a) -> None:
    from .project import Project

    p = Project.load(a.slug)
    report = p.check(strict=a.strict, ignore_anchor=a.reanchor)
    sb = report.storyboard
    for w in report.warnings:
        log(f"  warning: {w}")
    for e in report.errors:
        log(f"  ERROR:   {e}")
    per_type: dict[str, int] = {}
    for c in sb.claims:
        per_type[c.type] = per_type.get(c.type, 0) + c.sentences[1] - c.sentences[0] + 1
    found = sum(r.status == "found" for r in report.evidence)
    log(f"scenes: {len(sb.scenes)}; sentences by claim type: "
        + (", ".join(f"{k} {v}" for k, v in sorted(per_type.items())) or "none")
        + f"; excerpts found: {found}/{len(report.evidence)}")
    if report.errors:
        raise PvmError(f"{len(report.errors)} problem(s) in {p.storyboard_path}")
    if sb.sentences_hash != report.sentences_hash:
        p.anchor_storyboard(report.sentences_hash)
        log(f"anchored the storyboard to the current script (sentences_hash {report.sentences_hash})")
    log("ok" + (f", {len(report.warnings)} warning(s)" if report.warnings else ""))


def cmd_list(a) -> None:
    from .project import Project, list_projects
    from .research import list_research

    projects = list_projects()
    log("projects:" if projects else "projects: (none)")
    for slug in projects:
        p = Project(slug)
        papers = p.sources()
        state = "storyboard" if p.storyboard_path.exists() else ("script" if p.script_path.exists() else "new")
        log(f"  {slug:<28} {state:<11} sources: {', '.join(papers) or '-'}")
    research = list_research()
    log("research:" if research else "research: (none)")
    for r in research:
        log(f"  {r['slug']:<28} {r['n']:>3} candidates  {r['topic']}")


# ---------------------------------------------------------------- voice and timeline

def cmd_voice(a) -> None:
    from .pipeline import prepare
    from .project import Project
    from .util import fmt_seconds
    from .voice import build_voice

    p = Project.load(a.slug)
    if not p.storyboard_path.exists():
        build_voice(p, None, a.engine, force=a.force)
        log("no storyboard yet, so no timeline; the voice timing is in audio/voice.json")
        return
    _, track, tl = prepare(p, engine=a.engine, force_voice=a.force)
    log(f"timeline: {len(tl.scenes)} scenes, {len(tl.cues)} subtitle cues, {fmt_seconds(tl.duration)} "
        f"-> audio/timeline.json, audio/subtitles.srt")
    for sc in tl.scenes:
        log(f"  {sc.id:<12} {sc.type:<12} {fmt_seconds(sc.start)} - {fmt_seconds(sc.end)}  ({sc.end - sc.start:.1f} s)")
    log(f"  hook on screen {tl.hook[0]:.1f} - {tl.hook[1]:.1f} s")


# ---------------------------------------------------------------- images

def cmd_images(a) -> None:
    from .config import get_settings
    from .images import accept_candidate, run_images
    from .project import Project
    from .quota import status

    p = Project.load(a.slug)
    if a.accept:
        log(f"accepted {accept_candidate(p, a.accept)} (recorded as an operator decision)")
        return
    results = run_images(p, only=a.scene, attempts=a.attempts, regenerate=a.regenerate, dry_run=a.dry_run)
    if not results:
        log("no scenes need generated images")
        return
    review = []
    for r in results:
        if r.status == "dry-run":
            log(f"--- {r.scene}: {r.size[0]}x{r.size[1]}, {r.afp} AFP per attempt\n{r.prompt}\n")
        elif r.status == "up-to-date":
            log(f"  {r.scene:<12} up to date      {r.file}")
        elif r.status == "accepted":
            log(f"  {r.scene:<12} accepted        attempt {len(r.attempts)}  {r.file}")
        else:
            last = r.attempts[-1]
            problems = "; ".join(filter(None, [
                "labels not found: " + "、".join(last["missing"]) if last["missing"] else "",
                "model drew letters or digits: " + " / ".join(last["forbidden"]) if last["forbidden"] else ""]))
            log(f"  {r.scene:<12} NEEDS REVIEW    {problems}; candidate {r.file}")
            review.append(r.scene)
    settings = get_settings()
    if a.dry_run:
        todo = [r for r in results if r.status == "dry-run"]
        attempts = a.attempts or settings.image_attempts
        log(f"estimate: {len(todo)} image(s), {len(todo) * settings.afp_per_image:,} AFP at one attempt each, up to "
            f"{len(todo) * settings.afp_per_image * attempts:,} with retries; today's allowance "
            f"{status().allowance_today:,} AFP")
    else:
        log(f"spent {sum(r.afp for r in results):,} AFP; today's allowance left {status().allowance_today:,} AFP")
    if review:
        raise PvmError(f"look at the candidates, then regenerate or accept: pvm images {a.slug} --accept <scene>")


def _warn_stale(p, sb) -> None:
    from .images import stale_images

    for scene_id in stale_images(p, sb):
        warn(f"{scene_id}: the image was generated for an older brief, labels or style; run  pvm images {p.slug}")


# ---------------------------------------------------------------- render and QA

def _print_qa(result: dict) -> bool:
    for c in result["checks"]:
        log(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['name']:<14} {c['detail']}")
    return result["passed"]


def cmd_animatic(a) -> None:
    from .pipeline import prepare
    from .project import Project
    from .render.video import render, write_manifest

    p = Project.load(a.slug)
    sb, _, tl = prepare(p, engine=a.engine)
    summary = render(p, sb, tl, ratio=a.ratio, kind="animatic", jobs=a.jobs)
    write_manifest(p, sb, tl, [summary], "animatic")
    log("review the timing, the claims and the panel briefs; nothing was spent on images")


def cmd_render(a) -> None:
    from .pipeline import prepare
    from .project import Project
    from .qa import run_qa
    from .render.video import render, save_cover, write_description, write_manifest
    from .util import write_text

    p = Project.load(a.slug)
    kind = "draft" if a.draft else "final"
    sb, _, tl = prepare(p, engine=a.engine, strict=kind == "final")
    _warn_stale(p, sb)
    ratios = ["3x4", "9x16"] if a.ratio == "both" else [a.ratio]
    renders = [render(p, sb, tl, ratio=r, kind=kind, jobs=a.jobs) for r in ratios]
    save_cover(p, sb, tl, ratios[0])
    write_description(p, sb)
    write_text(p.output_dir / "subtitles.srt", (p.audio_dir / "subtitles.srt").read_text(encoding="utf-8"))
    write_manifest(p, sb, tl, renders, kind)
    passed = True
    for r in ratios:
        log(f"QA {kind}_{r}.mp4:")
        passed = _print_qa(run_qa(p, r, kind)) and passed
    log(f"outputs in {p.output_dir}: {', '.join(Path(x['file']).name for x in renders)}, cover.png, "
        "subtitles.srt, description.txt (publish checklist), manifest")
    if not passed:
        raise PvmError("QA found problems (see above); the files were still written")


def cmd_qa(a) -> None:
    from .project import Project
    from .qa import run_qa

    p = Project.load(a.slug)
    if not _print_qa(run_qa(p, a.ratio, a.kind, Path(a.file) if a.file else None)):
        raise PvmError("QA found problems")


# ---------------------------------------------------------------- setup and quota

def cmd_fonts(a) -> None:
    from .fonts import download_fonts

    if not download_fonts(force=a.force):
        raise PvmError("some fonts could not be downloaded; see the warnings above")
    log("fonts ready (SIL Open Font License)")


def cmd_quota(a) -> None:
    from .quota import status

    st = status()
    log(f"plan tier {st.tier}: monthly budget {st.monthly_budget:,} AFP, daily cap {st.daily_cap:,} AFP")
    log(f"used this month {st.used_cycle:,} AFP ({100 * (1 - st.remaining_fraction):.0f}%), today {st.used_today:,}; "
        f"{st.days_left} day(s) left in the cycle")
    log(f"allowance today: {st.allowance_today:,} AFP; mode: {st.mode}")


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvm", description="Evidence-led paper explainer videos (spec: docs/spec.md)")
    parser.add_argument("--version", action="version", version=f"pvm {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    s = sub.add_parser("research", help="search scholarly indexes and rank candidate papers")
    s.add_argument("topic")
    s.add_argument("-q", "--query", action="append", help="English search query (repeatable; default: the topic)")
    s.add_argument("--slug", help="folder name under research/ (default: from the topic)")
    s.add_argument("--limit", type=int, default=15)
    s.add_argument("--per-query", type=int, default=25)
    s.add_argument("--since", type=int, help="earliest publication year")
    s.add_argument("--sources", default="openalex,crossref", help="comma list: openalex,crossref,europepmc,arxiv,s2")
    s.add_argument("--oa-only", action="store_true", help="only open-access papers")
    s.set_defaults(func=cmd_research)

    s = sub.add_parser("paper", help="attach a source paper to a project")
    s.add_argument("slug")
    s.add_argument("--doi")
    s.add_argument("--pick", help="<research-slug>:<candidate-id>, e.g. sunk-cost:c03")
    s.add_argument("--id", default="src1", help="source id (default src1, the paper shown in the opening)")
    s.add_argument("--no-download", action="store_true", help="do not fetch the open-access PDF")
    s.set_defaults(func=cmd_paper)

    s = sub.add_parser("source", help="show a source's license, display policy and quotable text")
    s.add_argument("slug")
    s.add_argument("--id", help="only this source")
    s.add_argument("--find", help="show where this text occurs (to copy verbatim excerpts)")
    s.add_argument("--full", action="store_true", help="print the full text")
    s.set_defaults(func=cmd_source)

    s = sub.add_parser("script", help="create or update a project's narration script")
    s.add_argument("slug")
    s.add_argument("--file", help="UTF-8 text file, one paragraph per line")
    s.add_argument("--text")
    s.set_defaults(func=cmd_script)

    s = sub.add_parser("sentences", help="print the numbered sentences")
    s.add_argument("slug")
    s.set_defaults(func=cmd_sentences)

    s = sub.add_parser("check", help="validate storyboard.json: schema, claims, excerpts, rights, anchor")
    s.add_argument("slug")
    s.add_argument("--strict", action="store_true", help="final-render rules: unverifiable excerpts and rights issues are errors")
    s.add_argument("--reanchor", action="store_true", help="accept the current script after re-checking the sentence ranges")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("voice", help="synthesize the narration and build the timeline and subtitles")
    s.add_argument("slug")
    s.add_argument("--engine", choices=["edge", "ark"], help="override PVM_TTS_ENGINE and the storyboard")
    s.add_argument("--force", action="store_true", help="rebuild voice.wav even if nothing changed")
    s.set_defaults(func=cmd_voice)

    s = sub.add_parser("images", help="generate poster images (Seedream) with the OCR label check")
    s.add_argument("slug")
    s.add_argument("--scene", action="append", help="only this scene (repeatable)")
    s.add_argument("--attempts", type=int, help="retry budget per image (default PVM_IMAGE_ATTEMPTS or 3)")
    s.add_argument("--regenerate", action="store_true", help="generate again even if an accepted image is current")
    s.add_argument("--dry-run", action="store_true", help="print the prompts and the AFP estimate; call nothing")
    s.add_argument("--accept", metavar="SCENE", help="accept a candidate that failed the OCR check after reviewing it")
    s.set_defaults(func=cmd_images)

    s = sub.add_parser("animatic", help="zero-quota preview: real voice and timing, placeholder panels")
    s.add_argument("slug")
    s.add_argument("--ratio", choices=["3x4", "9x16"], default="3x4")
    s.add_argument("--engine", choices=["edge", "ark"])
    s.add_argument("--jobs", type=int, help="parallel render processes (default: automatic)")
    s.set_defaults(func=cmd_animatic)

    s = sub.add_parser("render", help="final render with strict checks, cover, description, manifest and QA")
    s.add_argument("slug")
    s.add_argument("--ratio", choices=["3x4", "9x16", "both"], default="3x4")
    s.add_argument("--draft", action="store_true", help="relaxed checks; missing images become placeholders")
    s.add_argument("--engine", choices=["edge", "ark"])
    s.add_argument("--jobs", type=int, help="parallel render processes (default: automatic)")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("qa", help="check a rendered file against the acceptance criteria")
    s.add_argument("slug")
    s.add_argument("--ratio", choices=["3x4", "9x16"], default="3x4")
    s.add_argument("--kind", choices=["final", "draft"], default="final")
    s.add_argument("--file", help="check this file instead")
    s.set_defaults(func=cmd_qa)

    s = sub.add_parser("list", help="list projects and research")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("fonts", help="download the openly licensed fonts used for rendering")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_fonts)

    s = sub.add_parser("quota", help="show the AFP budget, usage and today's allowance")
    s.set_defaults(func=cmd_quota)
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except PvmError as e:
        print(f"error: {e}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        return 130
