# AGENTS.md

A guide for coding agents, and for people, working in this repository. The product spec is
[`docs/spec.md`](docs/spec.md) (v1.2). Read §6 (sources and evidence) and §8.2 (who draws what) before
writing a storyboard.

## Environment

- Windows, with a Python 3.12 virtual environment in `.venv`. Run commands as `.venv\Scripts\python -m pvm <command>`.
- Run the tests with `.venv\Scripts\python -m unittest discover -s tests -t .` and keep them passing.
- Video data lives in `projects/`, `research/` and `cache/`, all git-ignored. Set `PVM_HOME` to put them elsewhere.
- `pvm fonts` downloads the openly licensed fonts into `assets/fonts/`. Rendering refuses proprietary system fonts
  unless `PVM_ALLOW_SYSTEM_FONTS=1`. Never set that for published videos.

## Making a video

1. `pvm research "<topic>" -q "<English query>" -q "<another>"` writes ranked candidates to `research/<slug>/candidates.md`.
2. `pvm script <project> --file script.txt` creates the project. Put one paragraph per line.
3. `pvm paper <project> --pick <research-slug>:c03` (or `--doi <doi>`) attaches the paper as `src1`, and downloads
   the open-access PDF when there is one. For a closed paper, save the operator's own copy as
   `projects/<project>/sources/src1.pdf`.
4. `pvm sentences <project>` prints the numbered sentences. `pvm source <project> --find "<phrase>"` shows the exact
   source text to quote.
5. Write `projects/<project>/storyboard.json` (format below), or draft it with `pvm plan <project> --auto` and then
   read and correct the draft. `pvm review <project>` asks the LLM to check every claim and the hook for overreach.
   Both run on `deepseek-v4.1-flash` through the Agent Plan unless `PVM_LLM_API_KEY` is set, and each call is
   billed in AFP. The plan's terms reserve its text models for AI tools rather than API calls; the operator
   accepted that risk (spec §7.3). Draft once and review once per storyboard rather than looping on them.
6. Run `pvm check <project>` until it prints `ok`. Before a final render, `pvm check <project> --strict` must pass too.
7. `pvm voice <project>` builds the narration and timeline; `pvm animatic <project>` renders the zero-quota preview
   for checkpoint 2.
8. `pvm images <project> --dry-run` shows the compiled prompts and the AFP estimate; without `--dry-run` it generates,
   checks every label with OCR and retries up to the budget. A failed image is left as `visuals/<scene>.candidate.png`
   for review (`--accept <scene>` after looking at it).
9. `pvm render <project> --ratio both` renders the final videos and runs QA; `--draft` allows placeholder panels.

## Writing storyboard.json (version 2)

### Rules that `pvm check` enforces

- **Coverage.** `scenes` and `claims` each cover every sentence exactly once, in order: `[1, 3]`, then `[4, 6]`, and so on.
- **Claim types.** Every claim is `source_fact`, `interpretation` or `advice`.
- **Evidence.** A `source_fact` needs `"evidence": [{"source": "src1", "excerpt": "..."}]`. Each excerpt is copied
  **verbatim** from the source and is at least 6 words long. `pvm check` looks for it in the title, the abstract and
  the PDF text. A paraphrase fails, and so does a translation.
- **Unverifiable excerpts.** If only the title and abstract are available, an excerpt from the body is a warning, and
  an error under `--strict`. Add the PDF.
- **The hook.** `hook_claim` is required, because the hook sits on the paper and viewers read it as the paper's
  finding.
  - A `source_fact` hook needs evidence.
  - An `interpretation` or `advice` hook needs a `basis`: one sentence on how it follows from the paper.
- **Labels** (`sections[].labels`) are drawn by the image model. Keep them to 7 characters at most and 4 per section,
  with no digits and no Latin letters. Numbers, names and citations go in headings or narration, which code draws.
- **Paper display.** A `paper` scene with `"source": "auto"` shows what the license allows: the full page, the title
  region, or a citation card. `paper_scroll`, and `"source": "pdf"` on a closed paper, need `"rights": "permitted"`,
  which records that the operator holds permission. `"landing"` is not supported.
- **Anchor.** `pvm check` writes `sentences_hash` into the storyboard. If `script.txt` changes later, fix the ranges
  against `pvm sentences`, then run `pvm check --reanchor`.

### Judgment rules (code cannot check these, so you are responsible)

- Never invent a paper, DOI, number, sample size, effect or quote.
- Keep correlation apart from causation. "Is among the strongest predictors of X" is not "causes X". A sample is not
  "everyone", and "a study found" is not "science proves".
- A sentence that introduces the paper (journal, year, authors, institution) is a `source_fact`. Quote the title, or
  the affiliation line from the PDF.
- When the evidence is thin, write the sentence as an interpretation ("一种可能的解释是…", "可以这样理解…") and label
  it that way.
- The hook is 1–3 lines of 2–7 characters. Before you keep a hook, ask: would a viewer seeing it over the paper
  believe the paper says it? "越不懂越自信" fails for Kruger & Dunning (1999); "越不懂，越高估自己" passes.
- A warning about research wording ("sentence N uses research wording…") means a sentence sounds like a finding but
  is not labeled `source_fact`. Relabel it with evidence, or rephrase it.

### Scene types

| Type | Key fields | Notes |
|---|---|---|
| `paper` | `paper` (source id), `source` (`auto`/`pdf`/`card`), `page`, `highlights` `[{text, at}]`, `zoom`, `rights` | The opening. Highlight text must appear on the page |
| `paper_scroll` | `paper`, `pages` `[first, last]`, `speed`, `rights` | Open-licensed papers only, unless `rights: "permitted"` |
| `poster` | `title` (≤ 8 characters), `sections` `[{heading, visual, labels, at}]` | 2–4 sections, 3 is the house style. `at` is the sentence where that panel takes focus |
| `summary` | `title`, `label`, `sections` | Ending. Code draws the citation block |
| `image` | `title`, `visual` | One full illustration |
| `text` | `lines`, `pose` | Emphasis card; `pose` shows a mascot pose under the lines |

`visual` is an English brief for the illustration, at most 60 characters: the mascot, an action, and 2–3 props.
Describe the scene, not text.

A complete example is in `docs/spec.md` §14.2.

## The mascot

- The design lives in `assets/mascot/mascot.json`; the model sheet and 18 cut-out poses are in `assets/mascot/`
  (`contact.png` shows them all). Poses: front, wave, point, explain, think, idea, surprised, puzzled, investigate,
  read, compare, caution, shrug, thumbsup, write, walk, worried, celebrate.
- Use a pose on a text card with `"pose": "caution"`. Caution suits counterpoints and boundaries; shrug suits
  "we don't know yet".
- Every poster prompt passes the model sheet as its reference image, so the character stays the same.
- Changing `description` or the sheet invalidates every pose (19 images, about 2,850 AFP at 150 each). Change one
  pose's text to regenerate only that pose: `pvm mascot --pose read`. `pvm mascot --recut` redoes the transparent
  cut-outs from the kept originals for free.
- Switching the image model does not invalidate accepted assets: fingerprints record the shape (16:9 sheet, 3:4
  poses), not the pixel size, which follows the model.

## Code conventions

- Python 3.12, Pydantic v2, Pillow, pypdfium2, and FFmpeg through imageio-ffmpeg. No services.
- Raise `PvmError` for expected, user-facing failures; the CLI prints them without a traceback.
- Write files with `util.write_json`, `util.write_text` or `util.write_bytes`. They are atomic and retry on Windows
  file locks.
- Build data paths from `util.data_dir()`, never from `ROOT`, so that `PVM_HOME` keeps working.
- Code draws everything on screen except in-scene labels (spec §8.2).
- Every behavior change comes with a test in `tests/`.
