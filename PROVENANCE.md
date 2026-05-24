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
