# pvm: evidence-led paper explainer videos

`pvm` turns a research paper and a narration script into a Douyin-style explainer video. The video opens on the
paper, then walks through paper-cut collage posters. Every research claim in it is traceable to a verbatim quote
from the source.

- **Spec:** [`docs/spec.md`](docs/spec.md) (v1.2). The benchmark measurements behind it are in §2.
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

One Agent Plan key (`AGENT_PLAN_API_KEY` in `.env`) covers images, voice and the LLM. Verified on 2026-10-07,
after the plan was renewed:

- **Voice:** Ark TTS with per-character timestamps (`enable_subtitle`). It costs 1,350 AFP per 10,000
  characters, and new sentences are recorded in the AFP ledger.
- **Images:** Seedream 5.0 pro at 1.5K, 150 AFP per image. Seedream 5.0 lite left the plan in October 2026.
  The redrawn `read` and `compare` poses and the demo poster each passed their checks on the first attempt.
- **Planner and claim review:** DeepSeek V4.1 Flash through the plan (`deepseek-v4.1-flash`), billed in AFP
  and recorded in the ledger. On the demo, a draft passed every check in one round (40 s, 4 AFP), and the
  review passed all claims (17 s, 1 AFP). The plan's terms reserve its text models for AI tools rather than
  API calls; this route was chosen knowing that (spec §7.3). Set `PVM_LLM_API_KEY` to use DeepSeek's own
  API instead.

Set `PVM_PLAN_START` to the plan's purchase date: the plan's month, and its quota, starts on that day.
`pvm quota` shows the cycle and today's allowance.

A worked example lives in `projects/demo-social-capital/`: script, reviewed storyboard, voice, a poster with
the mascot, and final 3:4 and 9:16 renders that pass QA. `projects/nature-120min/` is a full 60-second video on
White et al. (2019), made end to end with these commands. It covers every scene type and cost 354 AFP, which the
manifest itemizes.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -t .
```
