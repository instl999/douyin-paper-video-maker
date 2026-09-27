# Evidence-Led AI Short-Video Factory

## Product & Technical Specification

**Volcano Ark Agent Plan / Seedream + DeepSeek API + Deterministic Video Rendering**  
**Based on the analysis of seven benchmark short videos supplied by the user**  
**Version 1.0 — September 24, 2026**

---

## 1. Executive Summary

The concept is viable and productizable. The most important design decision is to avoid treating the system as a "live image generator while the video is playing." A production-grade system should instead use a **precomputed, time-coded pipeline**:

> research source → structure script → split into semantic beats → pre-generate visuals → run quality checks → synthesize voice → align timing → render with deterministic templates → export → QC

This changes the project from a fragile AI demo into a repeatable content production system.

The recommended positioning is:

> **Evidence-Led AI Explainer Video Factory**

rather than a generic "AI auto-editing" product.

The proposed core stack is still strong:

- **DeepSeek API** as the reasoning, planning, scripting, storyboard, prompt-compilation, and QA layer.
- **Volcano Ark Agent Plan + Seedream** as the primary visual-generation layer.
- **TTS + alignment** as the voice and timing layer.
- **Remotion / React / SVG / HTML / CSS** as the deterministic visual-composition layer.
- **FFmpeg** as the final encoding, audio normalization, validation, and packaging layer.

Five principles should guide the implementation:

1. **Do not generate images during playback.** Generate and validate them before rendering.
2. **Do not ask the image model to generate readable Chinese or English text.** Generate text-free visuals, then render headlines, labels, numbering, citations, and subtitles programmatically.
3. **Treat papers as traceable evidence objects, not decorative screenshots.** Every research claim should map to a source ID.
4. **Build an original recurring mascot / researcher character.** Do not rely on a character that resembles an existing anime or entertainment IP.
5. **Treat AFP quota and provider limits as first-class scheduling constraints.** Production reliability depends on quota awareness, caching, retries, and fallback routing.

---

## 2. Benchmark Video Findings

Seven benchmark videos were reviewed through frame extraction and structural analysis. Duration and aspect-ratio data come from the files themselves. Estimated paper-opening durations are approximate rather than frame-by-frame annotations.

### 2.1 Benchmark Overview

| Sample | Duration | Resolution | Ratio | Visual Structure | Category |
|---|---:|---:|---:|---|---|
| Sample 1 | 127.2 s | 1080×1440 | 3:4 | Paper page remains dominant; summary visual appears later | Evidence-wall style |
| Sample 2 | 135.6 s | 1920×2560 | 3:4 | ~20 s paper opening, then infographic cards | Hybrid explainer |
| Sample 3 | 115.0 s | 1080×1440 | 3:4 | ~20–25 s paper opening, then explainer visuals | Hybrid explainer |
| Sample 4 | 157.6 s | 1080×1440 | 3:4 | ~15–25 s paper opening, then explainer visuals | Hybrid explainer |
| Sample 5 | 132.0 s | 1080×1440 | 3:4 | Paper remains on screen for a long section; subtitles carry the explanation | Evidence-wall style |
| Sample 6 | 143.6 s | 1080×1440 | 3:4 | ~20 s paper opening, then explainer cards | Hybrid explainer |
| Sample 7 | 114.1 s | 1080×1440 | 3:4 | ~15–20 s paper opening, then explainer cards | Hybrid explainer |

Average duration is approximately **132 seconds**, and all seven benchmark videos use a **3:4 vertical canvas**.

### 2.2 Repeated Visual Language

The benchmark videos share a very consistent grammar:

- **Opening evidence cue:** a journal article or paper page fills the screen and immediately signals that the content is "research-based."
- **Hook typography:** large, high-saturation yellow text with a thick black outline is placed over the paper page.
- **Subtitles:** white subtitles with a dark outline remain close to the bottom safe area and carry most of the information density.
- **Explainer section:** warm off-white / paper-like backgrounds, a recurring mascot, numbered sections, arrows, icons, and metaphorical objects.
- **Visual cadence:** a single visual often supports an entire semantic paragraph for roughly **8–15 seconds** instead of changing every sentence.
- **Animation style:** motion is relatively light. Cuts, small zooms, text progression, highlights, and simple element entrances carry the rhythm.

### 2.3 What Should Be Improved

| Existing Pattern | Risk | Recommended Improvement |
|---|---|---|
| Paper screenshot used mainly as decoration | The viewer sees "a paper" but cannot tell which claim comes from it | Show author/year/source, highlight the title or relevant section, and maintain claim-to-source mapping |
| Long static periods | Visual fatigue and weaker retention | Add 1–2 lightweight motion layers per beat: slow push-in, highlight, element entrance, or number progression |
| AI-generated text inside images | Misspellings, typography drift, poor batch editability | Generate text-free visuals; render all text programmatically |
| Mascot style resembles familiar entertainment/anime language | IP and brand risk | Build an original recurring researcher/mascot with a controlled reference pack |
| Image generation per sentence | High quota usage, many retries, visual drift | Generate by semantic beat; one image can support 8–15 seconds of narration |
| Research claims and editorial interpretation are mixed | Risk of overstating research | Label content as `source_fact`, `interpretation`, or `advice` in the data model |

---

## 3. Recommended Creative Format

The best evolution of the benchmark style is:

> **Paper evidence + visual explanation + original recurring IP**

This keeps the recognizable "evidence" feeling while avoiding long stretches of static paper screenshots.

### 3.1 Recommended 120–150 Second Structure

| Time | Narrative Function | Goal | Visual Treatment |
|---|---|---|---|
| 0–1.5 s | Evidence first | Establish credibility before explanation | Full-screen real source page or source card |
| 1.5–4 s | Hook | Present tension, contradiction, or counterintuitive idea | Large outlined headline; ideally ≤ 8–12 Chinese characters for Chinese output |
| 4–8 s | Source highlight + one-line finding | Make the evidence readable | Author / year / journal / DOI or source identifier |
| 8–18 s | Research-to-story bridge | Translate the source into the content topic | Slow zoom + highlight box |
| 18–105 s | 6–8 semantic beats | Mechanism, examples, counterexamples, advice | Template-based AI illustrations |
| 105–125 s | Boundary / counterpoint | Prevent overgeneralization | Contrast or exception card |
| 125–140 s | Synthesis | Compress the story into 3 key points | Three-part summary card |
| 140–150 s | Source + soft CTA | Build trust and series value | Citation/end card |

If retention is the priority, compress the paper section to roughly **8–12 seconds**. If the account is explicitly positioned as a "paper-reading" or "research explainer" channel, the evidence section can remain **15–25 seconds**, but it should include dynamic highlighting, author/year overlays, and localized zooms rather than remaining fully static.

### 3.2 Semantic Beats, Not Sentence-by-Sentence Images

A 130-second video with a new image every three seconds could require 40+ visuals. That creates unnecessary quota usage, more failures, more visual inconsistency, and more review work.

A better approach is usually **7–10 main visuals**.

A semantic beat normally contains:

- one core conclusion,
- two or three supporting points,
- one main visual metaphor,
- one stable background/composition,
- programmatic internal motion.

Within a beat, the renderer can create movement without requesting a new image:

- reveal a headline,
- highlight one numbered item at a time,
- zoom into an area,
- animate arrows,
- emphasize keywords,
- fade in supporting objects.

Only generate a new AI image when the **narrative logic changes**, not when the next sentence starts.

---

## 4. Product Form and User Workflow

The product should be a **controlled semi-automatic factory**, not a black-box one-click generator.

### 4.1 Recommended Workflow

#### Input

The user provides some or all of:

- topic,
- finished script,
- target duration,
- target platform,
- language,
- visual style pack,
- research mode on/off,
- source or paper if already known.

#### Research Workspace

The system displays candidate sources and the exact claims they support. The operator can:

- lock a source,
- replace a source,
- reject a weak claim,
- inspect metadata,
- decide whether to use a real page screenshot or a generated citation card.

#### Script Workspace

DeepSeek produces structured narration and labels each statement as:

- `source_fact`
- `interpretation`
- `advice`

This distinction should remain visible in the editor.

#### Storyboard Workspace

Each semantic beat becomes one card containing:

- narration,
- target duration,
- purpose,
- source IDs,
- visual template,
- visual brief,
- image-generation prompt,
- character / style references,
- overlay text.

#### Asset Workspace

The operator can regenerate only the failed scene instead of the entire video. Independent locks should be available for:

- character,
- background,
- visual template,
- composition,
- reference images,
- accepted AI asset.

#### Render Workspace

Outputs should include:

- MP4,
- cover image,
- SRT subtitles,
- source/citation card,
- optional production manifest.

Support at least:

- **3:4** for benchmark-style output,
- **9:16** for mainstream short-video platforms.

#### Batch Workspace

Allow CSV / spreadsheet import of multiple topics. Jobs enter a queue and are scheduled according to:

- AFP availability,
- provider concurrency,
- job priority,
- cached assets,
- retry budget.

### 4.2 Two Production Modes

| Mode | Workflow | Best For |
|---|---|---|
| Fast Mode | User provides script; system handles storyboard, visuals, voice, timing, and render | Highest reliability and high-frequency publishing |
| Research Mode | System first searches/validates research, then generates the script and evidence mapping | Stronger differentiation and research-led channels |

---

## 5. System Architecture

The most important architectural boundary is:

> **LLMs and image models should output structured decisions and visual assets. Final typography, dimensions, timing, transitions, subtitles, and source displays must be controlled by deterministic code.**

### 5.1 Recommended Stack

| Layer | Suggested Technology | Responsibility |
|---|---|---|
| Frontend / Operations Console | Next.js / React | Storyboard editing, asset locking, batch jobs, quota dashboard |
| Business API | Node.js + TypeScript | Unified data model, schemas, provider adapters, render integration |
| Queue | BullMQ + Redis for MVP; Temporal at scale | Retry, timeout, idempotency, workflow state |
| Database | PostgreSQL | Projects, sources, beats, prompt versions, task states, metrics |
| Object Storage | TOS or S3-compatible storage | Paper pages, AI images, audio, subtitles, final video |
| LLM | DeepSeek API | Research planning, script, beat planning, prompt compilation, QA |
| Image Generation | Volcano Ark Agent Plan + Seedream | Text-free scenes, characters, backgrounds, props |
| Voice | Seed TTS or another stable TTS provider | Narration audio |
| Alignment | ASR / forced alignment | Sentence- or word-level timestamps |
| Video Composition | Remotion + React | Layout, animation, reusable templates |
| Final Encoding | FFmpeg | Encoding, audio normalization, validation, packaging |
| Monitoring | OpenTelemetry / Sentry + custom metrics | Error rates, retries, AFP consumption, cost, latency |

### 5.2 High-Level Pipeline

```text
Topic / Script
      |
      v
Research Planner -----------------------------+
      |                                       |
      v                                       |
Source Retrieval / Validation                 |
      |                                       |
      v                                       |
Evidence Objects                              |
      |                                       |
      v                                       |
Script Writer                                 |
      |                                       |
      v                                       |
Beat Splitter                                 |
      |                                       |
      +-----------> Prompt Compiler ----------+
      |                         |
      |                         v
      |                Ark / Seedream
      |                         |
      |                         v
      |                  Visual Assets
      |                         |
      v                         |
TTS ---------------------> Voice Audio         |
      |                         |              |
      v                         v              |
Alignment ----------------> Timeline <---------+
                                |
                                v
                     Remotion / SVG / HTML
                                |
                                v
                              FFmpeg
                                |
                                v
                          QC + Final Output
```

---

## 6. Paper / Journal Source Pipeline

### 6.1 Papers Are Evidence Objects, Not Background Assets

The research layer should prioritize metadata sources that can be traced and verified, such as:

- OpenAlex,
- Crossref,
- PubMed for biomedical topics,
- open-access repositories,
- user-authorized source files.

For every important claim, store at least:

```text
title
authors
year
venue
DOI or source URL
page or section when available
supporting_excerpt
claim_type
confidence
```

The opening should preferably show one of the following:

- an openly accessible title page,
- an abstract page,
- a permitted screenshot,
- a generated citation/source card.

If redistribution rights for a full PDF page are unclear, do not make the full page a permanent branded asset. A citation card generated from metadata is safer and often visually cleaner.

### 6.2 Recommended Research Flow

1. Generate 3–5 search queries from the topic.
2. Retrieve 10–20 candidate sources.
3. Filter by relevance, study type, year, sample characteristics, and accessibility.
4. Use DeepSeek to extract only claims actually supported by the source.
5. Run a second verification step to check whether the wording overreaches the original source.
6. Generate the opening source card / screenshot composition.
7. Attach `source_id` values to every relevant semantic beat.

### 6.3 Claim Safety Rule

The renderer should never present an unsupported statement as "the paper proves..." simply because a paper screenshot exists.

A production rule can be:

```text
if claim_type == "source_fact" and source_ids.length == 0:
    block_render_or_rewrite()
```

When evidence is insufficient, the script should instead use language such as:

- "One possible interpretation is..."
- "This can be understood as..."
- "A practical way to think about it is..."

For psychology, medicine, health, finance, and other sensitive topics, apply stricter evidence rules and avoid presenting correlation as causation.

---

## 7. DeepSeek API Responsibilities

DeepSeek should not be used only as a generic "write me a script" endpoint. It is more valuable as the **structured orchestration layer** for the entire pipeline.

### 7.1 Recommended Roles

| Role | Output |
|---|---|
| Research Planner | Converts a topic into academic search queries and claims to verify |
| Evidence Extractor | Extracts what the source actually supports |
| Script Writer | Produces Hook → Evidence → Mechanism → Example → Boundary → Takeaway narration |
| Beat Splitter | Splits narration into 6–10 semantic beats and estimates timing |
| Prompt Compiler | Converts each beat into a Seedream-compatible visual brief |
| QC Reviewer | Checks logic, exaggeration, visual relevance, and source consistency |
| Repair Agent | Repairs only the failed node instead of regenerating everything |

### 7.2 Enforce Structured Output

Example:

```json
{
  "video_id": "vid_20260924_001",
  "source": {
    "title": "...",
    "year": 2025,
    "doi": "...",
    "claim": "...",
    "claim_type": "source_fact"
  },
  "beats": [
    {
      "id": "b03",
      "purpose": "mechanism",
      "narration": "...",
      "visual_template": "three_step_explainer",
      "visual_brief": "...",
      "source_ids": ["src_01"],
      "estimated_seconds": 11.5
    }
  ]
}
```

Production rules:

- Validate every result with JSON Schema, Pydantic, Zod, or equivalent.
- Retry only the failed step when required fields are missing.
- Treat empty or invalid model output as an explicit recoverable failure state.
- Prefer multiple smaller calls over one very large request that attempts research, writing, storyboarding, prompts, and QC in a single response.
- Save `prompt_version`, `model`, `temperature`, and `input_hash` for reproducibility.

---

## 8. Volcano Ark Agent Plan / Seedream Integration

The visual layer should be implemented behind a provider adapter so the business logic does not depend on one transport method or one specific plan configuration.

### 8.1 Provider Adapter Pattern

```ts
interface ImageProvider {
  generate(input: SceneImageRequest): Promise<GeneratedAsset[]>;
  getQuota?(): Promise<QuotaSnapshot>;
}

class ArkAgentPlanProvider implements ImageProvider { /* ... */ }
class ArkPayAsYouGoProvider implements ImageProvider { /* ... */ }
class FallbackProvider implements ImageProvider { /* ... */ }
```

The business layer should only know that it needs an image matching a `SceneImageRequest`. It should not care whether the provider is:

- Agent Plan,
- standard Volcano Ark image API,
- another preconfigured fallback route.

### 8.2 What Seedream Should Generate

Seedream should generate:

- original character scenes,
- backgrounds,
- props,
- metaphorical objects,
- paper-like editorial illustrations,
- composition-ready image assets.

Seedream should **not** be responsible for:

- final headlines,
- Chinese characters,
- English labels,
- numbering,
- citations,
- subtitles,
- precise UI-like typography.

All visible text should be rendered deterministically.

### 8.3 Quota-Aware Routing

The scheduler should periodically retrieve available AFP / usage information and apply configurable thresholds.

Example policy:

- **>30% remaining:** normal operation.
- **10–30% remaining:** reduce double-candidate generation and nonessential variants.
- **<10% remaining:** process only approved/high-priority jobs; defer experiments and nonurgent batches.

The exact thresholds are business settings, not fixed product truths.

When the primary route cannot continue, the system can:

- defer the job,
- reduce the number of visual candidates,
- reuse cached accepted assets,
- switch to a separately configured fallback provider.

Do not assume the primary plan will continue seamlessly after quota exhaustion.

### 8.4 Cache by Content Hash

A visual request can be cached using a hash of:

```text
image_prompt
reference_asset_ids
model_version
style_pack_version
aspect_ratio
other generation parameters
```

If the hash already maps to an accepted asset, rerendering a video should reuse it instead of consuming quota again.

### 8.5 Retry Budget

Recommended rule:

- maximum 2–3 automatic retries per scene,
- after the retry budget is exhausted, move the scene to manual review,
- never run unlimited generation loops.

---

## 9. Visual Consistency and Templating

### 9.1 Build an Original Researcher / Mascot IP

Instead of reproducing the visual identity of an existing recognizable character, create an original recurring character.

A practical reference pack should include 8–12 images such as:

- front view,
- side view,
- half-body,
- seated pose,
- holding a book,
- thinking,
- surprised,
- rejecting / disagreeing,
- pointing,
- summarizing.

Lock recurring traits:

- hairstyle,
- glasses or accessories,
- clothing,
- skin tone,
- line thickness,
- color palette,
- shadow style,
- paper/background tone.

When supported by the image-generation configuration, use multiple reference images to stabilize the original mascot and art direction.

### 9.2 Do Not Put Text Instructions Into the Image Itself

The image prompt should describe layout intent, for example:

- reserve the top 18% for a programmatic headline,
- keep the character on the right side,
- leave three numbered regions on the left,
- reserve the bottom safe area for subtitles,
- no readable letters or characters.

### 9.3 Recommended Template Library

| Template | Structure | Use Case |
|---|---|---|
| T1 Paper Hook | Paper/source image + large hook + highlighted source metadata | Opening |
| T2 Three-Step | Three numbered explanation blocks | Mechanism / steps |
| T3 Contrast | Left vs right | Misconception vs better interpretation |
| T4 Timeline | Cause → process → result | Growth, decisions, behavioral mechanisms |
| T5 Spectrum | Low → high / A → B | Degree, trade-offs, boundaries |
| T6 Summary | Three-point recap + source | Ending |

The consistent "same-series" feeling should come primarily from **fixed templates + original recurring character + controlled typography**, not from asking the image model to improvise a full poster each time.

---

## 10. Voice, Subtitles, and Timeline

Recommended order:

1. finalize the script,
2. generate TTS,
3. align timestamps from the actual audio,
4. derive the final scene timeline,
5. render visuals according to semantic boundaries.

Do not assign fixed scene duration before knowing the real voice timing unless it is only a rough planning estimate.

### 10.1 Subtitle Rules

For Chinese output, a useful starting point is:

- 1–2 lines,
- roughly 12–18 Chinese characters per line,
- strong safe-area constraints,
- high contrast and dark outline/shadow.

Use separate visual hierarchies for:

- **hook / flower text / headline:** short theme-level phrase,
- **subtitles:** complete semantic information.

Do not overload both layers at once.

### 10.2 Scene Timing

Scene changes should align with narrative meaning rather than a fixed "change every N seconds" rule.

Useful lightweight motion:

- 2–5% Ken Burns zoom,
- highlight box,
- animated arrow,
- number emphasis,
- sequential reveal,
- local crop / push-in.

The tone should remain closer to "research explainer" than to an aggressive motion-graphics ad.

---

## 11. Industrial Reliability: Queue, Quota, Cache, Retry

### 11.1 Workflow State Machine

Recommended state flow:

```text
CREATED
  -> RESEARCHED
  -> SCRIPTED
  -> BEATS_READY
  -> VISUALS_DRAFTED
  -> VOICE_READY
  -> ALIGNED
  -> RENDERED
  -> QC_PASS
  -> PUBLISHED

QC_FAIL
  -> REPAIR
  -> return only to the failed node
```

### 11.2 Reliability Rules

#### Idempotency

Every job should have an `idempotency_key`. Repeated clicks on "generate" must not create duplicate API spending.

#### Separate Queues

Maintain independent queues such as:

```text
deepseek_queue
image_queue
tts_queue
render_queue
```

Each queue can have its own:

- concurrency,
- timeout,
- retry policy,
- rate limit,
- health state.

A slowdown in one provider should not block the entire pipeline.

#### Resume From Failure

If image beat `b06` fails, do not rerun:

- research,
- accepted script,
- accepted images for b01–b05,
- TTS if unchanged.

Repair only the failed node and downstream outputs that depend on it.

#### Version Everything

Store references such as:

```text
script_v3
style_pack_v2
template_v5
model_version
prompt_version
```

inside the production manifest.

#### Reusable Assets

Reuse across videos where appropriate:

- original character reference images,
- paper texture,
- generic icons,
- source screenshots,
- recurring background props,
- approved template animations.

#### Priority

Example task priority:

1. continuation of an already-published series,
2. deadline-sensitive content,
3. normal scheduled content,
4. experimental topics.

---

## 12. Cost and AFP Model

The useful cost variable is not primarily final video duration. It is:

> **semantic beat count × candidate count × retry rate × cost per generated image**

A simple planning formula is:

```text
image_AFP = semantic_beats × average_candidates_per_beat × AFP_per_image
```

Using the planning example already referenced in the original specification for Seedream 5.0 Lite at **99 AFP per image**:

| Mode | Assumption | Image Calls | Example Image AFP |
|---|---|---:|---:|
| Economy | 7 beats × 1 image | 7 | ~693 AFP |
| Recommended | 8 beats × ~1.5 attempts | ~12 | ~1,188 AFP |
| High Quality | 10 beats × 2 candidates | 20 | ~1,980 AFP |

These numbers are **capacity-planning examples, not contractual pricing**, and should be configuration values rather than hard-coded constants.

The operator dashboard should show, per video:

- estimated image calls,
- estimated AFP,
- actual image calls,
- actual AFP when available,
- retry count,
- cache-hit rate,
- failed scene,
- reusable assets.

This allows operators to choose between:

- **quota-saving mode**, and
- **more-candidate / quality mode**.

---

## 13. Quality Control and Compliance

### 13.1 Five-Layer Quality Gate

| Layer | Checks |
|---|---|
| Factual QA | Was the paper overstated? Are sample size, numbers, causality, and findings accurate? |
| Script QA | Does the hook match the body? Does the script contain absolutist or pseudoscientific language? |
| Visual QA | Is the character consistent? Does the image match the beat? Are there malformed objects or accidental text? |
| Layout QA | Do subtitles stay inside safe areas? Are headlines blocked? Is the source readable? |
| Output QA | Black frames, silence, A/V desync, encoding failure, abnormal duration |

### 13.2 Research Integrity

Maintain a strict distinction between:

- **research finding**,
- **editorial interpretation**,
- **actionable advice**.

The distinction should exist in the data structure, not only in editorial guidelines.

Every `source_fact` should have at least one `source_id`.

### 13.3 Paper and Screenshot Rights

When possible, use:

- open title pages,
- abstract pages,
- metadata-based source cards,
- screenshots the user is authorized to use.

Do not assume that the ability to access a PDF automatically means the entire page can be redistributed in branded social content.

### 13.4 Character / IP Strategy

Avoid reproducing identifiable copyrighted characters. The safest long-term brand asset is:

> original mascot + controlled style guide + reusable reference pack

### 13.5 Production Traceability

For every final video, save a manifest containing:

- source IDs,
- script version,
- model versions,
- generation timestamps,
- prompt versions,
- style pack version,
- template version,
- accepted visual asset IDs.

This improves review, rollback, reproducibility, and content removal if a source later becomes problematic.

---

## 14. Data Structures and Interface Contracts

### 14.1 Recommended Beat Schema

```ts
type Beat = {
  id: string;
  purpose:
    | "hook"
    | "evidence"
    | "mechanism"
    | "example"
    | "boundary"
    | "summary";
  narration: string;
  subtitle: string;
  estimated_seconds: number;
  source_ids: string[];
  claim_type: "source_fact" | "interpretation" | "advice";
  visual_template: string;
  visual_brief: string;
  image_prompt: string;
  reference_asset_ids: string[];
  overlay: {
    headline?: string;
    labels?: string[];
  };
};
```

### 14.2 Suggested Project Output Structure

```text
project/
  manifest.json

  sources/
    src_01.json
    src_01_first_page.png

  script/
    script_v3.json

  audio/
    voice.wav
    subtitles.srt

  visuals/
    b01.png
    b02.png
    ...
    b08.png

  render/
    final_3x4.mp4
    final_9x16.mp4
    cover.png
```

### 14.3 Suggested Render Manifest

```json
{
  "canvas": {
    "ratio": "3:4",
    "fps": 30
  },
  "voice": "audio/voice.wav",
  "subtitles": "audio/subtitles.srt",
  "scenes": [
    {
      "beat_id": "b01",
      "start": 0.0,
      "end": 8.4,
      "template": "paper_hook"
    },
    {
      "beat_id": "b02",
      "start": 8.4,
      "end": 19.7,
      "template": "three_step"
    }
  ],
  "source_card": {
    "source_ids": ["src_01"]
  },
  "versions": {
    "script": 3,
    "style_pack": 2,
    "template": 5
  }
}
```

---

## 15. Prompt Frameworks

### 15.1 DeepSeek Beat-Planning Prompt Skeleton

```text
SYSTEM:
You are the structured planner for an evidence-led short-video production system.
Return valid JSON only.
Separate source facts from interpretation and advice.
Never invent a paper, DOI, sample size, effect size, or quoted finding.

USER INPUT:
- topic
- target duration
- verified source objects
- tone/style pack

OUTPUT:
- hook
- evidence_summary
- beats[]
- each beat:
  - purpose
  - narration
  - claim_type
  - source_ids
  - visual_template
  - visual_brief
  - estimated_seconds
```

### 15.2 Seedream Visual Prompt Skeleton

```text
STYLE ANCHOR:
original editorial explainer illustration,
warm ivory paper background,
clean ink outlines,
restrained navy/ochre palette,
consistent original mascot,
flat hand-drawn objects,
strong negative space,
no readable text in image.

SCENE:
[visual metaphor + action + 2–3 props + composition]

Reserve the top 18% for programmatic headline.
Reserve the bottom 14% for subtitles.
No letters, Chinese characters, logos, watermarks, captions, or UI text.
```

---

## 16. MVP and Iteration Roadmap

Do **not** start with a fully autonomous pipeline that does research, script writing, image generation, voice, rendering, and publishing with no operator checkpoint.

First make the middle of the pipeline reliable.

### 16.1 Four-Phase Roadmap

| Phase | Scope | Outcome |
|---|---|---|
| Phase 1 — Stable MVP | User supplies script and source image; DeepSeek beat split; Seedream visuals; TTS; Remotion; per-scene regenerate | Prove reliable daily production |
| Phase 2 — Evidence Automation | Paper search, source/claim mapping, automatic source card | Create a trust and research moat |
| Phase 3 — Consistency & Batch | Original mascot pack, template library, batch queues, AFP dashboard, cache | Turn a single-video tool into a production factory |
| Phase 4 — QA & Operations | Automated visual QA, repair loops, opening A/B variants, asset reuse, publishing integrations | Improve throughput and consistency |

### 16.2 Recommended MVP Boundary

The first version only needs to do this reliably:

> **script + paper/source → DeepSeek storyboard → 7–10 text-free Seedream visuals → original character + fixed templates → TTS/subtitle alignment → one-click Remotion/FFmpeg render → regenerate only failed scenes**

After this chain is stable, add:

- automatic paper discovery,
- automatic topic ideation,
- large-scale batch production,
- automatic publishing.

This sequence has lower risk and is much closer to a genuinely scalable production system.

---

## 17. Acceptance Criteria

### Technical

- The same accepted project can be rerendered deterministically.
- A failed job resumes from the failed node.
- Repeated actions do not trigger duplicate paid/API generation.
- Provider-specific logic is isolated behind adapters.

### Research

- 100% of statements labeled `source_fact` contain at least one `source_id`.
- The wording of source-backed claims does not exceed what the evidence supports.

### Visual

- Visible text is never dependent on the image-generation model.
- All Chinese / English copy is drawn by the rendering layer.
- Character identity, clothing, palette, and line language remain visibly consistent.

### Timing

- The transition from evidence hook to first explanatory visual happens quickly, ideally within roughly 8–12 seconds for retention-focused output.
- Ordinary scenes do not remain completely static for long stretches.

### Operations

The dashboard can show at least:

- estimated AFP,
- actual AFP where available,
- image-generation count,
- retry count,
- failed node,
- cache reuse,
- accepted/rejected assets.

---

## 18. Reference Notes Used in the Original Specification

The original bilingual specification was prepared using official product documentation available as of **September 24, 2026**. The implementation team should revalidate all plan details, supported visual models, API endpoints, Base URLs, keys, quota rules, and pricing in the actual production account before launch.

The original research notes referenced:

- Volcano Ark Agent Plan short-video development guidance.
- Volcano Ark Agent Plan AFP usage APIs.
- Volcano Ark enterprise over-quota rules.
- Volcano Ark Seedream model capability lists, including text-to-image and reference-image workflows.
- DeepSeek API JSON Output documentation.
- DeepSeek API tool/function-calling documentation.

Plan capabilities and charging rules can change, so these should be maintained as configuration and deployment documentation rather than embedded as permanent assumptions in application logic.

---

## 19. Final Recommendation

The strongest first product is not a fully autonomous AI content bot. It is a **stable semi-automatic production line** with clear checkpoints, reusable assets, deterministic rendering, and recoverable failures.

The winning engineering principle is:

> **Use AI for judgment and asset generation; use software for layout, timing, reliability, traceability, and scale.**

If the system can repeatedly turn a verified source and script into a high-quality video using 7–10 consistent, text-free visual assets—and regenerate only failed scenes without wasting accepted work—you already have the foundation of an industrialized content engine.
