# DeckEngine

A local-first, open-source slide generator built on one idea:

> **Separate slide CONTENT from slide LAYOUT.** A model emits content + fuzzy
> intent. A *deterministic* engine resolves geometry. The model never places
> boxes — which is why the output isn't ugly.

When a slide is genuinely under-constrained (more than one sound design),
the engine doesn't guess. It surfaces the fork as a **taste question**
anchored to the slide region it affects, and the user's answer supplies the
missing constraint. This turns the hard "pick the right layout automatically"
problem into a UX affordance.

**Running it on your own machine:** [SETUP.md](SETUP.md) — Python, Ollama +
`gemma3:4b`, LibreOffice, then `scripts/start.sh`.
**Teaching it your company's style:** [kits/README.md](kits/README.md) —
template, example decks, icons, house rules and voice, added by upload, by
pointing at a folder, or by dropping files into `kits/<company>/`.

## Architecture

```
rough text ──(parse_to_ir)──► Slide IR ──(ambiguity.detect)──► taste questions
                                  │                                   │
                                  │            user answers ──────────┘
                                  ▼
                          layout engine (deterministic)
                                  │
                    ┌─────────────┼─────────────┐   ← one IR, three themes
                  bold          clean          warm    = three "directions"
                    └─────────────┼─────────────┘       for free
                                  ▼
                         .pptx renderer (judgment-free)
```

- `deckengine/ir.py` — content/intent/theme dataclasses. **No geometry.**
- `deckengine/parse.py` — text → IR. The local-model swap point.
- `deckengine/ambiguity.py` — principled per-archetype scorer. Asks when
  the top-2 are within ε.
- `deckengine/layout.py` — **the contribution.** IR + theme → resolved
  boxes (inches). Five archetypes. Layout rules are explicit constraints.
- `deckengine/render.py` — boxes → `.pptx`. Deliberately judgment-free.
- `deckengine/spec_render.py` — frontend SlideSpec → `.pptx`. Same rule.
- `deckengine/ingest.py` — `.pptx` → IR. Content-only; geometry discarded.
- `deckengine/condense.py` — IR → smaller IR. Deterministic fallback first,
  model-based path optional. Anti-fabrication guard at the boundary.
- `deckengine/boundary.py` — adds `#` to colors, converts inches → pixels
  for the JSON layer. The ONLY place those conversions happen.
- `server.py` — FastAPI; speaks the canvas data contract. Offline.
- `tests/` — 48 unit tests, all green. Layout invariants for every resolver.

## Why the tests matter

`good layout` is usually treated as taste. Here it's invariants:
margins are a hard floor, peer elements never overlap, the hero stat is
≥1.3× its neighbors, title is ≥2× the labels, palettes never change
geometry. Refactor the engine freely; the invariants catch regressions.
This is what makes the approach defensible.

```bash
python tests/test_layout.py      # 24/24 — every resolver
python tests/test_ingest.py      # 6/6   — .pptx → IR safety
python tests/test_condense.py    # 8/8   — no fabrication
python tests/test_ambiguity.py   # 10/10 — scorer + tie detection
python tests/smoke_e2e.py  # every endpoint
```

## Run

Full install for a work machine: [SETUP.md](SETUP.md). Day to day:

```bash
scripts/start.sh                               # checks deps, serves 127.0.0.1:8000
# open http://127.0.0.1:8000/
```

Or by hand:

```bash
pip install -r requirements.txt
python -m uvicorn server:app --reload          # offline API on :8000
# open http://localhost:8000/ — the workspace (the only page)
```

## API

### IR-engine path (the project's stated contribution)

```
POST /api/design        rawContent + answers → slideIR + questions + directions
POST /api/ir            rawContent → Deck IR (peek at the content layer)
POST /api/ingest        .pptx upload → Deck IR (content only)
POST /api/render_ir     rawContent + palette → .pptx via the engine
```

### Frontend contract

```
POST /api/storyboard      mirror of `window.extractStoryboard(req)`
POST /api/critique        mirror of `window.generateCritique(req)`
POST /api/render          { slides: SlideSpec[] } → .pptx
POST /api/render_direction { direction } → .pptx (one-click export)
POST /api/plot            { block, params } → PNG (server-side rasterized plot)
```

See `frontend/types.md` for the SlideSpec contract.

There is one server-side slide pipeline: the IR engine, and one page: the
workspace at `/`. The old landing, setup, storyboard, workbench and canvas
pages (and `mockBackend.js`, their in-browser demo backend) were deleted;
their URLs redirect to `/`.

All assets live flat in `frontend/` — one copy of each file.
`scripts/build-netlify.mjs` assembles the static deploy from there.

## The UI contract (for the Claude Design canvas)

UI → backend: `{ rawContent, answers }`
backend → UI: `{ slideIR, questions:[{id,region,text,options}], directions:[{key,label,previewSpec}] }`

`previewSpec` carries fully-resolved geometry as pixel coordinates so the
canvas renders verbatim and invents nothing. `region` ∈ {top,bottom,left,right}
drives where a question card anchors and which way it drifts when answered.

## The local-model swap (the only thing left for v1.1)

`parse_to_ir()` in `deckengine/parse.py` is a deterministic regex
classifier. To run on a local LLM (Ollama / LM Studio / Gemma), replace the
body of that ONE function with a model call that emits a `Slide`.
Everything downstream — ambiguity scorer, engine, ingest, condense, render,
tests — is unchanged. That's the point of the §0 separation.

```python
# deckengine/parse.py
def parse_to_ir(text: str) -> Slide:
    json_str = ollama_chat(SYSTEM_PROMPT, text)   # ← only this changes
    return _slide_from_json(json_str)
```

## Prior art & inspiration

The architecture below is **not novel**. Every load-bearing idea has
published precedent; DeckEngine packages them for offline, local, end-user
use. Key lineages we draw on:

- **Content/geometry separation via a semantic IR** — the defining paradigm
  of automatic layout generation (LayoutTransformer and the
  "intermediate action schema" line of work).
- **Design principles as layout constraints** — existing patents on
  constraint-and-rule-based page layout. Our §2.5 invariants implement a
  known, patented pattern; clean-room reimplementation is fine, novelty
  claims are not.
- **Constraint solver producing multiple alternatives** — *Scout*
  (CHI 2020): high-level constraints in, multiple satisfying layouts out,
  mixed-initiative. Our "directions" feature is this idea.
- **Ask-on-detected-ambiguity beats auto-resolving** — "Clarify When
  Necessary" / structured-uncertainty work. The taste-question UX applies
  this to the slide-layout setting.

See `PROVENANCE.md` for the full attribution. DeckEngine's contribution is
**packaging** (offline, local-first, interactive, usable) — not algorithms.

## Honest limitations (v1)

- **Directions vary palette only.** Same geometry across `bold`/`clean`/
  `warm`. Structural variation per direction is research-flavored work.
- **No font embedding.** Renders assume Georgia/Calibri are installed.
- **Condense is reviewable, not silent — but small.** The deterministic
  fallback only carries source-anchored content. The model-based path
  exists but isn't wired to a local model yet (the swap point above).
- **No image generation.** Image content is recorded as a placeholder
  during ingest. Real diffusion is out of scope.
