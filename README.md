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

## Architecture

```
rough text ──(local model)──► Slide IR ──(ambiguity detect)──► taste questions
                                  │                                   │
                                  │            user answers ──────────┘
                                  ▼
                          layout engine (deterministic)
                                  │
                    ┌─────────────┼─────────────┐   ← one IR, three themes
                  bold          clean          warm    = three "directions"
                    └─────────────┼─────────────┘       for free
                                  ▼
                          .pptx renderer (dumb)
```

- `deckengine/ir.py` — content/intent/theme dataclasses. No geometry.
- `deckengine/layout.py` — **the contribution.** IR + theme → resolved boxes
  (inches). Pure, testable. Layout *rules* are explicit constraints.
- `deckengine/render.py` — boxes → `.pptx`. Deliberately judgment-free.
- `deckengine/ambiguity.py` — detects forks → taste questions with `region`.
- `server.py` — FastAPI; speaks the canvas data contract. Offline.
- `tests/test_layout.py` — constraint tests: margins, no-overlap, hero
  contrast, even distribution. **Layout quality is measured, not eyeballed.**

## Why the tests matter

`good layout` is usually treated as taste. Here it's invariants:
margins are a hard floor, stat columns never overlap, the hero stat is
≥1.3× its neighbors, title is ≥2× the labels. Refactor the engine freely;
the invariants catch regressions. This is what makes the approach defensible.

## Run

```bash
pip install -r requirements.txt
python tests/test_layout.py          # 6/6 should pass
uvicorn server:app --reload          # offline API on :8000
```

## The UI contract (for the Claude Design canvas)

UI → backend: `{ rawContent, answers }`
backend → UI: `{ slideIR, questions:[{id,region,text,options}], directions:[{key,label,previewSpec}] }`

`previewSpec` carries fully-resolved geometry as **percentage boxes** so the
canvas renders verbatim and invents nothing. `region` ∈ {top,bottom,left,right}
drives where a question card anchors and which way it drifts when answered.

> Integration note: if the Claude Design export defines a *different*
> `previewSpec` shape, the engine conforms to it — `preview_spec()` in
> `server.py` is the single place to change. The contract serves the UI.

## Local model

`parse_to_ir()` in `server.py` is a regex stand-in for a local LLM. Swap it
for an Ollama / LM Studio call that emits the IR JSON. Everything downstream
is unchanged. That's the point of the separation.

## Honest limitations (v1)

- **One archetype.** Only `stat_callout` renders end-to-end. `icon_rows`,
  `two_column_stats`, `bullets_plain` are detected and chosen but not yet
  resolved/rendered. Each is ~one resolver function in `layout.py`.
- **Directions = palettes only.** Real "directions" should also vary
  *structure*, not just color. That's the next research-flavored step.
- **No images/charts.** Offline image-gen is heavy; plan is icon + shape
  composition first, real diffusion later (out of scope).
- **Ambiguity rules are hand-written.** The principled version ("ask when two
  archetypes score within ε") is unbuilt and is the most publishable piece.
- **No font embedding.** Renders assume Georgia/Calibri are installed.
```
