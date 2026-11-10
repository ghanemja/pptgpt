# DeckEngine — project guide for Claude Code

## What this is
A local-first, open-source slide generator. The core idea is **strict
separation of slide CONTENT from slide LAYOUT**: a (local) model emits content
+ fuzzy intent; a *deterministic* engine resolves geometry; the model never
places boxes. When a slide is under-constrained, the engine surfaces the fork
as a **taste question** anchored to a slide region, and the user's answer
supplies the missing constraint.

Read `README.md` for the full architecture diagram before making changes.

## Templates: who owns geometry
Without a template, `layout.py` owns geometry — the rule below applies as
written. With an uploaded template, the TEMPLATE owns it: `deckengine/
native.py` casts a slide into that template's own layouts and fills its
placeholders, so position, size, type ramp, colour and bullet styling all
inherit from the file. Approximating a template with engine-placed boxes was
tried first and does not work: a real template's design IS its layouts.

A slide is classified by what it carries — cover, section break, statement,
two-column, picture, bullets — and matched to the layout whose roles fit,
so a template's full range gets used rather than one title-and-bullets
layout. Charts and plots render to PNG and land in the template's picture
slot, letterboxed rather than cropped.

§0 is intact where it matters — the model and the UI still choose no
geometry. Layout selection is a deterministic function of the slide's
content and the template's layout inventory. `tests/test_native.py` asserts
that a cast slide never moves a template placeholder and never writes a
font, size or colour onto a run.

## The non-negotiable architectural rule
**Design decisions live in the engine, never in the model or the UI.**
- The model (`parse_to_ir`) only produces IR. It must not choose colors,
  sizes, coordinates, or archetypes.
- The UI only renders `previewSpec` verbatim. It must not invent geometry.
- If you're tempted to add x/y/w/h to the IR, stop — geometry belongs in
  `layout.py` only.

## Layout
- `deckengine/ir.py` — content/intent/theme dataclasses. **No geometry here.**
- `deckengine/parse.py` — text → IR. The local-model swap point.
- `deckengine/layout.py` — the deterministic engine. IR + theme → resolved
  boxes (inches). This is the project's actual contribution. Keep layout rules
  explicit and constraint-based.
- `deckengine/render.py` — boxes → .pptx. Deliberately judgment-free; do not
  add design logic here.
- `deckengine/spec_render.py` — frontend SlideSpec → .pptx (judgment-free).
- `deckengine/ambiguity.py` — principled per-archetype scorer + tie-detection
  → taste questions with `region`.
- `deckengine/ingest.py` — .pptx → IR (content only; geometry discarded
  by design per R7.2.2).
- `deckengine/condense.py` — IR → smaller IR. Deterministic stat-gathering
  fallback + model-based path with anti-fabrication guard.
- `deckengine/template.py` — an uploaded .pptx/.potx as a Theme + CONSTRAINTS
  (margins, bands the master already occupies). Never a content box: the
  template supplies brand and backdrop, `layout.py` still resolves geometry.
  `render.open_base()` opens the template file as the presentation base.
  The preview backdrop is a PNG of the master rendered through LibreOffice
  (`backdrop_png`), cached per template; the real background colour is then
  sampled off that render rather than guessed from the theme. Optional
  dependency: without `soffice` the backdrop endpoint 503s and the UI falls
  back to the template's palette.
- `deckengine/coach.py` — the critic, per slide and per deck. Named LENSES (ask, evidence, source,
  comparison, density, title, hedge, jargon, ownership, handoff) find what
  is wrong with a slide by rule; a PERSONA in `coaches/*.json` decides which
  lenses matter, how hard to push and in whose voice. `review_deck` reads a
  whole deck and tallies where it is weakest; `apply_overrides` tunes a
  persona for one sitting without editing its file. Deterministic, so a note
  is a property of the slide. Notes never carry geometry: each names the
  CONTENT it is about (`target`: `{field, index?, missing?}`), and
  `frontend/ws-annotate.jsx` finds where SlideCard drew that field
  (`data-field`) to pin the note there with a callout and leader line.
  A COMPANY KIT can restate the criteria in its own words and tune them
  (`kits/<co>/criteria.json`: labels, "what good looks like", its own
  jargon list and bullet limit, and `banned` phrase rules of its own, named
  `kit:<id>`); `parse_criteria` validates it and refuses geometry. A tuned
  reviewer can be saved (`save_persona`) to `coaches/saved/` — same format
  as a shipped persona, gitignored, never allowed a built-in's name.
- `deckengine/scorecard.py` — a PANEL of reviewers, each scoring the deck
  0–100 per aspect (clear messaging, evidence, content density, plain
  language, ownership, house rules). Scores are the coach's notes counted —
  deterministic — judged for the AUDIENCE (how much technical detail a
  slide may carry) and against the PURPOSE (the scoping decision must be
  asked for). `/api/scorecard`; the workspace's Scores strip re-scores live
  as the deck is edited (`frontend/ws-scores.jsx`).
- `deckengine/org.py` — per-organization profiles loaded from `orgs/*.json`
  and from company kits: the scoping interview, narrative arc and house
  style rules. Convention, never geometry — the loader rejects a profile
  carrying coordinates. A kit wins a slug clash with `orgs/`.
- `deckengine/kit.py` — company kits. `kits/<slug>/` is the source of truth
  (profile.json, voice.md, a top-level template, examples/, assets/ +
  assets.csv, learned.json); upload, "point to a folder" (copy or link) and
  files dropped in by hand all land in the same folder, and `scan()` re-reads
  it every call. Also the asset library search, SVG→PNG, and `house_brief`
  (rules + learned norms + voice → generation prompt). Import and reveal
  answer to localhost only.
- `deckengine/humanplease_slides.md` — the slide voice: a short block
  derived from the humanplease writing skill (pinned copy in
  `deckengine/vendor/humanplease/`, refreshed only by
  `scripts/sync_humanplease.py`, never fetched at runtime). `workspace_gen`
  appends it to every feature's prompt after the house style. Content rules
  only; `tests/test_workspace_gen.py` keeps it short, geometry-free and in
  step with the vendored commit. `scripts/eval_voice.py` A/Bs it.
- `deckengine/kit_ingest.py` — `learn(slug)`: MEASURES the example decks
  (points/slide, words/point, titles, visuals, layouts, type) into
  learned.json, with norms and suggested rules. Never inferred by a model.
- `kits/` — one folder per company; git-ignored except `kits/README.md`
  (the user-facing setup guide) and `kits/example-co/` (a working example,
  rebuilt by `scripts/make_example_kit.py`). Install guide: `SETUP.md`;
  start script: `scripts/start.sh` (binds 127.0.0.1, auth off).
- `frontend/ws-*.jsx` — the workspace UI: React + Babel standalone from a
  CDN, no bundler; modules share via `Object.assign(window, {...})`, and a
  new file is registered in `frontend/workspace.html` and
  `scripts/build-netlify.mjs`. `ws-kit.jsx` is kit setup, `ws-library.jsx`
  the asset library (sets `slide.image = {kit, file, label}` — a reference,
  never a position). `ws-thread.jsx` is Story → Threads, drawing
  `threadmap.py`'s graph (fast read first, the model's read after). `window.WS_ORG` names the selected company on every API
  call; read it at call time, as `window.aiGenerate` must be (the backend
  wrapper replaces it after load).
- `deckengine/preview.py` — EXACT slide previews: one spec through
  `spec_render` onto the template master, rasterised by LibreOffice and
  cached by content hash. The HTML preview can only draw with fonts the
  viewer has installed, so it is the fallback, not the source of truth.
- `deckengine/boundary.py` — adds `#` and converts inches→pixels at the JSON
  edge. The ONLY place that translation happens.
- `frontend/` — every page and asset, flat, one copy each. `server.py`
  serves it as-is; `scripts/build-netlify.mjs` copies it into the static
  deploy. Do not fork a page into a second directory — edit it in place.
- `server.py` — FastAPI, speaks the canvas contract. Offline.
- `tests/test_layout.py`, `tests/test_ingest.py`, `tests/test_condense.py`,
  `tests/test_ambiguity.py`, `tests/test_org.py`, `tests/test_template.py`,
  `tests/test_native.py`, `tests/test_coach.py`, `tests/test_scorecard.py`,
  `tests/test_charts.py`, `tests/test_kit.py`,
  `tests/smoke_e2e.py` — invariant + endpoint tests.

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
Working end-to-end via the IR engine: every archetype — `stat_callout`,
`title_slide`, `two_column_stats`, `icon_rows`, `bullets_plain` — renders
to openable `.pptx`. The `/api/design` endpoint exercises the §0 path
(parse_to_ir → ambiguity scorer → layout.resolve → render). It is the only
server-side slide pipeline: the old `synth.py` direct-SlideSpec path (a
Python port of `frontend/mockBackend.js` with its own hard-coded pixel
geometry, served as `/api/backend`) was removed. The legacy `/canvas` and
`/workbench-v1` pages and the `/workbench` page get their per-mode
directions from `frontend/mockBackend.js` in the browser.

Done in v1:
1. All five archetype resolvers (+ R2.5 invariant tests, 24/24 green).
2. `deckengine/parse.py` — deterministic IR producer; documented swap
   point for the local model (single function).
3. `/api/design`, `/api/ir`, `/api/render_ir`, `/api/render_direction`,
   `/api/ingest` wired through the engine.
4. `deckengine/ingest.py` (REQUIREMENTS §7.2) — .pptx → IR, geometry
   discarded by design. §7.4.1 tests green.
5. `deckengine/condense.py` (§7.3) — deterministic stat-gathering fallback
   FIRST (§7.3.4) + model-based path with anti-fabrication guard (§7.3.5).
6. Principled ambiguity scorer in `ambiguity.py` (`score_archetypes`).
   Ask when top-2 within ε. User-agency override for the focus fork.
7. Server-side `.pptx` export visible in the UI (`save as .pptx`).
8. Bug fixes: `/api/plot` no longer cross-contaminates curve params;
   chart renderer accepts CSS `rgba(...)` strings.

Remaining priorities:
1. **The Gemma swap.** Replace `parse_to_ir` body with an Ollama/LM Studio
   call that emits a `Slide`. The entire repo downstream is unchanged.
2. (Research-flavored) Make "directions" vary structure, not just palette.
3. Feature A (math plots in the IR), B (outline editor), C (three-panel
   UI) — speccd below.

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
