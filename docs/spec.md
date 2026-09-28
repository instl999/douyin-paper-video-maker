# Evidence-Led AI Short-Video Factory

## Product & Technical Specification

**Volcano Ark Agent Plan (Seedream, TTS) + DeepSeek API + deterministic Python rendering**
**Based on measured analysis of seven benchmark Douyin videos supplied by the user**
**Version 1.1 — September 26, 2026** (supersedes v1.0 of September 24, 2026)

---

## 0. What Changed in v1.1

Version 1.0 was reviewed against the benchmark files themselves and against the first implementation (`pvm/`). Several of its statements did not hold up when measured. This version replaces them. Everything else in v1.0 that held up is carried forward.

| Area | v1.0 | v1.1 | Why |
|---|---|---|---|
| Benchmark pacing | One visual per 8–15 s; 7–10 visuals per video | One poster per ~25 s (16–40 s); 4–5 posters per video; each poster has 3 panels of ~8 s | Measured with ffmpeg scene and freeze detection (§2) |
| Image budget | ~12 images ≈ 1,188 AFP per video | ~7–8 images ≈ 740 AFP per video | Follows from the measured pacing (§12) |
| Motion | "Relatively light" | The benchmarks are 87–99% frozen above the subtitles. Motion comes from panel focus inside a poster | Measured (§2.2) |
| Text in images | The image model never draws text | Code draws facts and structure. The model may draw short labels inside a scene, and every label is checked by OCR | Benchmark posters show clean model-drawn Chinese labels, but facts must never depend on the model (§8.2) |
| Claims | A `source_fact` needs a `source_id` | Every sentence has a claim type. Every `source_fact` carries a verbatim excerpt that the tool finds in the source text. The hook is a claim too | A source id alone can be attached to anything (§6.3–6.5) |
| Paper pages | General rights warning | What is shown follows the paper's license: full page, title region, or citation card | 6 of the 7 benchmark papers are closed-access (§6.6) |
| Compliance | Facts, screenshots, IP | Adds AI-content labeling, font licensing and platform homogeneity risk | Missing from v1.0 (§13) |
| Stack | Next.js, Node, BullMQ/Temporal, Postgres, object storage, Remotion | Python CLI, one folder per video, content hashes. Services are added only when needed | Phase 1 is a single-operator tool (§5) |
| Timing | ASR / forced alignment | TTS word timestamps, with `jieba` word boundaries as a fallback | Removes a whole component (§10) |
| Quota | The plan's daily cap used as the daily budget | The monthly budget is paced over the days left in the cycle | The daily cap is half the monthly quota, so using it as a budget empties the month in two days (§8.6) |
| Workflow | Checkpoints implied | Three explicit checkpoints, including a zero-quota animatic before any image is generated | Quota is spent only on approved storyboards (§4) |

---

## 1. Executive Summary

The concept is viable and distinctive. Its core bet is right: an explainer that leads with real evidence, keeps every research claim traceable to a source, prepares every asset in advance and renders the video with deterministic code.

The production chain is:

> source → script → sentences → storyboard with typed claims → checks → voice with timestamps → zero-quota animatic → posters → OCR verification → render → QA → publish checklist

The recommended positioning is an **Evidence-Led AI Explainer Video Factory**, not a generic "AI auto-editing" product.

Six principles guide the implementation:

1. **Precompute everything.** Nothing is generated while the video plays. Every image, voice clip and timing is produced, checked and cached before rendering.
2. **Code draws facts and structure; the model draws scenes.** Code renders DOIs, authors, years, venues, numbers, poster titles, numbered badges, panel headings, the hook and the subtitles. The image model may draw short labels inside a scene (on paper tags, signs and arrows), and every such label is checked by OCR.
3. **Every claim is typed and traceable.** Each sentence is labeled `source_fact`, `interpretation` or `advice`. Each `source_fact` carries a verbatim excerpt that the tool locates in the source text. The hook shown over the paper is a claim as well.
4. **An original recurring mascot, built once as a pose library.** The character is generated once, reused in every video, and never resembles an existing character or another creator's persona.
5. **Quota is a scheduling constraint.** The monthly budget is paced, and paid calls are cached and logged. No image is generated before the operator approves the animatic.
6. **Publish responsibly.** Output carries AI-content labels, uses only openly licensed fonts, and shows paper pages only as far as their license allows.

The guiding engineering principle is unchanged:

> **Use AI for judgment and asset generation; use software for layout, timing, verification, traceability and scale.**

---

## 2. Benchmark Findings (measured)

All numbers in this section come from the seven benchmark files, measured with ffmpeg 7.1 and the OpenAlex API. The method is in §2.5.

### 2.1 Samples

| # | File | Duration | Resolution | Paper | License (OpenAlex) | Format |
|---|---|---:|---|---|---|---|
| 1 | `owvZ1VCk….mp4` | 127.2 s | 1080×1440 | Chetty et al., *Nature* 2022 — "Social capital I" | CC-BY | Paper wall + summary card |
| 2 | `oIPT4IAM….mp4` | 135.6 s | 1920×2560 | Scholer, Hubley & Fujita, *Nature Reviews Psychology* 2024 | closed | Hybrid |
| 3 | `video_为什么一定要远离蠢人…` | 115.1 s | 1080×1440 | Kruger & Dunning, *JPSP* 1999 | closed | Hybrid |
| 4 | `video_为什么权衡利弊…` | 157.6 s | 1080×1440 | Mann, Burnett, Radford & Ford, *J. Behavioral Decision Making* 1997 | closed | Hybrid |
| 5 | `oI8mYBaq….mp4` | 132.0 s | 1080×1440 | Sheldon & Elliot, *JPSP* 1999 | closed | Paper wall + summary card |
| 6 | `o8iBPlcf….mp4` | 143.6 s | 1080×1440 | Sivanathan & Pettit, *J. Experimental Social Psychology* 2010 | closed | Hybrid |
| 7 | `video_成长最快的方式…` | 114.1 s | 1080×1440 | Aryee & Chu, *Human Performance* 2012 | closed | Hybrid |

All seven videos are 3:4 at 30 fps. The mean duration is 132 s (range 114–158 s).

### 2.2 Measured pacing

| # | Hook on screen | Opening (hook + paper) | Posters | Poster holds (s) | Frozen above subtitles |
|---|---:|---:|---:|---|---:|
| 1 | 8.5 s | paper for ~105 s | 1 summary card | 22.1 | 94% |
| 2 | 7.8 s | 20.2 s | 4 | 22.1 · 23.7 · 40.1 · 29.4 | 99% |
| 3 | 7.9 s | 22.6 s | 4 | 16.7 · 28.5 · 20.9 · 26.4 | 87% |
| 4 | 6.0 s | 18.8 s | 5 | 24.5 · 28.9 · 34.3 · 27.0 · 24.2 | 95% |
| 5 | 10.5 s | paper for ~124 s | 1 summary card | 7.7 | 89% |
| 6 | 8.6 s | 13.5 s | 5 | 26.1 · 27.0 · 31.3 · 21.6 · 24.2 | 96% |
| 7 | 7.7 s | 12.3 s | 5 | 20.2 · 23.0 · 18.6 · 23.9 · 16.1 | 98% |

Across the 23 posters in the five hybrid videos, a poster stays on screen for 16–40 s, 25 s on average.

What this means:

- **The unit of generation is a poster (~25 s). The unit of narration is a panel (~8 s).** Each poster has three numbered panels, and the narration moves through them. v1.0's "8–15 s per visual" describes a panel, not an image.
- **Nothing moves except the subtitles.** Posters and paper pages hold perfectly still.
- **The hook appears over the paper at frame 0** and stays for 6–10.5 s. It is not preceded by a bare paper shot.
- **Audio is hot.** Six of the seven videos measure about −11 LUFS integrated, with true peaks of +0.4 to +0.7 dBFS, so they clip. Sample 4 is an outlier at −28 LUFS.

### 2.3 Visual language

- **Opening:** a full paper page with a very large yellow hook in a heavy face with a thick black outline. The hook has two lines of 2–7 characters each ("及时/止损", "人生就是比/谁先找到自己").
- **Subtitles:** white heavy sans with a black outline. They usually show one line of about 9–12 characters, with the baseline at about 93% of frame height. When they wrap, the second line is sometimes orphaned ("财富上限往往不是由努力/决定").
- **Posters:** paper-cut collage on ivory paper.
  - A title of at most 8 characters sits over an ochre underline bar.
  - Three numbered panels follow, with navy number badges and headings of mostly 4–7 characters. The middle panel is framed.
  - The mascot appears two or three times per panel.
  - Short labels sit on torn paper tags, signposts and arrow chips.
- **Summary card (samples 1 and 5):** a "<creator>的总结" title, a citation block (paper title, DOI, venue and year), then three panels that include numbers such as sample sizes and percentages.
- **Model-drawn text:** the Chinese labels inside the posters are clean even at 1920×2560, so current image models draw short Chinese labels reliably. The summary cards also carry facts (a DOI, sample sizes) inside the illustration, which is exactly the failure mode §8.2 rules out.
- **Mascot:** the recurring character is the benchmark creator's persona (西门). It must not be echoed.

### 2.4 What to improve

| Benchmark pattern | Risk | Improvement |
|---|---|---|
| Posters hold still for 16–40 s | Visual fatigue, weaker retention | Panel-by-panel focus and a slow push-in; nothing above the subtitles frozen for more than 5 s |
| The paper is shown as decoration, under hooks it does not support ("远离蠢人" over Kruger & Dunning) | Misrepresenting research | Claim types, verified excerpts, the hook treated as a claim, a source chip during source-fact sentences |
| Facts drawn inside AI images | Silent digit errors on the "evidence" card | Facts drawn by code only |
| Closed papers shown page by page for about two minutes (sample 5) | Rights | License-aware display (§6.6) |
| Hot, clipping audio | Distortion on phone speakers | −12 LUFS integrated, −1 dBTP ceiling |
| Orphaned subtitle lines | Readability | Balanced wrapping, at most 14 characters per line |
| Another creator's persona as mascot | Brand and IP | Original mascot built as a pose library |

### 2.5 How the numbers were measured

Re-run these on any new benchmark before changing the format.

```text
# Cuts, frozen stretches and black gaps, measured on the top 82% of the frame so subtitle changes do not count
ffmpeg -i in.mp4 -an -f null - -vf "scale=270:360,crop=270:295:0:0,freezedetect=n=0.001:d=2,blackdetect=d=0.1:pix_th=0.12,select='gt(scene,0.18)',showinfo"

# Loudness
ffmpeg -i in.mp4 -vn -af ebur128=peak=true -f null -
```

Licenses come from OpenAlex (`best_oa_location.license` and `.version`).

---

## 3. Creative Format

The format keeps the recognizable "paper evidence + visual explanation" grammar of the benchmarks. It adds motion inside posters, claims that viewers can trace, and an original recurring character.

### 3.1 Structure of a 120–150 s video

| Time | Function | Visual | Claim type |
|---|---|---|---|
| 0 s | Hook and evidence together | Source page (or citation card) with the hook over it | The hook is a claim (§6.5) |
| 0–8 s | Source and one-line finding | Highlight sweep over the finding; author · year · venue | `source_fact` |
| 8–20 s | Bridge from the paper to the topic | Push-in on the highlighted passage, or the first poster | `interpretation` |
| 20–110 s | 3–4 posters × 3 panels | Collage posters with panel focus | Mixed, each sentence labeled |
| 110–130 s | Boundary / counterpoint | Contrast poster (2 panels) | `interpretation` |
| 130–150 s | Summary and source | Summary card with the citation block | — |

There are two opening lengths:

- **Retention mode:** the first poster appears by 12 s.
- **Research-channel mode:** the opening may run up to 25 s. It must still include highlights and push-ins, never a static page.

### 3.2 Posters and panels

A poster is generated once and carries about 25 s of narration. It has three panels (2–4 allowed), and each panel is one step of the argument, about 8 s. A new poster is generated when the narrative logic changes, not when a new sentence starts.

This matches the benchmarks and halves the image count compared with v1.0.

### 3.3 Motion inside a poster

- **Panel focus:** the panel being narrated lifts slightly (about 2% scale and a stronger shadow) while the others dim a little. The change eases in over about 0.4 s.
- **Push-in:** a slow 2–4% zoom over the whole poster.
- **Small entrances:** heading tags, highlight sweeps.
- **Precision:** all motion is sub-pixel accurate (§10.4).

### 3.4 Summary card

The summary card has a title, a citation block drawn by code (title, authors, year, venue, DOI) and three panels summarizing the takeaways. Any number on the card is drawn by code.

---

## 4. Product Form and Workflow

The product is a **controlled semi-automatic production line**, not a one-click black box.

### 4.1 Workflow and checkpoints

1. **Source and claims (checkpoint 1).**
   - The operator chooses the source or sources. The tool shows license, open-access status and the resulting display policy.
   - The tool also shows the abstract and the PDF text so excerpts can be quoted exactly.
2. **Script and storyboard.**
   - The script is split into numbered sentences. The operator, or a coding agent following `AGENTS.md`, writes `storyboard.json`: claims, hook claim, scenes, panel briefs and labels.
   - `pvm check` validates it (§6.4, §11).
3. **Animatic (checkpoint 2).**
   - A full-length preview uses the real voice and timing, with placeholder panels showing each panel's brief and labels.
   - It costs no image quota. The operator approves timing, structure and claims here.
4. **Visuals.**
   - Posters are generated with caching, a retry budget and the OCR gate. A single poster, or a single panel, can be regenerated without touching the rest.
5. **Render and QC (checkpoint 3).**
   - The final render runs automated QA (§13.1). The operator watches it once and works through the publish checklist, which includes the Douyin AI declaration.

### 4.2 Two modes

| Mode | Workflow | Best for |
|---|---|---|
| Fast | The operator supplies the script and the source; the system does the rest | Reliable, frequent publishing |
| Research | The system first proposes sources and verified claims, then the script | A research-led channel |

### 4.3 Outputs per video

- `final_3x4.mp4`, plus `final_9x16.mp4` when requested
- `animatic.mp4`
- `cover.png`
- `subtitles.srt`
- `description.txt`: the citation and the AI-declaration reminder
- `manifest.json`: every version and asset used (§13.7)
- `qa.json`: automated QA results

### 4.4 Scheduling without homogeneity

Videos can be queued and paced by quota. Scheduling must never produce near-identical videos: structure, templates and poster layouts should vary, and every video carries its own evidence. See §13.6.

---

## 5. System Architecture

The central boundary is unchanged:

> **LLMs and image models output structured decisions and assets. Typography, dimensions, timing, transitions, subtitles, facts and source displays are controlled by deterministic code.**

### 5.1 Phase-1 stack

| Layer | Phase 1 (now) | Add later, only if needed |
|---|---|---|
| Interface | `pvm` command-line tool, plus a coding agent that follows `AGENTS.md` | Web console |
| Orchestration | Stage stamps (input hashes) in `project.json`; content-hash caches | Job queue, workflow engine |
| Storage | One folder per video under `projects/` | Database, object storage |
| LLM | DeepSeek API with JSON output | — |
| Images | Seedream through Agent Plan, behind an adapter | Fallback providers |
| Voice | Ark TTS (Agent Plan) for final renders; edge-tts (free) for drafts and animatics | — |
| Timing | TTS word timestamps; `jieba` word boundaries as a fallback | Forced alignment, only for human voiceover |
| Rendering | Pillow compositor in parallel worker processes → FFmpeg (x264, AAC, compression + limiting to the loudness target) | GPU or HTML renderer |
| QA | FFmpeg filters (freezedetect, blackdetect, ebur128); OCR (RapidOCR) | — |
| Monitoring | AFP ledger and per-video manifest | Metrics service |

Phase 1 runs on Python 3.12 on Windows, with no services. Remotion, proposed in v1.0, needs a paid company license for companies with more than three employees. That is one more reason to keep rendering in Pillow + FFmpeg.

### 5.2 Pipeline

```text
topic ─► research (OpenAlex, Crossref, …) ─► source + license + text ─┐
                                                                     │
script.txt ─► sentences ─► storyboard.json (claims, hook claim, scenes)
                                   │
                              pvm check ── schema · claims · evidence · rights · anchor
                                   │
                    TTS per sentence (cached, word timestamps)
                                   │
                              timeline ─► animatic (placeholders) ── checkpoint 2
                                   │
        prompt compiler ─► image provider (cache · ledger · retries) ─► OCR gate ─► posters
                                   │
           renderer (Pillow, parallel) ─► FFmpeg (loudness, AIGC metadata) ─► QA ── checkpoint 3
```

### 5.3 Project layout on disk

```text
projects/<slug>/
  project.json          metadata, sources, stage stamps
  script.txt            narration, one paragraph per line
  sentences.json        numbered sentences (derived)
  storyboard.json       claims, hook claim, scenes (authored, then anchored)
  sources/src1.pdf      source PDF (open-access copy or the operator's own)
  sources/src1.txt      optional plain text of the source
  audio/                voice.wav, subtitles.srt, timeline.json
  visuals/<scene>.png   accepted poster images (+ .json metadata)
  output/               animatic.mp4, final_3x4.mp4, cover.png, description.txt, manifest.json, qa.json
cache/                  tts/, images/, afp_ledger.jsonl
research/<slug>/        candidates.json, candidates.md
```

### 5.4 Commands

| Command | Purpose | Milestone |
|---|---|---|
| `pvm research "<topic>" -q …` | Search, merge and rank candidate papers | M1 |
| `pvm script <slug> --file …` | Create a project and set its script | M1 |
| `pvm sentences <slug>` | Print the numbered sentences for storyboard authoring | M1 |
| `pvm paper <slug> --doi … \| --pick …` | Attach a source and show its display policy | M1 |
| `pvm source <slug>` | Show the text available for quoting excerpts | M1 |
| `pvm check <slug> [--strict] [--reanchor]` | Validate the storyboard, claims, evidence and rights | M1 |
| `pvm fonts` | Download the openly licensed fonts | M1 |
| `pvm quota` | Show the monthly budget, usage and today's allowance | M1 |
| `pvm voice <slug>` | Synthesize speech per sentence and build the timeline and SRT | M2 |
| `pvm animatic <slug>` | Zero-quota preview render | M3 |
| `pvm render <slug>` | Final render (3:4 and/or 9:16) | M3 |
| `pvm qa <slug>` | Automated QA on the rendered file | M3 |
| `pvm images <slug> [--scene …]` | Generate or regenerate posters | M4 |
| `pvm plan <slug> --auto` | LLM draft of the storyboard | M5 |

---

## 6. Sources and Evidence

### 6.1 Sources are evidence objects

Each source records:

```text
title, authors, year, venue, volume, issue, pages
doi, url, pdf_urls
abstract, cited_by, type
is_oa, oa_status, license, license_version
openalex_id, origin
```

The text used to verify excerpts is the title, the abstract, the text of `sources/<id>.pdf` if present, and `sources/<id>.txt` if present.

### 6.2 Research flow

1. Turn the topic into 3–5 English academic queries (by the operator, or by the LLM in M5).
2. Search OpenAlex and Crossref; Europe PMC, arXiv and Semantic Scholar are optional.
3. Merge the results by DOI.
4. Fill in open-access status and license from OpenAlex, in one batched lookup.
   - Crossref PDF links are publisher text-mining endpoints. They are **not** evidence of open access: in a live test, half of the Crossref results with PDF links were closed.
5. Rank by relevance, citations, venue, open access, recency, study type and whether an abstract exists.
6. The operator picks a source. The tool records its license and display policy.
7. Place the PDF in `sources/` (an open-access copy, or the operator's own copy) so excerpts can be verified against the full text.

### 6.3 Claim model

Every sentence of the script belongs to exactly one **claim**. Claims cover the sentences in order, with no gaps, just like scenes do.

| Type | Meaning | Evidence |
|---|---|---|
| `source_fact` | What the source reports | Required: at least one `{source, excerpt}` item |
| `interpretation` | Editorial reading, bridge, framing, question | Optional: the facts it builds on |
| `advice` | What the viewer could do | Optional |

An evidence item is `{"source": "src1", "excerpt": "<verbatim text>", "page": 3}`. The `page` field is optional.

Sentences that introduce the source ("published in JPSP by two Cornell psychologists") are `source_fact` too. Their excerpt is the title or the affiliation line.

When the evidence is thin, write the sentence as an interpretation: "一种可能的解释是…", "可以这样理解…". Stricter rules apply to psychology, health and finance: correlational studies never become causal language, a sample never becomes "everyone", and "a study found" never becomes "science proves".

### 6.4 Verification ladder

1. **Deterministic excerpt match.** Both texts are normalized: NFKC (which also resolves ligatures such as "ﬁ"), end-of-line hyphenation, curly quotes and dashes, whitespace, case. If that fails, a second match compares letters and digits only.
   - Not found in text that includes the full paper → **error**. Excerpts must be verbatim.
   - Only the title and abstract are available → **warning** in drafts, **error** in the final render (`--strict`). Add the PDF or a text file.
2. **Excerpt length.** Fewer than 6 words or characters is an error. More than 400 characters is a warning: quote the specific sentence.
3. **Research-language lint.** A sentence with research wording (研究, 实验, 数据, 样本, %, …) that is not labeled `source_fact` → warning.
4. **LLM claim review (M5).** Does the excerpt support the sentence without overreach in causation, population, magnitude or certainty?
5. **Operator sign-off** at checkpoints 1 and 2.

### 6.5 The hook is a claim

The hook sits on top of the paper, so viewers read it as the paper's finding. It needs its own claim:

- `hook_claim.type` is required.
- A `source_fact` hook needs evidence, verified like any other.
- An `interpretation` or `advice` hook needs a `basis`: one sentence explaining how it follows from the source. The claim review checks that basis.

Example: "越不懂越自信" is a popular misreading of Kruger & Dunning (1999). The low scorers overestimated themselves, but they still rated themselves below the high scorers. "越不懂，越高估自己" is supported by the excerpt "grossly overestimated their test performance and ability".

### 6.6 Showing paper pages

| Paper status | Opening shows | Scrolling through pages |
|---|---|---|
| Open license (CC-BY, CC-BY-SA, CC0, public domain) on the published version, PDF available | Full page with highlights and push-in | Allowed |
| Closed, or a non-commercial / no-derivatives license, PDF available | The title region of page 1 (title, authors, journal) | Only with `"rights": "permitted"` |
| No PDF | A citation card generated from metadata | — |

- `"rights": "permitted"` on a scene records that the operator holds permission to show the pages.
- Screenshots of publisher landing pages are not supported, because of both rights and anti-bot risk.
- This policy is a risk decision, not legal advice. Confirm with counsel before commercial use.

---

## 7. LLM (DeepSeek) Responsibilities

### 7.1 Roles

| Role | Output | Milestone |
|---|---|---|
| Research planner | English search queries and the claims to verify | M5 |
| Evidence extractor | Verbatim excerpts, which the §6.4 check then locates | M5 |
| Script writer | Hook → evidence → mechanism → example → boundary → summary | M5 |
| Storyboarder | A storyboard v2 draft with claims | M5; coding agents follow `AGENTS.md` until then |
| Claim reviewer | An overreach check for each claim and for the hook | M5 |
| Repair agent | Fixes only the failed node | Later |

The image prompt compiler is deterministic code, not an LLM (§15.2).

### 7.2 Structured output rules

- Validate every result against the schema (Pydantic).
- Retry only the failed step.
- Treat empty or invalid output as an explicit, recoverable failure.
- Prefer several small calls over one large call that does everything.
- Save `prompt_version`, `model`, `temperature` and `input_hash` with every output.
- Never invent a paper, DOI, sample size, effect size or quote. Excerpts are checked mechanically, so an invented quote fails §6.4.

---

## 8. Image Generation (Seedream via Agent Plan)

### 8.1 Provider adapter

```python
class ImageProvider(Protocol):
    name: str
    def generate(self, request: ImageRequest) -> GeneratedImage: ...
```

Agent Plan is the first adapter. Pay-as-you-go Ark and other providers sit behind the same interface. Business logic never knows which transport is in use.

### 8.2 Who draws what

| Text | Drawn by | Why |
|---|---|---|
| Citation: title, authors, year, venue, DOI | Code | Must be exact and traceable |
| Numbers, percentages, sample sizes | Code | A wrong digit is invisible to viewers |
| Poster title, numbered badges, panel headings | Code | Fixed positions; animated; re-laid out for 9:16 |
| Hook, subtitles, source chip, AI label | Code | Must be exact |
| Short labels inside a scene (tags, signs, arrows; ≤ 7 characters, ≤ 4 per panel, no digits) | Model | This is the collage look; OCR checks each label |

Image prompts list the allowed labels explicitly and forbid any other text, including digits and Latin letters.

### 8.3 OCR gate

- Run RapidOCR on every generated image.
- **Pass:** every requested label is found (after normalization), and no text containing digits or Latin letters appears.
- **Warning:** extra Chinese text appears.
- **Fail:** counts against the retry budget (§8.7).

### 8.4 Generate for the box

Request each image at the aspect ratio of the area it will fill, which is the three-panel area below the title. Do not request a full frame with instructions like "reserve the top 18%"; models do not follow percentage instructions reliably.

### 8.5 Panel positions

A poster is composed as a collage:

1. The generated image is cut into panel sheets at its gutters. The gutters are found by a row-profile scan; equal thirds are the fallback.
2. The sheets are pasted onto the paper background with shadows.
3. Code pins a numbered heading tag on each sheet.

Panel positions are therefore known by construction, so the focus can follow the narration. Per-panel generation (three images per poster) is available for quality mode, and to replace a single failed panel.

### 8.6 Quota pacing

- Daily allowance = (monthly budget − used this cycle) ÷ days left in the cycle, capped by the plan's daily limit.
- Every paid call is written to a ledger (`cache/afp_ledger.jsonl`).
- Thresholds by remaining budget: above 30%, normal operation; 10–30%, one candidate per poster; below 10%, approved jobs only.
- Never assume the plan continues seamlessly after quota exhaustion. Defer, reuse cached assets, or switch to a configured fallback provider.

### 8.7 Cache and retries

- Cache key: hash of the prompt, reference assets, model, size, style-pack version and provider parameters.
- Accepted images are reused when re-rendering. A re-render never pays twice.
- At most 3 attempts per poster, OCR failures included. After that the poster goes to manual review with the best candidate kept.

---

## 9. Visual Consistency

### 9.1 Original mascot as a pose library

- Design an original researcher mascot. It must not resemble an existing anime or entertainment character, or the benchmark creator's persona.
- Generate 20–30 text-free poses once: thinking, pointing, surprised, rejecting, presenting, holding a book, walking, sitting, and so on. Cut them out onto transparent backgrounds and store them in `assets/mascot/`.
- Posters either composite poses from the library (collage mode), or pass 2–3 poses to the image model as references.
- Benefits: an identical character in every video, zero quota per video, and a series look that survives model upgrades.

### 9.2 Style pack

A versioned style pack defines:

- the palette: ivory background `#F4EFE6`, ink `#1E1E1E`, navy badges `#1F3A5F`, ochre underline `#E3A21A`, hook yellow `#FFE11A`
- paper texture, line style and collage rules (torn edges, drop shadows)
- fonts
- the mascot description and references

Its version is part of every image cache key and of the manifest.

### 9.3 Templates

| Template | Structure | Use |
|---|---|---|
| T1 Paper hook | Source page (per §6.6) with the hook, highlights and a push-in | Opening |
| T2 Three-panel poster | Title + 3 numbered panel sheets | Mechanism, steps, examples |
| T3 Contrast | Title + 2 panels | Misconception vs. better reading, boundary |
| T4 Sequence | Title + 3–4 panels | Cause → process → result |
| T5 Summary card | Citation block + 3 panels | Ending |
| T6 Text card | Large lines of text | Emphasis; animatic placeholders |

The consistent "same series" feeling comes from fixed templates, the pose library and controlled typography. The image model is not asked to improvise a whole poster.

---

## 10. Voice, Subtitles, Timeline, Audio

### 10.1 Order

1. Script
2. Sentences
3. TTS per sentence (cached)
4. Timeline from the real durations
5. Render

Scene durations are never fixed before the voice exists.

### 10.2 TTS

- Ark TTS (Agent Plan) is used for final renders; edge-tts (free) is used for drafts and animatics.
- The engine's word timestamps are mapped to character offsets in each sentence.
- Pauses are 0.25 s between sentences and 0.5 s at paragraph ends.
- Audio is cached per sentence, keyed by engine, voice, speed and text. Editing one sentence re-synthesizes only that sentence.

### 10.3 Subtitles

- Lines are at most 14 Chinese characters wide. One line is preferred, two at most, balanced so there are no orphans.
- Subtitles are cut at clause punctuation. Long clauses are cut at word boundaries, taken from the TTS tokens or, failing that, from `jieba`.
- Punctuation is hidden (benchmark style), except `·` in transliterated names and apostrophes inside English words.
- The baseline is fixed, so subtitles do not move up or down between cues.
- Style: heavy white text with a black outline, placed by the safe-area rules in §10.6.

### 10.4 Motion rules

- Zoom and pan use sub-pixel affine transforms with bicubic resampling, never crop boxes rounded to whole pixels. Rounded boxes make slow zooms jitter.
- Push-in: 2–4% per poster. Focus transitions: about 0.4 s, eased.
- The tone stays "research explainer", not aggressive motion graphics.

### 10.5 Audio

- Loudness: −12 LUFS integrated (±1) with a true-peak ceiling of −1 dBTP. Speech peaks sit 15–20 dB above its loudness, so gain alone cannot reach this; `loudnorm` stalls near −15 LUFS. The chain is gentle compression (−24 dB, 4:1), measured gain, and a 4×-oversampled peak limiter at −1.5 dBFS, with the gain re-measured once after limiting. Measured on the first real render: −12.3 LUFS, −1.4 dBTP.
- Background music is off by default. Add it in the Douyin app from its licensed library. If music is baked into the render, keep the license records.

### 10.6 Safe areas (defaults; verify on a device)

- **3:4:** subtitles centered at about 86% of frame height.
- **9:16:** the 3:4 content block is centered. Subtitles sit at about 77% of frame height and stay left of the platform's right-hand action rail.
- Verify each ratio by uploading a private test video with a grid overlay and taking screenshots on a phone. The defaults above are starting points, not measurements.

---

## 11. Reliability (Phase 1)

- **Stage stamps.** Each stage stores a hash of its inputs, and a stage whose inputs have not changed is skipped. This gives resume-from-failure and idempotency without a workflow engine.
- **Content-hash caches for paid calls.** Repeating a command, or re-rendering, never repeats a paid call.
- **Storyboard anchor.** `pvm check` stores a hash of the sentence list in the storyboard. If the script changes afterwards, checks and renders stop until the scene and claim ranges have been re-checked (`pvm check --reanchor`). Without this, splitting one sentence and merging two others would silently shift every later scene.
- **Safe writes.** Every file is written to a temporary file and then swapped in. The swap is retried when Windows reports the file as locked, and a lock guards updates to `project.json`.
- **Retry budget.** Failure states are recorded in `project.json`, never retried without limit.
- **Versions.** The manifest records the script hash, storyboard hash, style-pack version, template version, model versions and prompt versions.
- **When to add services.** Add a queue or a database only when several videos render concurrently or several operators share the system.

---

## 12. Cost and Quota Model

Cost is driven by poster count, not by video length:

```text
image_AFP = posters × attempts_per_poster × AFP_per_image
```

| Mode | Assumption | Images | AFP at 99 per image |
|---|---|---:|---:|
| Economy | 4 posters × 1.0 attempt | 4 | ~396 |
| Standard | 5 posters × 1.5 attempts | ~7.5 | ~743 |
| Quality | 5 posters × 2 candidates, plus the summary card | ~12 | ~1,188 |
| Per-panel | 15 panels × 1.3 attempts | ~20 | ~1,930 |

A one-time cost to plan for: the mascot pose library, about 30 poses × 1.5 attempts ≈ 45 images ≈ 4,455 AFP. Schedule it at the start of a quota cycle.

Monthly capacity at Standard:

| Plan tier | Monthly AFP | Daily cap | Videos per month (Standard) |
|---|---:|---:|---:|
| small | 20,000 | 10,000 | ~26 |
| medium | 100,000 | 50,000 | ~134 |
| large | 250,000 | 125,000 | ~336 |
| max | 500,000 | 250,000 | ~672 |

- TTS on Agent Plan may also consume AFP. Measure it; edge-tts drafts cost nothing.
- The figure of 99 AFP per image and the plan quotas come from the v1.0 planning figures and `pvm/config.py`. They are configuration values, not contractual pricing. Revalidate them in the production account.

The per-video manifest records estimated AFP, actual AFP, image calls, retries, cache hits and the failed stage. The operator chooses between quota-saving and quality modes.

---

## 13. Quality Control and Compliance

### 13.1 Quality gates

| Gate | Automated check | Manual check |
|---|---|---|
| Claims | Coverage, excerpts found, research-language lint, hook claim | Checkpoints 1 and 2 |
| Script | Absolutist and pseudoscientific wording lint (later) | Tone; the hook matches the body |
| Visual | OCR label match; no digits or Latin letters in model images | Character consistency; the image matches the panel |
| Layout | Subtitles, hook and chips inside safe areas (by construction) | Device test (§10.6) |
| Output | Duration, black frames, nothing frozen for more than 5 s, loudness, streams | One full viewing |

### 13.2 AI-content labeling (China)

- The *Measures for Labeling AI-Generated Synthetic Content* (CAC and others, in force since September 1, 2025) and the mandatory national standard GB 45438-2025 require explicit and implicit labels on AI-generated content. This project's images and voice are AI-generated.
- **Explicit label:** a visible label in the video (default "含AI生成内容", configurable), plus Douyin's AI-content declaration at upload.
- **Implicit label:** the pipeline writes an AIGC metadata record into the MP4. Pillow compositing and FFmpeg re-encoding drop any metadata label carried by the provider's images, so the pipeline must write its own.
- Never remove or obscure labels added by a provider. If the provider's visible watermark is turned off, the video's own label must cover that obligation.
- Verify the exact label wording, placement and metadata fields against the current official texts (§13.8).

### 13.3 Paper and screenshot rights

See §6.6. The fact that a PDF can be downloaded does not mean its pages can be redistributed in branded social content.

### 13.4 Fonts

- Render only with openly licensed fonts: Noto Sans CJK SC and Source Serif 4, both under the SIL Open Font License. `pvm fonts` downloads them.
- If they are missing, rendering fails rather than silently falling back to system fonts. Setting `PVM_ALLOW_SYSTEM_FONTS=1` overrides this, at the operator's own risk.
- Microsoft YaHei and SimHei ship with Windows, but their commercial rights sit with their foundries; YaHei was designed by Founder (方正). Do not use them in published videos without a license.

### 13.5 Character and IP

Use an original mascot (§9.1). Do not echo recognizable characters or other creators' personas.

### 13.6 Platform homogeneity risk

Douyin has repeatedly announced actions against low-quality, mass-produced AI content. A "factory" that emits near-identical videos is exactly the pattern those rules describe. Every video must carry real evidence and its own claims, and structure and assets must vary. The evidence layer and the original mascot are distribution requirements, not just brand polish.

### 13.7 Traceability manifest

Every final video has a `manifest.json` that records:

- source ids, DOIs, licenses and display policies
- the script hash, storyboard hash and claim statistics
- voice engine, voice and speed
- model versions, prompt hashes, attempts and OCR results for each image
- style-pack and template versions
- labels applied (visible and metadata)
- QA results
- AFP estimated and used

The manifest supports review, rollback, reproduction and takedown if a source later becomes problematic.

### 13.8 To verify with official sources

- The exact AI-label requirements (wording, placement, metadata format) in the Measures and GB 45438-2025.
- Douyin's current rules for AI-generated content and for declarations.
- Font licenses for any font added beyond the OFL defaults.
- Rights to show closed-access paper pages, if the operator wants more than the title region.
- Agent Plan quotas, per-image AFP, TTS billing and the terms for the chosen voices.

---

## 14. Data Structures

### 14.1 Source

See §6.1. Sources are stored in `project.json` under `sources`, keyed by id (`src1`, `src2`, …). `src1` is the primary paper shown in the opening.

### 14.2 Storyboard v2

The example below uses a 12-sentence script about Kruger & Dunning (1999). Sentence numbers refer to `pvm sentences` output.

```json
{
  "version": 2,
  "title": "为什么越不懂的人越高估自己",
  "hook": ["越不懂", "越高估自己"],
  "hook_until": 3,
  "hook_claim": {
    "type": "source_fact",
    "evidence": [{"source": "src1", "excerpt": "grossly overestimated their test performance and ability"}]
  },
  "claims": [
    {"sentences": [1, 1], "type": "interpretation"},
    {"sentences": [2, 2], "type": "source_fact",
     "evidence": [{"source": "src1", "excerpt": "How Difficulties in Recognizing One's Own Incompetence Lead to Inflated Self-Assessments"}]},
    {"sentences": [3, 3], "type": "source_fact",
     "evidence": [{"source": "src1", "excerpt": "grossly overestimated their test performance and ability"}]},
    {"sentences": [4, 4], "type": "interpretation"},
    {"sentences": [5, 6], "type": "source_fact",
     "evidence": [{"source": "src1", "excerpt": "robs them of the metacognitive ability to realize it"}]},
    {"sentences": [7, 8], "type": "interpretation"},
    {"sentences": [9, 11], "type": "advice"},
    {"sentences": [12, 12], "type": "interpretation"}
  ],
  "scenes": [
    {"id": "open", "type": "paper", "sentences": [1, 3], "paper": "src1", "source": "auto",
     "highlights": [{"text": "grossly overestimated their test performance and ability", "at": 3}]},
    {"id": "p1", "type": "poster", "sentences": [4, 8], "title": "错而不自知",
     "sections": [
       {"heading": "不懂不自知", "at": 4, "labels": ["不会做", "看不出"],
        "visual": "mascot confidently holds a wrong answer sheet while a tiny question mark floats behind him"},
       {"heading": "缺的是尺子", "at": 6, "labels": ["尺子"],
        "visual": "mascot measures a tall stack of books with a ruler that is missing its markings"},
       {"heading": "越争越累", "at": 7, "labels": ["争论", "疲惫"],
        "visual": "two mascots argue across a table, one slumped and tired, papers scattered"}
     ]},
    {"id": "p2", "type": "poster", "sentences": [9, 10], "title": "先问怎么知道",
     "sections": [
       {"heading": "特别确定时", "at": 9, "labels": ["我确定"],
        "visual": "mascot pauses mid-stride and looks at a magnifying glass in his hand"},
       {"heading": "找人挑毛病", "at": 10, "labels": ["请指正"],
        "visual": "mascot hands his notebook to a friendly colleague who points at a page"}
     ]},
    {"id": "end", "type": "summary", "sentences": [11, 12],
     "sections": [
       {"heading": "研究发现", "labels": [], "visual": "mascot beside a test paper with a big gap between two bars"},
       {"heading": "原因", "labels": ["尺子"], "visual": "mascot holding a blank ruler"},
       {"heading": "对策", "labels": ["请指正"], "visual": "mascot shaking hands with a colleague"}
     ]}
  ],
  "voice": {"engine": "edge"}
}
```

`pvm check` adds `"sentences_hash"` after it validates the storyboard (§11).

### 14.3 Scene types

| Type | Fields (besides `id`, `sentences`, `transition`) | Notes |
|---|---|---|
| `paper` | `paper`, `source` (`auto`/`pdf`/`card`), `page`, `highlights[{text, at}]`, `highlight_title`, `zoom`, `rights` | `auto` applies §6.6 |
| `paper_scroll` | `paper`, `pages`, `speed`, `rights` | Open-licensed papers only, unless `rights: "permitted"` |
| `poster` | `title`, `sections[{heading, visual, labels, at}]`, `focus`, `extra`, `image` | 2–4 sections; 3 is the house style |
| `summary` | `title`, `label`, `sections`, `focus`, `extra`, `image` | Citation block drawn by code |
| `image` | `title`, `visual`, `extra`, `image` | One full illustration |
| `text` | `lines` | Emphasis card |

`image` fields let the operator supply a finished image instead of generating one. Labels are at most 7 characters, at most 4 per section, with no digits or Latin letters.

### 14.4 Render manifest

```json
{
  "project": "dunning-kruger",
  "rendered_at": "2026-09-26T15:00:00+08:00",
  "canvas": {"ratio": "3:4", "width": 1080, "height": 1440, "fps": 30},
  "duration": 128.4,
  "inputs": {"script_hash": "…", "storyboard_hash": "…", "style_pack": "paper-cut@1",
             "voice": {"engine": "edge", "voice": "zh-CN-YunxiNeural", "rate": "+10%"}},
  "sources": [{"id": "src1", "doi": "10.1037/0022-3514.77.6.1121", "license": null, "display": "title_crop"}],
  "scenes": [{"id": "open", "type": "paper", "start": 0.0, "end": 14.2}],
  "visuals": [{"scene": "p1", "file": "visuals/p1.png", "provider": "ark", "model": "doubao-seedream-5.0-lite",
               "prompt_hash": "…", "attempts": 2, "ocr": "pass", "afp": 198}],
  "claims": {"sentences": 12, "source_fact": 5, "verified": 5},
  "labels": {"visible": "含AI生成内容", "metadata": true},
  "qa": {"loudness_lufs": -12.1, "true_peak_dbtp": -1.2, "max_frozen_s": 3.1, "black_frames": 0}
}
```

---

## 15. Prompt Frameworks

### 15.1 Storyboard planning (LLM)

```text
SYSTEM:
You are the structured planner for an evidence-led short-video system. Return valid JSON only (storyboard v2).
Every sentence belongs to exactly one claim: source_fact, interpretation or advice.
Every source_fact quotes the source verbatim in evidence[].excerpt; excerpts are checked mechanically.
The hook is a claim: give hook_claim with evidence (source_fact) or a basis (interpretation/advice).
Never invent a paper, DOI, sample size, effect size or quote. Never turn correlation into causation.
Poster labels: at most 7 characters, at most 4 per section, no digits or Latin letters.

USER:
- numbered sentences
- sources with title, abstract and available text
- target duration and mode (retention / research)
- style pack notes
```

### 15.2 Poster image (compiled by code)

```text
STYLE: paper-cut collage explainer illustration, warm ivory paper, torn-paper textures, soft drop shadows,
clean ink outlines, restrained navy / ochre palette, the original mascot (see references), generous empty space.

LAYOUT: three stacked horizontal panels separated by clear empty gutters; the top-left corner of each panel
stays empty. Aspect ratio of the panel area.

PANEL 1: <section 1 visual>. Paper tags reading: <labels>.
PANEL 2: <section 2 visual>. Paper tags reading: <labels>.
PANEL 3: <section 3 visual>. Paper tags reading: <labels>.

TEXT RULE: the only readable text allowed is the listed tag words, in Chinese.
No other letters, no digits, no titles, no numbers, no logos, no watermarks, no UI.
```

### 15.3 Claim review (LLM)

```text
For each claim: given the sentence, its type and its excerpts, answer JSON
{"supported": true|false, "issues": ["causation" | "population" | "magnitude" | "certainty" | "other"], "fix": "<rewrite>"}.
For the hook: judge whether a viewer seeing the hook over the paper would believe the paper says it.
```

---

## 16. Roadmap

### 16.1 Phases

| Phase | Scope | Outcome |
|---|---|---|
| Phase 1: reliable single video | Milestones M1–M5 below | One verified video a day, reliably |
| Phase 2: evidence automation | Research planner, automatic source cards, LLM claim review in the loop | A trust and research moat |
| Phase 3: consistency and scale | Mascot pose library, template variety, quota-aware scheduling, hook A/B variants | A production line, not a single-video tool |
| Phase 4: operations | Analytics loop (completion rate, 5-second retention, saves, shares) joined with manifests; publish checklist automation | Decisions driven by performance, not volume |

### 16.2 Phase-1 milestones

| Milestone | Scope |
|---|---|
| M1 Foundation | CLI; storyboard v2 with claims and excerpt verification; anchor guard; research open-access and license fixes; font policy; subtitle fixes; quota pacing; tests |
| M2 Voice and timeline | TTS (edge-tts, Ark), per-sentence cache, word timestamps, timeline, SRT |
| M3 Renderer and animatic | Compositor for every scene type, hook, subtitles, source chip, AI label; FFmpeg encode with loudness normalization and AIGC metadata; animatic; QA |
| M4 Images | Ark adapter, prompt compiler, cache, ledger, OCR gate, panel cutting |
| M5 Planner | DeepSeek storyboard drafts and claim review |

### 16.3 MVP boundary

The first version only needs to do this reliably:

> **script + source → storyboard v2 with claims → check → animatic → 4–5 OCR-verified posters → final render with labels → QA → publish checklist, regenerating only failed posters**

Automatic paper discovery, topic ideation, large batches and automatic publishing come after this chain is stable.

---

## 17. Acceptance Criteria (measurable)

### Technical

- Re-rendering an accepted project reproduces the same frames, with an unchanged manifest hash.
- A failed stage resumes without redoing completed stages.
- Repeating a command never repeats a paid call.
- Provider-specific code stays inside adapters.

### Research

- 100% of sentences are covered by exactly one claim.
- 100% of `source_fact` claims have at least one excerpt found in the source text (final render, `--strict`).
- The hook has a claim, and `interpretation`/`advice` hooks state a basis.
- Every research-language lint warning is resolved or deliberately accepted at checkpoint 2. The lint is a heuristic, so it stays a warning.

### Visual

- Facts, titles, headings, hook and subtitles are drawn by code: OCR finds no digits or Latin letters in model images.
- OCR finds 100% of the requested labels on accepted images.
- The mascot comes from the pose library or its references, and passes visual review.

### Timing and motion

- Retention mode: the first poster appears by 12 s. Research mode: by 25 s.
- No region above the subtitle band is frozen for more than 5 s (freezedetect, `n=0.001`).

### Audio

- −12 ± 1 LUFS integrated; true peak at or below −1 dBTP.

### Compliance

- A visible AI label and an AIGC metadata record are present.
- Only licensed fonts are used.
- Paper display follows §6.6.

### Operations

- Every manifest records estimated and actual AFP, image calls, retries, cache hits, the failed stage (if any) and accepted/rejected assets.

---

## 18. References and Revalidation

- Benchmark analysis: the seven files in the user's benchmark folder, measured with ffmpeg 7.1 filters (§2.5); licenses from the OpenAlex API (September 2026).
- Volcano Ark Agent Plan documentation: short-video guidance, AFP usage APIs, over-quota rules, Seedream capabilities including reference images.
- DeepSeek API documentation: JSON output, function calling.
- *Measures for Labeling AI-Generated Synthetic Content* (in force since September 1, 2025) and GB 45438-2025.
- OpenAlex open-access and license fields; Unpaywall.
- Douyin creator rules for AI-generated content (check the current version).

Plan capabilities, quotas, prices and platform rules change. Keep them in configuration and deployment notes, and revalidate them in the production account before launch.

---

## 19. Final Recommendation

The strongest first product is not an autonomous content bot. It is a stable, semi-automatic production line with three checkpoints, typed and verified claims, reusable assets, deterministic rendering and recoverable failures.

If the system can repeatedly turn a verified source and a script into a video built from 4–5 OCR-verified collage posters, with an original mascot, a visible evidence trail and correct labels, and can regenerate only what failed, it already has the foundation of an evidence-led content engine that the platform will not treat as mass-produced filler.
