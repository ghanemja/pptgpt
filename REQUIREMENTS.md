# DeckEngine — IR & Layout Engine Requirements

**Status:** v1 (stat_callout end-to-end). **Audience:** contributors and Claude Code.
**Purpose:** This document specifies the data model (IR) and the layout engine
as binding requirements. It is the contract any contributor — human or agent —
must satisfy. Where the code and this document disagree, treat the disagreement
as a bug to be reconciled, not a license to diverge.

**What this project is (and isn't).** DeckEngine is an *engineering* artifact:
a local-first, offline, open-source, interactive slide generator. It is NOT a
research contribution, and contributors MUST NOT describe it as novel. The
architecture below (typed semantic IR → deterministic constraint-based layout →
render) is the well-established consensus design of the automatic-layout field
(see §6, Prior Art). DeckEngine's value is in *packaging* these known-good ideas
for a use case the prior work did not serve — running fully offline, with a
human-in-the-loop disambiguation UX, as a tool a non-expert can actually use.
Honesty about this lineage is a project requirement, not a courtesy (see §6).

---

## 0. Governing principle (MUST)

> **Content, layout, and theme are separate concerns and MUST NOT leak into one another.**

- The model produces **content + fuzzy intent** only (the IR).
- The layout engine produces **all geometry** deterministically.
- The theme supplies **all visual style** (color, font, spacing constants).

Three prohibitions follow, and each is non-negotiable:

- **R0.1** The IR MUST NOT contain coordinates, sizes, or colors. No `x/y/w/h`,
  no point sizes, no hex values on any IR type.
- **R0.2** The layout engine MUST NOT contain content authoring. It arranges
  what it is given; it does not invent or rewrite text.
- **R0.3** The renderer MUST NOT contain design logic. It places resolved boxes
  verbatim. No conditional styling, no layout decisions.

A change that violates R0.1–R0.3 is rejected regardless of test status.

---

## 1. The Intermediate Representation (IR)

### 1.1 `BlockKind` (enum, string-valued)
The set of content block types. Current members:
`title`, `subtitle`, `paragraph`, `bullets`, `stat`, `quote`, `image`,
`icon_row`, `caption`.

- **R1.1.1** Adding a new `BlockKind` MUST be additive (no renaming/removal of
  existing members without a migration note), because IR is a serialized
  contract consumed by the model step and the API.

### 1.2 `ContentBlock` (dataclass)
A single unit of slide content. Fields:

| field | type | meaning | constraints |
|-------|------|---------|-------------|
| `kind` | `BlockKind` | the block type | required |
| `text` | `str?` | used by title/subtitle/paragraph/quote/caption | optional |
| `items` | `list[str]?` | used by `bullets` and `icon_row` | optional |
| `value` | `str?` | the stat value, e.g. `"99.97%"` | optional |
| `label` | `str?` | stat label, image alt text | optional |
| `emphasis` | `int` | 0 normal, 1 emphasized, 2 hero | default 0 |

- **R1.2.1** `emphasis` is the ONLY signal the model may give about visual
  weight. It is an *abstract* priority, not a size. The engine decides what
  emphasis means geometrically. The model MUST NOT express weight any other way.
- **R1.2.2** A `ContentBlock` MUST carry only the fields relevant to its `kind`;
  unused fields stay `None`. (e.g. a `stat` uses `value`/`label`/`emphasis`,
  not `text`.)
- **R1.2.3** No geometry or color fields may ever be added to `ContentBlock`
  (see R0.1).

### 1.3 `LayoutIntent` (enum, string-valued)
The model's *fuzzy* hint about arrangement. Current members:
`auto`, `title_slide`, `stat_callout`, `two_column_stats`, `icon_rows`,
`bullets_plain`.

- **R1.3.1** `auto` means "the engine/ambiguity layer chooses." It is the
  preferred default and MUST remain valid.
- **R1.3.2** Intent is advisory. The engine MAY override an intent when the
  content cannot support it (e.g. `stat_callout` with zero stats), but MUST
  do so deterministically and document the fallback.
- **R1.3.3** Every `LayoutIntent` value (other than `auto`) that is intended to
  render MUST eventually have a corresponding resolver (see §2). An intent with
  no resolver is an incomplete feature and MUST be documented as such.

### 1.4 `Slide` (dataclass)
Fields: `blocks: list[ContentBlock]`, `intent: LayoutIntent = auto`,
`notes: str? = None`.

- **R1.4.1** A `Slide` MUST hold no geometry. `notes` are speaker notes only.

### 1.5 `Theme` (dataclass)
Carries ALL visual style. Fields and their roles:

| field | meaning | constraint |
|-------|---------|------------|
| `primary` | slide background hex (no `#`) | required |
| `secondary` | supporting color hex | required |
| `accent` | sharp accent (hero color) hex | required |
| `fg_on_dark` / `fg_on_light` | foreground text per background mode | required |
| `sub_on_dark` / `sub_on_light` | muted/secondary text per mode | required |
| `header_font` / `body_font` | font family names | required |
| `dark` | is this slide a dark background? | drives fg/sub selection |
| `margin_in` | hard outer margin, inches | **constraint, not hint** |
| `gap_in` | gap between content blocks, inches | **constraint, not hint** |
| `name` | human label for the palette | required |

- **R1.5.1** All colors are stored as 6-digit hex **without** a leading `#`.
  The `#` is added ONLY at JSON/UI boundaries. Internal code MUST NOT carry `#`.
- **R1.5.2** `margin_in` and `gap_in` are spacing **constraints**. The engine
  MUST treat them as hard values, never approximate or ignore them.
- **R1.5.3** Foreground selection MUST go through the `dark` flag (a slide on a
  dark background uses `fg_on_dark`/`sub_on_dark`, and vice versa). The engine
  MUST NOT hardcode a text color. This is what prevents low-contrast output.

### 1.6 Palettes & "directions"
`PALETTES` is a dict of named `Theme`s (`bold`, `clean`, `warm`).

- **R1.6.1** Multiple design **directions** are produced by resolving the SAME
  `Slide` through DIFFERENT `Theme`s. This means: **swapping the theme MUST NOT
  change geometry.** (Enforced by test; see R3.6.) In v1 directions differ only
  in color; a future version may introduce directions that also vary structure,
  but that MUST be done via explicit archetype choice, not by leaking style into
  layout.

---

## 2. The Layout Engine

The engine maps `(Slide, Theme[, archetype]) → ResolvedSlide`. It is the
project's core contribution and MUST remain pure and deterministic.

### 2.1 Canvas
- **R2.1.1** The canvas is **16:9 widescreen: 13.333 × 7.5 inches.** All engine
  math is in **inches**. These constants (`CANVAS_W`, `CANVAS_H`) are the single
  source of truth.

### 2.2 `Box` (resolved element)
Fields: `x, y, w, h` (inches), `role` (str), `text`, `font`, `size_pt`, `bold`,
`color` (hex no `#`), `align` (`left|center|right`), `valign` (`top|middle|bottom`).

- **R2.2.1** A `Box` is fully resolved: every field has a concrete value. The
  renderer needs no further decisions.
- **R2.2.2** `role` is a stable string tag (`"title"`, `"stat_value"`,
  `"stat_label"`, …) usable by tests and the UI to identify elements. New
  archetypes define their own role names; roles SHOULD be descriptive.

### 2.3 `ResolvedSlide`
Fields: `boxes: list[Box]`, `bg: str` (hex no `#`), `archetype: str`.

### 2.4 Resolvers
Each archetype is one function `resolve_<archetype>(slide, theme) -> ResolvedSlide`,
registered in the `RESOLVERS` dict. The dispatcher `resolve(slide, theme, archetype=None)`
selects by explicit `archetype`, else by `slide.intent`, else falls back.

- **R2.4.1** Adding an archetype = adding ONE `resolve_*` function + registering
  it. No other module changes for a new archetype (the renderer is generic).
- **R2.4.2** A resolver MUST be a pure function of its inputs: same
  `(Slide, Theme)` in ⇒ byte-identical `ResolvedSlide` out. No randomness, no
  clocks, no global state.
- **R2.4.3** A resolver MUST raise `ValueError` with a clear message if the
  content cannot support the archetype (precedent: `resolve_stat_callout`
  raises when there are no stats).

### 2.5 Layout invariants (these are the requirements that make output "good")
Every resolver MUST satisfy, for all valid inputs:

- **R2.5.1 — Margins are a hard floor.** Every box lies fully within the
  margin box: `x ≥ margin_in`, `y ≥ margin_in`, `x+w ≤ CANVAS_W − margin_in`,
  `y+h ≤ CANVAS_H − margin_in`.
- **R2.5.2 — No overlap among peer elements.** Boxes that are siblings of the
  same role class (e.g. the set of `stat_value` boxes, the set of bullet rows)
  MUST NOT overlap. (Intentional layering, if ever needed, must be explicit and
  justified; default is no overlap.)
- **R2.5.3 — Title/body size contrast.** When a title is present, its
  `size_pt` MUST be ≥ 2× the smallest body/label `size_pt` on the slide.
- **R2.5.4 — Hero dominance.** When emphasis designates a hero element, its
  primary text `size_pt` MUST be ≥ 1.3× its non-hero peers, and it SHOULD use
  the theme `accent` color.
- **R2.5.5 — Even distribution.** Elements arranged in a row/grid MUST be
  evenly spaced: equal gaps between adjacent peers (within float tolerance).
- **R2.5.6 — Text alignment discipline.** Titles MAY be centered; body text,
  bullets, and paragraphs MUST be left-aligned. (Stat values/labels, being
  short and columnar, MAY be centered within their cell.)
- **R2.5.7 — Contrast via theme.** Foreground colors MUST be selected through
  the theme's dark/light logic (R1.5.3); a resolver MUST NOT emit a color that
  matches or near-matches the background.

### 2.6 Per-archetype shape requirements (v1 + planned)

- **stat_callout** (DONE): title top-left; N stat columns evenly distributed
  across the content band; one hero (emphasis≥2, else first) larger and in
  accent; each stat is a `stat_value` box above a `stat_label` box.
- **two_column_stats** (PLANNED): title top; left column = bullets (≈60% width),
  right column = stacked stats (≈40%); columns MUST NOT overlap and MUST align
  to the same top.
- **icon_rows** (PLANNED): title top; vertical list of rows, each = a numbered/
  icon marker + a label; rows evenly spaced; marker and label vertically
  centered to each other.
- **bullets_plain** (PLANNED): title top; single left-aligned bullet list in the
  content band; when too many items, the density decision (see ambiguity layer)
  governs whether to truncate/continue.

- **R2.6.1** Each PLANNED archetype is "done" only when it (a) has a resolver,
  (b) passes R2.5.1 and R2.5.2 tests specifically written for it, and (c) is
  registered in `RESOLVERS`.

---

## 3. Testing requirements

- **R3.1** `tests/test_layout.py` MUST stay green on every commit.
- **R3.2** Every resolver MUST have, at minimum, a margins test (R2.5.1) and a
  no-overlap test (R2.5.2).
- **R3.3** Tests assert **invariants**, not pixel-exact coordinates, so the
  engine can be refactored without rewriting tests.
- **R3.4** The hero-contrast (R2.5.4) and title/body-contrast (R2.5.3) invariants
  MUST be tested for any archetype that has a hero or a title.
- **R3.5** Even-distribution (R2.5.5) MUST be tested for any row/grid archetype.
- **R3.6** A test MUST assert that resolving one `Slide` through all `PALETTES`
  yields identical geometry and differing background color (R1.6.1).

---

## 4. Boundaries to other components (informative, not the focus here)

- The **model step** (`parse_to_ir`) produces IR and nothing else. Swapping the
  regex stub for a local LLM MUST NOT require any change in §1–§3.
- The **API** (`server.py`) adds `#` to colors and converts inches→percent at
  the JSON boundary only; it performs no layout.
- The **UI** renders `previewSpec` verbatim and invents no geometry.

These boundaries exist so the engine (§2) can be developed, tested, and
released as a self-contained, well-tested artifact.

---

## 5. Change control

- Any change to §1 (IR) or §2.2–2.3 (resolved types) is a **contract change**
  and MUST be noted in `README.md` and reflected in `server.py`'s boundary code.
- Any new archetype MUST update §2.6 and ship its tests (§3.2).
- Violations of §0 are not mergeable.

---

## 6. Prior art & attribution (MUST)

DeckEngine's architecture is **not novel**, and the project's honesty about this
is a hard requirement. A literature scan (May 2026) found every load-bearing
idea has published precedent. Contributors and any generated documentation MUST
NOT claim novelty, MUST cite the lineage below where relevant, and MUST frame
DeckEngine as a *packaging/engineering* contribution (offline, local-first,
interactive, usable) rather than a research one.

**The lineage (cite these in README, not as ours):**

- *Content/geometry separation via a semantic IR* — the defining paradigm of
  automatic layout generation. Layout-generation work (e.g. LayoutTransformer
  and the "intermediate action schema" line of work) treats elements as carrying
  both semantic and geometric info and separates the two; "slide" is explicitly
  named as a target domain. **Our IR (§1) is an instance of this, not new.**
- *Design principles as layout constraints, with rules that adjust on overflow*
  — covered by existing patents on constraint-and-rule-based page layout.
  **Our §2.5 invariants + overflow handling implement a known, patented pattern.
  Clean-room reimplementation of well-known techniques is fine; novelty claims
  are not.**
- *Semantic-IR → constraint solver decomposition* — actively published in
  adjacent domains (e.g. NL→constraint→spatial-solver pipelines in 3D scene
  synthesis, 2025). **Our pipeline shape is the 2D-slide version of an
  established decomposition.**
- *Constraint solver producing multiple layout alternatives for human selection*
  — Scout (CHI-lineage, 2020): high-level constraints in, multiple satisfying
  layouts out, mixed-initiative. **Our "directions" feature is this idea.**
- *Ask-on-detected-ambiguity beats auto-resolving* — formalized for LLM tasks
  ("Clarify When Necessary"; "Structured Uncertainty"-style work). **Our
  human-in-the-loop disambiguation UX applies an established framework to the
  slide-layout setting; it is not a new method.**
- *Slide-generation systems & evaluation* — AutoPresent (small open model ≈
  GPT-4o on slides), PPTAgent / PPTEval (edit-based generation + Content/Design/
  Coherence evaluation). **If we ever quantitatively evaluate output, use or
  compare against these rather than inventing metrics.**

**Requirements:**

- **R6.1** No file in this repo (README, code comments, docs, commit messages,
  release notes) may describe DeckEngine or any of its components as "novel,"
  "first," "new approach," or equivalent. State what it *is*: a local-first,
  offline, open-source reimplementation packaged for end-user use.
- **R6.2** The README MUST contain a "Prior art & inspiration" section citing
  the lineage above, stating plainly that the architecture follows established
  work and that DeckEngine's contribution is packaging/usability/offline
  operation.
- **R6.3** If a contributor (human or agent) believes some specific element IS
  genuinely novel, that claim MUST be supported by its own literature check
  recorded in the PR, not asserted. Default assumption: it is prior art.
- **R6.4** This section is informational about *positioning*; it does not relax
  any engineering requirement in §0–§5. Good engineering is still required —
  being unoriginal is not an excuse for being sloppy.

---

## 7. Deck ingest & condense/summarize (planned subsystem)

Two related capabilities for working with *existing* decks: importing a
half-finished or finished `.pptx`, and condensing a multi-slide deck into a
shorter summary (e.g. several slides → one stat/summary slide). These are NEW
subsystems, not engine changes, and they MUST respect §0.

### 7.1 The architectural placement (MUST)
- **R7.1.1** Ingest and summarization are **content operations**, and per §0
  they MUST NOT live in the layout engine (`layout.py`) or the renderer
  (`render.py`). The engine still only arranges; the renderer still only draws.
- **R7.1.2** Ingest produces **IR** (§1). Summarization transforms **IR → smaller
  IR**. Both sit at the model/content layer alongside `parse_to_ir`, in a new
  module (suggested: `deckengine/ingest.py` for import, `deckengine/condense.py`
  for summarization). Downstream (§2–§3) is unchanged: imported/condensed IR
  flows through the same engine, tests, and renderer as authored IR.

### 7.2 Ingest: `.pptx` → IR (planned)
- **R7.2.1** Ingest reads an existing `.pptx` and extracts **content only**:
  per-slide titles, body text/bullets, stat-like values, speaker notes. Use
  `python-pptx` to walk slides → shapes → text frames. Text extraction MAY
  follow the "one section per slide" pattern (see the pptx skill).
- **R7.2.2** **Ingest is intentionally lossy and MUST NOT attempt to preserve
  original geometry, themes, exact fonts, or positioning.** The imported deck's
  layout is *discarded by design*; the engine re-resolves layout from the
  extracted content. This is a stated product behavior, not a bug — document it
  prominently so users do not expect round-trip fidelity. A deck round-tripped
  through ingest → engine will look different from the original.
- **R7.2.3** Ingest MUST classify extracted content into existing `BlockKind`s
  conservatively. When a shape's role is ambiguous (is "94%" a stat or body
  text?), it MAY default to a safe kind (paragraph/bullets) rather than guess a
  stat. Heuristics for stat detection SHOULD mirror `parse_to_ir`.
- **R7.2.4** Content ingest MUST NOT extract or store images of people, and MUST
  NOT attempt OCR of faces or any facial data. Embedded images are out of scope
  for v1 ingest (extract their presence/alt text as an `IMAGE` block label at
  most; do not copy binary image data into the IR).
- **R7.2.5** Ingest MUST degrade gracefully: a slide it cannot parse becomes a
  best-effort title+paragraph IR, never a crash. Log what was dropped.

### 7.3 Condense / summarize: IR → smaller IR (planned)
- **R7.3.1** Summarization reduces a multi-slide deck's IR to a shorter IR
  (e.g. extract the key stats across slides into a single `stat_callout` summary
  slide, or collapse N content slides into one bulleted overview). It is a
  **model-layer transform**, performed by the same local model that backs
  `parse_to_ir` (or a deterministic fallback). It MUST output valid IR (§1) and
  nothing else — no geometry, no prose commentary.
- **R7.3.2** Summarization is the single feature most dependent on model quality
  and therefore the **least reliable in fully-offline mode**. A small local
  model will sometimes drop the load-bearing point. This limitation MUST be
  stated in README and surfaced to the user (e.g. "summary is AI-generated from
  your deck; review before using"). Do NOT present condensed output as
  authoritative.
- **R7.3.3** Summarization MUST be **reviewable, not silent**. The user MUST see
  what was kept vs. dropped (at minimum: which source slides fed the summary).
  Destructive replacement of the user's content without review is prohibited;
  the original imported IR MUST be retained alongside the summary.
- **R7.3.4** A **deterministic, no-model fallback** SHOULD exist for the common
  "make a summary stat chart" case: gather all `STAT` blocks across slides,
  dedupe, and emit a single `stat_callout` IR. This works offline with no model
  and is predictable; the model-based path is the richer-but-fuzzier option.
- **R7.3.5** Summarization MUST NOT fabricate stats or facts not present in the
  source IR. If it cannot find enough content to summarize, it returns a
  truthful "insufficient content" result rather than inventing material.

### 7.4 Tests
- **R7.4.1** Ingest MUST have tests on fixture `.pptx` files asserting: content
  is extracted, geometry is NOT carried into the IR (R7.2.2), and an
  unparseable slide degrades rather than crashes (R7.2.5).
- **R7.4.2** The deterministic summarize fallback (R7.3.4) MUST have a test:
  given a multi-slide IR with known stats, the summary IR contains those stats
  and no fabricated ones (R7.3.5).
- **R7.4.3** Model-based summarization need not be unit-tested for content
  quality (non-deterministic), but its IR *output validity* MUST be tested
  against a stubbed/mock model.

### 7.5 Out of scope for v1
- Preserving or re-applying the source deck's visual theme.
- Editing the source `.pptx` in place (we generate a new deck; we do not mutate
  the upload — consistent with not performing destructive operations).
- Image content beyond presence/alt-text. No image generation, no face data.
