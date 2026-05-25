"""
FastAPI backend — speaks the frontend contract from `frontend/types.md`.

Endpoints
---------
  POST /api/backend       mirror of `window.mockBackend(req)`.
  POST /api/storyboard    mirror of `window.extractStoryboard(req)`.
  POST /api/critique      mirror of `window.generateCritique(req)`.
  POST /api/render        { slides: SlideSpec[] } -> .pptx download.
  POST /api/plot          { block: PlotBlock, params?: dict } -> PNG.

  --- IR-engine path (the project's stated contribution) ---
  POST /api/design        { rawContent, answers? } -> { slideIR, questions, directions }
                          using parse_to_ir → ambiguity → layout.resolve.
  POST /api/ir            { rawContent } -> { deck, slides, intent } — peek at the IR.
  POST /api/ingest        upload a .pptx -> Deck IR (content-only).
  POST /api/render_ir     { rawContent, palette? } -> .pptx rendered via the engine.
  POST /api/thread_map    { outline, recommendations?, acceptedIds?, mode? }
                          -> before/after concept-thread visualization data.
                          Cascade: narrative-LLM → semantic-embeddings → lexical.
  POST /api/narrative     { outline, audience?, mode? }
                          -> structured narrative analysis from the LLM:
                             spine (one sentence), arc shape, orphans with
                             reasons, gaps with bridge suggestions, tensions
                             (contradictions, redundancies, unsupported), and
                             concrete recommendations. Requires ANTHROPIC_API_KEY
                             (or a Gemma swap in narrative._llm_call).

  GET  /health

Static
------
  GET  /                  serves `frontend/index.html`.
  GET  /workbench         serves `frontend/workbench.html`.
  GET  /frontend/*        serves the rest of `frontend/`.

Offline. No outbound calls. Same shapes as the mock so the UI swap is
literally `mockBackend.js` -> `fetch('/api/backend', ...)`.
"""
from __future__ import annotations
import os
import io
import tempfile
from typing import Any

from fastapi import FastAPI, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response as FResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deckengine.synth import backend as synth_backend
from deckengine.storyboard import extract_storyboard, generate_critique
from deckengine.spec_render import render_specs, _render_plot_png
from deckengine.parse import parse_to_ir, parse_deck_to_ir
from deckengine.ir import PALETTES, Theme
from deckengine.layout import resolve as layout_resolve
from deckengine.render import render_deck
from deckengine.boundary import (
    design, design_directions, design_deck_directions,
    deck_to_dict, ir_slide_to_dict, resolved_to_spec,
)
from deckengine.ambiguity import detect as detect_questions, to_dict as q_to_dict

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")

app = FastAPI(title="DeckEngine")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---- request models (loose: passthrough dicts) ---------------------------

class BackendReq(BaseModel):
    rawContent: str = ""
    mode: str = "draft"
    answers: dict = {}
    outline: list[dict] | None = None
    wantsLiveDirections: bool | None = None


class StoryboardReq(BaseModel):
    text: str = ""
    mode: str = "draft"
    audience: str | None = None
    targetCount: int | None = None


class CritiqueReq(BaseModel):
    audience: str = "exec"
    mode: str = "draft"
    outline: list[dict] = []


class RenderReq(BaseModel):
    slides: list[dict]


class PlotReq(BaseModel):
    block: dict
    params: dict | None = None


class DesignReq(BaseModel):
    rawContent: str = ""
    answers: dict = {}
    palette: str | None = None        # 'bold' | 'clean' | 'warm' | None
    archetype: str | None = None      # explicit override (advanced)


class RenderIrReq(BaseModel):
    rawContent: str = ""
    palette: str | None = None
    archetype: str | None = None


class RenderDirectionReq(BaseModel):
    """Render an entire backend direction (its slides[] array) to .pptx."""
    direction: dict
    filename: str | None = None


class ThreadMapReq(BaseModel):
    outline: list[dict] = []
    recommendations: list[dict] | None = None
    acceptedIds: list[str] | None = None
    mode: str = "potential"     # 'potential' (all advisories) | 'accepted'


class NarrativeReq(BaseModel):
    outline: list[dict] = []
    audience: str | None = None
    mode: str | None = None


# ---- API routes ----------------------------------------------------------

@app.post("/api/backend")
def api_backend(req: BackendReq):
    return synth_backend(req.model_dump())


@app.post("/api/storyboard")
def api_storyboard(req: StoryboardReq):
    return extract_storyboard(req.model_dump())


@app.post("/api/critique")
def api_critique(req: CritiqueReq):
    return generate_critique(req.model_dump())


@app.post("/api/render")
def api_render(req: RenderReq):
    fd, out = tempfile.mkstemp(prefix="deckengine-", suffix=".pptx")
    os.close(fd)
    render_specs(req.slides, out)
    return FileResponse(
        out, filename="deck.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.post("/api/plot")
def api_plot(req: PlotReq):
    """Plot-only render. Merges `params` onto each curve's *own* defaults
    (only keys the curve already declares); returns PNG."""
    block = dict(req.block or {})
    overrides = req.params or {}
    if overrides:
        curves = []
        for curve in block.get("curves") or []:
            base = dict(curve.get("params") or {})
            # ONLY override keys this curve actually uses; prevents cross-curve
            # contamination (e.g. damped's gamma leaking into a sine curve).
            for k, v in overrides.items():
                if k in base:
                    base[k] = v
            curves.append({**curve, "params": base})
        block["curves"] = curves
    png = _render_plot_png(block)
    if not png:
        return Response(status_code=503, content="matplotlib not installed")
    return Response(content=png, media_type="image/png")


# ---- IR-engine path ------------------------------------------------------

@app.post("/api/design")
def api_design(req: DesignReq):
    """The real IR-engine path. Same shape as /api/backend so the UI can use
    it interchangeably. Goes through parse_to_ir → ambiguity → layout.resolve.

    Unlike /api/backend (which routes through `synth.py` and emits SlideSpec
    directly), this route exercises §0's content/layout/theme separation."""
    slide = parse_to_ir(req.rawContent or "")
    questions = [q_to_dict(q) for q in detect_questions(slide, req.answers or {})]

    palette_key = req.palette
    if palette_key and palette_key in PALETTES:
        theme = PALETTES[palette_key]
    else:
        theme = Theme()

    # archetype override flows from answers when needed
    archetype = req.archetype
    if not archetype:
        # ambiguity.choose_archetype takes answers into account
        from deckengine.ambiguity import choose_archetype
        archetype = choose_archetype(slide, req.answers or {})

    slide_ir_spec = design(slide, theme, archetype=archetype)
    directions = design_directions(slide) if not questions else []

    return {
        "slideIR": slide_ir_spec,
        "ir": ir_slide_to_dict(slide),
        "questions": questions,
        "directions": directions,
        "archetypeChosen": archetype,
    }


@app.post("/api/ir")
def api_ir(req: DesignReq):
    """Peek at the IR for raw text. Useful for debugging and for the
    outline editor (CLAUDE.md feature B)."""
    deck = parse_deck_to_ir(req.rawContent or "")
    return deck_to_dict(deck)


@app.post("/api/ingest")
async def api_ingest(file: UploadFile = File(...)):
    """Upload a .pptx, get IR back. Content-only — geometry is discarded by
    design (R7.2.2). The engine re-resolves layout downstream."""
    from deckengine.ingest import ingest_pptx_bytes
    raw = await file.read()
    try:
        deck = ingest_pptx_bytes(raw)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"failed to ingest: {e}"})
    return deck_to_dict(deck)


@app.post("/api/narrative")
def api_narrative(req: NarrativeReq):
    """Direct access to the LLM narrative analysis.

    Returns the structured narrative dict (spine, arc, orphans-with-reasons,
    gaps, tensions, recommendations) or {'available': False, ...} if no
    model is configured. Cascades to None — the UI can then call /api/thread_map
    which will fall back to semantic/lexical itself.
    """
    from deckengine import narrative as narr_mod
    info = narr_mod.backend_info()
    if not narr_mod.available():
        if info.get("backend") == "ollama":
            reason = (f"Ollama at {info.get('host')} unreachable. "
                      "Run `ollama serve` and `ollama pull {model}`.".format(model=info.get("model")))
        else:
            reason = ("No narrative model configured. Set ANTHROPIC_API_KEY, "
                      "or set DECKENGINE_NARRATIVE_BACKEND=ollama and run a local model.")
        return {"available": False, "reason": reason, **info}
    result = narr_mod.analyze_narrative(
        req.outline or [], audience=req.audience, mode=req.mode,
    )
    if result is None:
        return {"available": False, "reason": "Model call failed; check server logs.", **info}
    return {"available": True, **info, **result}


@app.post("/api/thread_map")
def api_thread_map(req: ThreadMapReq):
    """Compute the before/after thread visualization for an outline.

    Returns {before, after, diff, applied, mode} where each side carries a
    graph (nodes + edges + orphans + spine + gaps) and a ribbons list. The
    UI renders the data; we never emit pixels or colors here.
    """
    from deckengine.threadmap import compute_thread_map
    return compute_thread_map(
        req.outline or [],
        recommendations=req.recommendations,
        accepted_ids=req.acceptedIds,
        mode=req.mode or "potential",
    )


@app.post("/api/render_direction")
def api_render_direction(req: RenderDirectionReq):
    """Render an entire backend Direction (its slides[] array) as a .pptx.

    This is the artifact button the UI shows next to a Direction — turn the
    on-screen result into something the user can open in PowerPoint.
    """
    direction = req.direction or {}
    slides = direction.get("slides") or ([direction.get("previewSpec")] if direction.get("previewSpec") else [])
    if not slides:
        return Response(status_code=400, content="direction has no slides")
    fd, out = tempfile.mkstemp(prefix="deckengine-dir-", suffix=".pptx")
    os.close(fd)
    render_specs(slides, out)
    fname = req.filename or f"deck-{direction.get('key', 'direction')}.pptx"
    return FileResponse(
        out, filename=fname,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.post("/api/render_ir")
def api_render_ir(req: RenderIrReq):
    """Raw text -> .pptx via the IR engine. The architecturally correct
    export path: parse → resolve → render. Output is openable in PowerPoint."""
    deck = parse_deck_to_ir(req.rawContent or "")
    theme = PALETTES.get(req.palette or "", Theme())
    resolved = [layout_resolve(s, theme, archetype=req.archetype) for s in deck.slides]
    fd, out = tempfile.mkstemp(prefix="deckengine-ir-", suffix=".pptx")
    os.close(fd)
    render_deck(resolved, out)
    return FileResponse(
        out, filename="deck.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.get("/health")
def health():
    return {"ok": True}


# ---- static frontend -----------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(FRONTEND, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/workbench", response_class=HTMLResponse)
@app.get("/workbench/", response_class=HTMLResponse)
def workbench():
    with open(os.path.join(FRONTEND, "workbench.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# All the JSX/CSS/JS assets live under /frontend/* so the HTML's relative
# `<script src="mockBackend.js">` and `<link href="styles.css">` resolve.
# We also mount the same dir at root so those bare paths work.
if os.path.isdir(FRONTEND):
    app.mount("/frontend", StaticFiles(directory=FRONTEND), name="frontend")
    app.mount("/assets",   StaticFiles(directory=FRONTEND), name="assets")
    # Catch-all for relative asset paths from index.html / workbench.html
    # (e.g. `styles.css`, `mockBackend.js`) by serving them at the root.
    @app.get("/{filename:path}")
    def root_assets(filename: str):
        # Don't shadow /api or /health
        if filename.startswith(("api/", "health")):
            return Response(status_code=404)
        target = os.path.normpath(os.path.join(FRONTEND, filename))
        if not target.startswith(FRONTEND):
            return Response(status_code=403)
        if os.path.isfile(target):
            return FileResponse(target)
        return Response(status_code=404)
