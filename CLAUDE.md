# DeckEngine — project guide for Claude Code

## What this is
A local-first, open-source slide generator. The core idea is **strict
separation of slide CONTENT from slide LAYOUT**: a (local) model emits content
+ fuzzy intent; a *deterministic* engine resolves geometry; the model never
places boxes. When a slide is under-constrained, the engine surfaces the fork
as a **taste question** anchored to a slide region, and the user's answer
supplies the missing constraint.

Read `README.md` for the full architecture diagram before making changes.

## The non-negotiable architectural rule
**Design decisions live in the engine, never in the model or the UI.**
- The model (`parse_to_ir`) only produces IR. It must not choose colors,
  sizes, coordinates, or archetypes.
- The UI only renders `previewSpec` verbatim. It must not invent geometry.
- If you're tempted to add x/y/w/h to the IR, stop — geometry belongs in
  `layout.py` only.

## Layout
- `deckengine/ir.py` — content/intent/theme dataclasses. **No geometry here.**
- `deckengine/layout.py` — the deterministic engine. IR + theme → resolved
  boxes (inches). This is the project's actual contribution. Keep layout rules
  explicit and constraint-based.
- `deckengine/render.py` — boxes → .pptx. Deliberately judgment-free; do not
  add design logic here.
- `deckengine/ambiguity.py` — fork detection → taste questions with `region`.
- `server.py` — FastAPI, speaks the canvas contract. Offline.
- `tests/test_layout.py` — constraint invariants (margins, no-overlap, hero
  contrast, even distribution).

## Conventions
- Python 3.11+, dataclasses over dicts for internal types, type hints required.
- Units: layout works in INCHES; canvas is 13.333 × 7.5 (16:9).
- Hex colors stored WITHOUT leading '#'; add it only at UI/JSON boundaries.
- New archetypes = a new `resolve_*` function in `layout.py` registered in
  `RESOLVERS`, plus matching constraint tests. Do not skip the tests.

## Testing requirement
Every layout change must keep `python tests/test_layout.py` at green. New
archetypes need their own invariant tests (no-overlap + margins at minimum)
before they count as done. Layout quality is *measured*, not eyeballed.

## Current state (v1) and next steps
Working end-to-end: `stat_callout` only (text → IR → engine → openable .pptx).
Detected-but-not-rendered: `icon_rows`, `two_column_stats`, `bullets_plain`.

Priority order for next work:
1. Implement the three remaining archetype resolvers (+ tests).
2. Swap `parse_to_ir` regex for a real local-model call (Ollama/LM Studio),
   emitting the same IR. Nothing downstream should change.
3. Wire the Claude Design canvas to the live `/design` endpoint. If the
   exported UI defines a different `previewSpec` shape, change ONLY
   `preview_spec()` in `server.py` to match — the contract serves the UI.
4. Deck ingest (`.pptx` → IR) per REQUIREMENTS §7.2. Content-only, geometry
   discarded by design. New module `deckengine/ingest.py`; do NOT put parsing
   in the engine or renderer (§7.1.1). Ship the §7.4.1 tests.
5. Condense/summarize (IR → smaller IR) per REQUIREMENTS §7.3. Build the
   deterministic stat-gathering fallback (§7.3.4) FIRST and test it (§7.4.2);
   the model-based path comes after and must remain reviewable (§7.3.3).
6. (Research-flavored) Replace hand-written ambiguity rules with a principled
   scorer: ask when two archetypes score within ε. And make "directions" vary
   structure, not just palette.

## Known limitations to preserve awareness of
- Directions currently differ only by color (same geometry by design).
- No image/chart rendering yet (plan: icon + shape composition before any
  diffusion).
- Renders assume Georgia/Calibri are installed; no font embedding.

## Planned features (specced; not yet implemented)

These extend the existing architecture. None of them relax §0. Each one fits
into the established layers — content in IR, geometry in the engine, style
in a theme or a dedicated renderer module. If a proposed addition seems to
break that, the design is wrong; raise it before implementing.

### A. Mathematical plots & visualizations (3Blue1Brown idiom)

Slides whose payload is a function plot, parametric curve, vector field, or
similar mathematical visual. Rendered in the **3Blue1Brown visual language**:
serif math typography, manim-flavored palette (deep navy background, yellow
hero, soft cyan/red/green secondaries), generous whitespace, one idea per
panel.

**Architectural placement (MUST):**

- New `BlockKind`: `MATH_PLOT`. Carries the **mathematical content only** —
  expression(s), independent-variable name, domain, optional parameter set
  (`{name, default, min, max, step}`), and a caption. No pixels, no axis
  coordinates in output space, no colors. (R0.1 still binding.)
- New `LayoutIntent`: `math_explainer`. Resolver places a hero plot region
  + caption + optional side notes, evenly and within margins. The layout
  engine decides WHERE the plot box goes; it does NOT decide what the plot
  contains. (R0.2.)
- New module: **`deckengine/viz.py`**. Pure function: `MATH_PLOT` block +
  resolved plot box (in inches) + theme → a vector/raster plot image
  matching the 3B1B idiom. This is a *content renderer*, not a layout
  engine. Lives next to `parse_to_ir`, not inside `layout.py`. The slide
  renderer (`render.py`) embeds the image verbatim in the resolved plot
  box. `render.py` stays judgment-free. (R0.3.)
- The 3B1B visual idiom (palette, font, line weights, axis style) lives in
  an extension of `Theme` — e.g. `Theme.math_style` — so swapping themes
  swaps the plot's look without changing the math or the box geometry.
  (R1.6.1 — directions must not change geometry.)

**Interactive tuning (split-screen):**

- In the UI, a `MATH_PLOT` slide gets a **mini split-screen** inside the
  center panel: slide design on one side, live plot rendering on the
  other. Sliders/inputs bound to the block's `parameters` re-render only
  the plot (cheap), not the whole deck.
- Slider state IS IR state. Editing a slider mutates the block's parameter
  defaults; the user is editing content, not layout. No geometry leaks
  into the slider model.
- An offline `/plot` endpoint on `server.py` returns the rendered plot for
  a given block + parameter snapshot. Kept separate from `/design` so the
  layout pipeline is not re-invoked on every slider tick.

**Tests required before this counts as done:**

- `MATH_PLOT` round-trip through IR carries no geometry (parallels R7.2.2).
- `resolve_math_explainer` passes R2.5.1 (margins) and R2.5.2 (no overlap
  between plot box and caption/notes).
- `viz.py` is deterministic on `(block, parameters, theme)` (parallels
  R2.4.2). Snapshot test on a fixed expression + params.

**Prior art / attribution (R6):** Mathematical-explainer visualization in
this idiom is Grant Sanderson's manim and the 3Blue1Brown channel.
DeckEngine does not reimplement manim; it borrows the visual language for
static slide output. Document this in `PROVENANCE.md` when the feature
lands. No novelty claims.

### B. Outline editor (left panel)

Per-slide editable view of: slide title, **three key messages**, intent.
This is the IR's content surface stripped of geometry — the model's output
made directly editable by the user.

**Architectural placement (MUST):**

- Add a `key_messages: list[str]` field to `Slide` in `ir.py`. Three is the
  typical case; the field is a list, not a fixed-arity tuple, so the model
  is not forced to invent points it doesn't have. Empty is valid.
- Key messages are **content**, not layout. They may or may not be rendered
  on the slide directly — by default they are speaker-facing scaffolding,
  similar to `notes`. (R0.1: no geometry on this field.)
- Edits in the outline panel mutate IR and re-trigger the engine. Same
  `/design` contract; no new endpoint needed.

**Tests required before this counts as done:**

- `Slide` with key messages round-trips through serialization unchanged.
- Resolving a slide with vs. without key messages yields identical
  geometry (key_messages must not leak into layout — direct R0.1 test).

### C. Three-panel UI layout

The canvas becomes a fixed three-pane layout:

- **Left:** outline editor (feature B). The deck as a list of slides; each
  expandable to title + key messages + intent.
- **Center:** slide editor — current slide preview + floating taste
  questions anchored to `region` (existing ambiguity layer behavior).
  For `MATH_PLOT` slides, center hosts the split-screen (feature A).
- **Right:** **results representation** — the live, interactive output of
  the current slide. For ordinary slides this is the rendered preview at
  presentation fidelity. For `MATH_PLOT` slides this is the tunable plot
  with the parameter sliders.

**Architectural placement (MUST):**

- All three panels read the same `previewSpec`/IR contract that already
  exists between `server.py` and the canvas (see README "UI contract").
  The backend does not learn about panels; it serves the same JSON. The
  panel split is purely a UI concern.
- The center panel's floating questions remain anchored via the existing
  `region` field on `Question`. Do not add new regions for the new panels
  — `region` is a position within the slide, not within the app.
- If the canvas export changes the `previewSpec` shape to accommodate
  panels, change ONLY `preview_spec()` in `server.py` — same rule as
  before; the contract serves the UI.

### Priority slot

These features slot **after** the current priority list (archetype
resolvers → local-model swap → canvas wiring → ingest → condense →
principled ambiguity scorer). Do not start them before the v1 archetype
work lands; an editor with two extra panels showing the same one archetype
is not the point.
