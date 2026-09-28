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
# write projects\sunk-cost\storyboard.json (see AGENTS.md), then:
pvm check sunk-cost
pvm voice sunk-cost                          # narration, timeline and subtitles (edge-tts or Ark)
pvm animatic sunk-cost                       # checkpoint 2: full-length preview, no image quota spent
pvm render sunk-cost --ratio both            # final 3:4 + 9:16, cover, description, manifest, QA
pvm render sunk-cost --draft                 # same, but missing images become placeholders
```

## Status

| Milestone | Scope | State |
|---|---|---|
| M1 Foundation | CLI; claims with verbatim-excerpt verification; storyboard anchor; open-access and license detection; font policy; subtitle fixes; quota pacing; tests | done |
| M2 Voice and timeline | TTS per sentence with word timestamps and a cache; voice track; timeline; SRT | done |
| M3 Renderer and animatic | Compositor for every scene type; hook, subtitles, source chip, AI label; parallel x264 encode; loudness to −12 LUFS / −1 dBTP; AIGC metadata; animatic; QA | done |
| M4 Images | Seedream adapter, prompt compiler, cache, OCR gate | next |
| M5 Planner | DeepSeek storyboard drafts and claim review | planned |

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -t .
```
