# PROVENANCE

Attribution map for DeckEngine's major components. Every load-bearing idea
here has published precedent; DeckEngine is a packaging/engineering effort,
not a research contribution. This file is the basis for the README's
"Prior art & inspiration" section (R6.2) and is binding under REQUIREMENTS.md
§6.

**Nothing in DeckEngine is claimed to be novel.** Where this file says "what
DeckEngine does differently," that means *engineering* difference (offline,
local, usable by a non-expert) — not methodological novelty.

---

## IR (`ir.py`)

- **Closest prior art (§6):** Content/geometry separation via a semantic IR —
  LayoutTransformer and the "intermediate action schema" line of automatic
  layout generation, where elements carry both semantic and geometric info
  and the two are separated; "slide" is explicitly named as a target domain.
- **What DeckEngine does differently (engineering only):** An instance of the
  same paradigm shaped to a small, fixed set of slide block kinds and a
  single `emphasis` integer — small enough that a local model can emit it
  reliably offline.

## Layout engine (`layout.py`)

- **Closest prior art (§6):** Design principles as layout constraints with
  rules that adjust on overflow (existing patents on constraint-and-rule-based
  page layout); semantic-IR → constraint-solver decomposition (e.g.
  NL→constraint→spatial-solver pipelines published in adjacent domains such
  as 3D scene synthesis, 2025).
- **What DeckEngine does differently (engineering only):** A clean-room
  reimplementation of the well-known constraint pattern, scoped to a 16:9
  slide canvas, pure-Python, no solver dependency, deterministic per
  archetype — runnable offline on a laptop.

## Ambiguity layer (`ambiguity.py`)

- **Closest prior art (§6):** Ask-on-detected-ambiguity formalized for LLM
  tasks ("Clarify When Necessary"; "Structured Uncertainty"-style work).
- **What DeckEngine does differently (engineering only):** Applies the
  established ask-on-ambiguity framework to the slide-layout setting and
  anchors each question to a slide `region` so a UI can place it spatially.
  The current rules are hand-written placeholders; the principled scorer is
  unbuilt and remains a human design decision.

## Directions feature (palette swap in `ir.py` / `layout.py`)

- **Closest prior art (§6):** Scout (CHI lineage, 2020) — constraint solver
  produces multiple satisfying layouts for human selection; mixed-initiative.
- **What DeckEngine does differently (engineering only):** Same `Slide`
  resolved through different `Theme`s yields multiple "directions" without
  re-solving geometry — directions vary only in palette in v1. This is
  Scout's idea in its weakest form (color-only variation, not structural),
  packaged so end users see alternatives by default.

## Slide voice (`humanplease_slides.md`, `workspace_gen.py`)

- **Source:** the author's own humanplease writing skills
  (github.com/ghanemja/humanplease), vendored at a pinned commit into
  `deckengine/vendor/humanplease/` by `scripts/sync_humanplease.py` (the
  commit is in `SOURCE.json`). `natural-voice-writing` draws its "shape"
  rules from the StoryScope study of human vs model fiction (COLM 2026), as
  cited in that skill.
- **What DeckEngine does with it (engineering only):** A short, slide-only
  derivation (`deckengine/humanplease_slides.md`) is appended to every
  generation prompt: real specifics or a visible placeholder, the banned
  phrase list, no em dashes, no stated moral, an honest bullet count. The
  prose-only rules are left out, and `natural-word-choice`'s
  "invent a specific person" rule is deliberately not used, since on a slide
  an invented specific is a fabricated fact. Measured with
  `scripts/eval_voice.py`.

## Diagram engine (`diagram.py`)

- **Closest prior art (§6):** Layered graph drawing — Sugiyama, Tagawa & Toda,
  "Methods for Visual Understanding of Hierarchical System Structures"
  (1981): cycle removal, layer assignment, crossing reduction by barycenter,
  coordinate assignment. Graphviz `dot` (Gansner et al., 1993) and ELK
  Layered are the standard implementations. Tidy trees after Reingold &
  Tilford (1981). Orthogonal connector routing as in every flowchart tool.
  Swimlane, timeline, 2x2 and funnel forms are long-standing business-diagram
  conventions (e.g. PowerPoint SmartArt).
- **What DeckEngine does differently (engineering only):** a small,
  deterministic, pure-Python subset sized for one slide, with invariants that
  are tested (no overlap, no connector through a box, labels fit) and output
  drawn as native editable PowerPoint shapes. No novelty claimed.

## Vendored browser libraries and fonts (`frontend/vendor/`)

Committed so the app runs with no internet access. Fetched by
`scripts/vendor_frontend.py`, which takes each library from both unpkg and
jsDelivr and refuses unless the bytes match; every file's SHA-384 is in
`frontend/vendor/MANIFEST.json` (`--check` re-verifies). Not modified.

- **React / ReactDOM 18.3.1** (production builds) — MIT, Meta Platforms.
- **@babel/standalone 7.29.0** — MIT, the Babel contributors.
- **pdf.js (`pdfjs-dist`) 3.11.174**, legacy build + worker — Apache-2.0,
  Mozilla.
- **JSZip 3.10.1** — MIT or GPLv3 (dual), Stuart Knightley et al.; used here
  under MIT.
- **Fonts** — IBM Plex Sans, IBM Plex Mono, IBM Plex Serif (IBM), Lato
  (Łukasz Dziedzic), Newsreader (Production Type), Space Grotesk (Florian
  Karsten) and Manrope (Mikhail Sharanda): all under the **SIL Open Font
  License 1.1**. The woff2 files are Google Fonts' latin and latin-ext
  subsets, unmodified; `fonts/fonts.css` is Google's CSS with the URLs made
  local. The OFL allows bundling and redistribution with software; the fonts
  may not be sold on their own.

## Semantic model (`models/`, not committed)

- **all-MiniLM-L6-v2** (sentence-transformers, Apache-2.0), downloaded once at
  a pinned revision by `scripts/fetch_models.py` and loaded from disk with
  `local_files_only`. Its model card (`README.md`, with the licence) is
  saved alongside the weights.
