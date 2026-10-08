"""LLM storyboard drafts and claim review (spec §7, §15.1, §15.3).

The model proposes; code decides. Every draft goes through the same schema, claim and excerpt checks as a
hand-written storyboard, and one repair round receives the exact errors.
"""
from __future__ import annotations

import json

from .evidence import check_evidence, describe_license, display_policy
from .llm import LLM
from .project import Project
from .schema import check_storyboard, parse_storyboard
from .util import PvmError, now_iso, stable_hash, write_json

PLAN_VERSION = 1
REVIEW_VERSION = 1
SOURCE_CHARS = 24_000  # abstract plus the start of the full text; enough for the claims a video makes
PLAN_TOKENS = 32_000  # reasoning counts against max_tokens: v4.1-flash spent 7,968 of 8,717 on a 6-sentence draft

EXAMPLE = {
    "version": 2, "title": "<internal title>", "hook": ["<2-7字>", "<2-7字>"], "hook_until": 3,
    "hook_claim": {"type": "source_fact", "evidence": [{"source": "src1", "excerpt": "<verbatim sentence from the source>"}]},
    "claims": [
        {"sentences": [1, 1], "type": "interpretation"},
        {"sentences": [2, 3], "type": "source_fact", "evidence": [{"source": "src1", "excerpt": "<verbatim>"}]},
        {"sentences": [4, 6], "type": "interpretation"},
        {"sentences": [7, 8], "type": "advice"},
    ],
    "scenes": [
        {"id": "open", "type": "paper", "sentences": [1, 3], "paper": "src1", "source": "auto",
         "highlights": [{"text": "<verbatim phrase on the first page>", "at": 3}]},
        {"id": "p1", "type": "poster", "sentences": [4, 8], "title": "<≤8字>", "sections": [
            {"heading": "<≤7字>", "at": 4, "labels": ["<≤7字>"], "visual": "mascot <action> with <props>"},
            {"heading": "<≤7字>", "at": 6, "labels": [], "visual": "..."},
            {"heading": "<≤7字>", "at": 7, "labels": ["<≤7字>"], "visual": "..."}]},
    ],
}

PLAN_SYSTEM = """You plan evidence-led Chinese explainer videos. Reply with one JSON object: a storyboard, version 2.

A program checks your JSON afterwards:
- "scenes" and "claims" each cover every sentence exactly once, in order, as [first, last] ranges numbered from 1.
- Every claim has a type: source_fact (what the source reports), interpretation (reading, bridge, question) or advice.
- Every source_fact has evidence: [{"source": "src1", "excerpt": "..."}]. Copy each excerpt character for character from
  SOURCE TEXT: one sentence or clause, at least 8 words. Never paraphrase, translate or invent an excerpt.
- "hook_claim" is required: a source_fact hook has evidence; an interpretation or advice hook has "basis", one sentence
  on how the hook follows from the source.
- The first scene is a paper scene: {"type": "paper", "paper": "src1", "source": "auto"}, optionally with
  "highlights": [{"text": "<a verbatim phrase from the first page>", "at": <sentence>}].
- Poster scenes: "title" of at most 8 Chinese characters; 2-4 "sections" (3 preferred), each with "heading" (at most 7
  characters), "visual" (an English brief under 60 characters: the mascot, an action, 2-3 props; never text),
  "labels" (0-3 Chinese words of at most 7 characters, no digits, no Latin letters) and "at" (the sentence where that
  panel starts).
- The last scene may be {"type": "summary", "title": "总结", "sections": [...]}.
- "hook": 1-2 lines of 2-7 Chinese characters.

Judgment:
- Never invent a paper, number, sample size, effect or quote.
- Keep correlation apart from causation. A sample is not everyone. "A study found" is not "science proves".
- Sentences that introduce the paper (journal, year, authors) are source_fact; quote the title.
- When the evidence is thin, label the sentence interpretation.
- The hook must not claim more than the paper shows: viewers who see it over the paper will believe the paper says it.
- About 5-8 sentences per poster and 1-3 sentences per panel.

The JSON shape (placeholders in <>, content illustrative only):
""" + json.dumps(EXAMPLE, ensure_ascii=False, indent=1)


def source_brief(p: Project, max_chars: int = SOURCE_CHARS) -> str:
    papers = p.sources()
    if not papers:
        raise PvmError(f"attach a source first:  pvm paper {p.slug} --doi <doi>")
    texts = p.source_texts()
    blocks = []
    for sid, paper in papers.items():
        text = texts[sid]
        body = " ".join((text.parts.get("pdf") or text.parts.get("txt") or "").split())
        blocks.append("\n".join([
            f"[{sid}] {paper.citation()}",
            f"license: {describe_license(paper)}; the opening shows {display_policy(paper, text.has_pdf)}",
            f"TITLE: {paper.title}",
            f"ABSTRACT: {paper.abstract or '(none)'}",
            "SOURCE TEXT (quote excerpts only from here, from the title or from the abstract):",
            body[:max_chars] or "(no full text; quote only the title or the abstract)",
        ]))
    return "\n\n".join(blocks)


def plan_prompt(p: Project) -> str:
    sentences = "\n".join(f"{s.n}. {s.text}" for s in p.sentences())
    return f"SENTENCES:\n{sentences}\n\nSOURCES:\n{source_brief(p)}\n\nWrite the storyboard JSON now."


def validate(p: Project, data: dict) -> tuple[list[str], list[str]]:
    """The checks `pvm check` runs, minus the anchor (a fresh draft has none)."""
    data = {k: v for k, v in data.items() if k != "sentences_hash"}
    try:
        sb = parse_storyboard(data)
    except PvmError as e:
        return [str(e)], []
    papers = p.sources()
    errors, warnings = check_storyboard(sb, [s.text for s in p.sentences()], set(papers), ignore_anchor=True)
    ev_errors, ev_warnings, _ = check_evidence(sb, p.source_texts(), papers, strict=False)
    return errors + ev_errors, warnings + ev_warnings


def plan(p: Project, llm: LLM, *, force: bool = False, temperature: float = 0.3) -> dict:
    """Draft storyboard.json (or storyboard.draft.json when one exists and force is off)."""
    prompt = plan_prompt(p)
    reply = llm.json(PLAN_SYSTEM, prompt, temperature=temperature, max_tokens=PLAN_TOKENS, project=p.slug)
    draft = reply.data
    errors, warnings = validate(p, draft)
    rounds = 1
    if errors:
        repair = (prompt + "\n\nYOUR PREVIOUS STORYBOARD:\n" + json.dumps(draft, ensure_ascii=False)
                  + "\n\nA program found these problems:\n" + "\n".join(f"- {e}" for e in errors)
                  + "\n\nReturn the corrected storyboard as one JSON object. Keep everything that was right.")
        reply = llm.json(PLAN_SYSTEM, repair, temperature=temperature, max_tokens=PLAN_TOKENS, project=p.slug)
        draft = reply.data
        errors, warnings = validate(p, draft)
        rounds = 2
    draft.pop("sentences_hash", None)
    target = p.storyboard_path if force or not p.storyboard_path.exists() else p.dir / "storyboard.draft.json"
    write_json(target, draft)
    meta = {"at": now_iso(), "prompt_version": PLAN_VERSION, "model": reply.model, "temperature": temperature,
            "input_hash": stable_hash([PLAN_SYSTEM, prompt])[:16], "rounds": rounds, "usage": reply.usage,
            "errors": errors, "warnings": warnings, "file": target.name}
    write_json(p.dir / "storyboard.plan.json", meta)
    return meta


REVIEW_SYSTEM = """You review the claims of a Chinese explainer video against quoted evidence from its source paper.
Reply with one JSON object:
{"claims": [{"index": 1, "supported": true, "issues": [], "fix": ""}], "hook": {"supported": true, "issues": [], "fix": ""}}

- supported: the sentences say no more than the excerpts show. An interpretation or advice claim is supported when it
  reads clearly as a reading or suggestion and does not contradict the evidence.
- issues, from this list: "causation" (correlation stated as cause), "population" (a sample generalized to everyone),
  "magnitude" (an effect inflated), "certainty" (a hedged finding stated as proven), "other".
- fix: a corrected Chinese sentence when not supported, otherwise "".
- For the hook, judge what a viewer who sees it over the paper would believe the paper says."""


def review(p: Project, llm: LLM) -> dict:
    sb = p.storyboard()
    sentences = {s.n: s.text for s in p.sentences()}
    items = []
    for i, c in enumerate(sb.claims, 1):
        text = "".join(sentences[n] for n in range(c.sentences[0], c.sentences[1] + 1))
        items.append({"index": i, "type": c.type, "sentences": text, "excerpts": [e.excerpt for e in c.evidence]})
    hook = {"lines": sb.hook, "type": sb.hook_claim.type if sb.hook_claim else None,
            "excerpts": [e.excerpt for e in sb.hook_claim.evidence] if sb.hook_claim else [],
            "basis": sb.hook_claim.basis if sb.hook_claim else None}
    # The citation carries journal, year and authors, which sentences introducing the paper rely on.
    sources = "\n".join(f"[{sid}] {paper.citation()}\n    abstract: {paper.abstract or '(none)'}"
                        for sid, paper in p.sources().items())
    user = json.dumps({"claims": items, "hook": hook}, ensure_ascii=False, indent=1) + "\n\nSOURCES:\n" + sources
    reply = llm.json(REVIEW_SYSTEM, user, temperature=0.0, max_tokens=PLAN_TOKENS, project=p.slug)
    result = {"at": now_iso(), "prompt_version": REVIEW_VERSION, "model": reply.model,
              "input_hash": stable_hash([REVIEW_SYSTEM, user])[:16], "claims": [], "hook": reply.data.get("hook") or {}}
    by_index = {int(c.get("index", 0)): c for c in reply.data.get("claims", []) if isinstance(c, dict)}
    for item in items:
        verdict = by_index.get(item["index"], {"supported": None, "issues": ["other"], "fix": "",
                                               "note": "no verdict returned"})
        result["claims"].append({**item, "supported": verdict.get("supported"), "issues": verdict.get("issues", []),
                                 "fix": verdict.get("fix", "")})
    result["passed"] = all(c["supported"] is True for c in result["claims"]) and result["hook"].get("supported") is True
    write_json(p.dir / "review.json", result)
    return result


def unsupported(result: dict) -> list[str]:
    out = []
    for c in result["claims"]:
        if c["supported"] is not True:
            issues = ", ".join(c.get("issues") or []) or "unclear"
            out.append(f"claim {c['index']} ({c['type']}): {issues}. {c['sentences']}"
                       + (f"\n      suggested: {c['fix']}" if c.get("fix") else ""))
    hook = result.get("hook") or {}
    if hook.get("supported") is not True:
        out.append(f"hook: {', '.join(hook.get('issues') or []) or 'unclear'}"
                   + (f"\n      suggested: {hook['fix']}" if hook.get("fix") else ""))
    return out

