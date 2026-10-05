# pvm: evidence-led paper explainer videos

`pvm` turns a research paper and a narration script into a Douyin-style explainer video. The video opens on the
paper, then walks through paper-cut collage posters. Every research claim in it is traceable to a verbatim quote
from the source.

- **Spec:** [`docs/spec.md`](docs/spec.md) (v1.1). The benchmark measurements behind it are in §2.
- **Storyboard format and working rules for agents:** [`AGENTS.md`](AGENTS.md).

## Setup (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This creates `.venv`, installs the dependencies, downloads the openly licensed fonts (about 50 MB), creates `.env`
from `.env.example`, and runs the tests. Add API keys to `.env` as each milestone needs them.

## Workflow

Run each command as `.venv\Scripts\python -m pvm <command>`:

```text
pvm research "sunk cost" -q "sunk cost effect decision making" --since 2000
pvm script sunk-cost --file script.txt
pvm paper sunk-cost --pick sunk-cost:c01     # attaches src1; downloads the PDF if it is open access
pvm sentences sunk-cost                      # numbered sentences for storyboard.json
pvm source sunk-cost --find "sunk cost"      # the exact source text to quote as evidence
pvm plan sunk-cost --auto                    # LLM draft of storyboard.json (or write it by hand: AGENTS.md)
pvm check sunk-cost                          # schema, claims, verbatim excerpts, rights, anchor
pvm review sunk-cost                         # LLM check of each claim and the hook for overreach
pvm voice sunk-cost                          # narration, timeline and subtitles (edge-tts or Ark)
pvm animatic sunk-cost                       # checkpoint 2: full-length preview, no image quota spent
pvm images sunk-cost --dry-run              # prompts and AFP estimate; then without --dry-run to generate
pvm render sunk-cost --ratio both            # final 3:4 + 9:16, cover, description, manifest, QA
pvm render sunk-cost --draft                 # same, but missing images become placeholders
```

## Status

| Milestone | Scope | State |
|---|---|---|
| M1 Foundation | CLI; claims with verbatim-excerpt verification; storyboard anchor; open-access and license detection; font policy; subtitle fixes; quota pacing; tests | done |
| M2 Voice and timeline | TTS per sentence with word timestamps and a cache; voice track; timeline; SRT | done |
| M3 Renderer and animatic | Compositor for every scene type; hook, subtitles, source chip, AI label; parallel x264 encode; loudness to −12 LUFS / −1 dBTP; AIGC metadata; animatic; QA | done |
| M4 Images | Seedream adapter, prompt compiler, per-attempt cache, retry budget with OCR label gate, AFP ledger, review/accept flow | done, verified live |
| M5 Planner | DeepSeek storyboard drafts (checked, one repair round) and claim review | done, verified live |
| Mascot | Original science-communication mascot: model sheet and 18 poses in `assets/mascot/` (`pvm mascot`) | done |

## Live services

One Agent Plan key (`AGENT_PLAN_API_KEY` in `.env`) covers everything. Verified on 2026-09-28:

- **Voice:** Ark TTS with per-character timestamps (`enable_subtitle`).
- **Images:** Seedream 5.0 lite; the first poster passed the OCR gate on attempt 1 (99 AFP).
- **Planner and claim review:** DeepSeek V4 Pro through the plan (`deepseek-v4-pro-beta`). Set
  `PVM_LLM_API_KEY` to use DeepSeek's own API instead.

A worked example lives in `projects/demo-social-capital/`: script, reviewed storyboard, voice, poster,
and final 3:4 and 9:16 renders that pass QA. Its poster predates the mascot (style pack v2), so
`pvm images demo-social-capital` will regenerate it with the mascot reference.

**Subscription:** on 2026-10-02 the API started answering `InvalidSubscription` (the Agent Plan had expired).
Until the plan is renewed in the Volcano Ark console, `pvm images`, `pvm mascot`, `pvm plan` and `pvm review`
fail with that message. `pvm voice` in auto mode falls back to free edge-tts for the whole video. Everything
else (checks, animatic, rendering, QA) runs offline.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -t .
```
