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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response as FResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import auth_middleware, mint_token, check_password

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
from deckengine.org import list_orgs, load_org, to_dict as org_to_dict, OrgError

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")
UPLOADS  = os.path.join(ROOT, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

app = FastAPI(title="DeckEngine")

# CORS — defaults to * for dev; in prod set CORS_ORIGINS to the Netlify URL
# (comma-separated allowed). Same env var name as the rest of the portfolio.
_cors_raw = os.environ.get("CORS_ORIGINS", "*").strip()
_cors_origins = ["*"] if _cors_raw == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"], allow_headers=["*"],
)

# Bearer-token auth — gated by BU_AUTH_* env vars (same pattern across all
# portfolio projects, so the shared secret means one login works everywhere).
app.middleware("http")(auth_middleware)


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


class StoryboardViewReq(BaseModel):
    outline: list[dict] = []
    audience: str | None = None
    mode: str | None = None


class WorkspaceGenReq(BaseModel):
    feature: str = "create"
    prompt: str = ""
    audience: str | None = None
    current: dict | None = None
    palette: str | None = None
    fileNames: list[str] = []


# ---- API routes ----------------------------------------------------------

@app.get("/api/orgs")
def api_orgs():
    """Every org profile this install knows about (slug + name only)."""
    return {"orgs": list_orgs()}


@app.get("/api/orgs/{slug}")
def api_org(slug: str):
    """One org profile: its scoping questions, narrative arc and style rules."""
    try:
        return org_to_dict(load_org(slug))
    except OrgError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


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
    """Upload a .pptx OR .pdf, get IR back. Content-only — geometry is
    discarded by design (R7.2.2). The engine re-resolves layout
    downstream. Format dispatched by filename extension."""
    from deckengine.ingest import ingest_bytes
    raw = await file.read()
    try:
        deck = ingest_bytes(raw, filename=file.filename or "",
                            uploads_dir=UPLOADS, url_prefix="/uploads")
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"failed to ingest: {e}"})
    return deck_to_dict(deck)


@app.post("/api/peek")
async def api_peek(file: UploadFile = File(...)):
    """Lightweight pre-extraction metadata. Returns slide/page count,
    titles, image / chart counts, and file size — enough for the UI to
    show "what's in this deck" before the user commits to a mode +
    extract. Handles .pptx and .pdf. Does NOT persist any image blobs."""
    raw = await file.read()
    size = len(raw)
    name = (file.filename or "").lower()

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io as _io
            reader = PdfReader(_io.BytesIO(raw))
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"failed to read pdf: {e}"})
        slides = []
        for i, page in enumerate(reader.pages):
            try:
                txt = (page.extract_text() or "").strip()
                first_line = next((l.strip() for l in txt.splitlines() if l.strip()), "")
            except Exception:
                first_line = ""
            slides.append({"index": i, "title": first_line or f"Page {i + 1}"})
        return {
            "filename": file.filename,
            "size_bytes": size,
            "slide_count": len(slides),
            "image_count": 0,   # pypdf can pull these but skipped for peek
            "chart_count": 0,
            "slides": slides,
        }

    try:
        from pptx import Presentation
        import io as _io
        prs = Presentation(_io.BytesIO(raw))
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"failed to read pptx: {e}"})
    slides = []
    image_count = 0
    chart_count = 0
    for i, sl in enumerate(prs.slides):
        title = ""
        for sh in sl.shapes:
            try:
                ph = sh.placeholder_format
            except Exception:
                ph = None
            if ph is not None and ph.idx == 0 and sh.has_text_frame:
                title = sh.text_frame.text.split("\n", 1)[0].strip()
                break
        if not title:
            for sh in sl.shapes:
                if sh.has_text_frame and sh.text_frame.text.strip():
                    title = sh.text_frame.text.split("\n", 1)[0].strip()
                    break
        for sh in sl.shapes:
            try:
                if getattr(sh, "shape_type", None) == 13:  # PICTURE
                    image_count += 1
                if getattr(sh, "has_chart", False):
                    chart_count += 1
            except Exception:
                pass
        slides.append({"index": i, "title": title or f"Slide {i + 1}"})
    return {
        "filename": file.filename,
        "size_bytes": size,
        "slide_count": len(slides),
        "image_count": image_count,
        "chart_count": chart_count,
        "slides": slides,
    }


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


@app.post("/api/workspace_generate")
def api_workspace_generate(req: WorkspaceGenReq):
    """Real backend for the pptgpt workspace UI's Create/Data/Refine/Condense
    composer (ws-app.jsx's `aiGenerate`). Same availability/error shape as
    /api/narrative so the frontend adapter can treat them the same way —
    the client falls back to its own canned generator when unavailable."""
    from deckengine import narrative as narr_mod, workspace_gen
    info = narr_mod.backend_info()
    if not narr_mod.available():
        if info.get("backend") == "ollama":
            reason = (f"Ollama at {info.get('host')} unreachable. "
                      "Run `ollama serve` and `ollama pull {model}`.".format(model=info.get("model")))
        else:
            reason = ("No generation model configured. Set ANTHROPIC_API_KEY, "
                      "or set DECKENGINE_NARRATIVE_BACKEND=ollama and run a local model.")
        return {"available": False, "reason": reason, **info}
    result = workspace_gen.generate_slide(
        feature=req.feature, prompt=req.prompt, audience=req.audience,
        current=req.current, palette=req.palette, file_names=req.fileNames,
    )
    if result is None:
        return {"available": False, "reason": "Model call failed; check server logs.", **info}
    return {"available": True, **info, "slide": result}


@app.post("/api/storyboard_view")
def api_storyboard_view(req: StoryboardViewReq):
    """Unified payload for the new storyboard page.

    Returns one bundle: outline (with role tags), threads, suggestions,
    spine, tensions, engine, stats. Single fetch per outline edit — the
    page never has to coordinate multiple endpoints.

    Cascade lives inside threadmap+narrative; this endpoint just shapes
    the response to what the design's JSX expects.
    """
    from deckengine.storyboard_view import compute_storyboard_view
    return compute_storyboard_view(
        req.outline or [], audience=req.audience, mode=req.mode,
    )


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


@app.post("/api/render_uploaded")
async def api_render_uploaded(file: UploadFile = File(...), palette: str = "clean"):
    """Upload .pptx → re-render via the engine in one shot. Images and
    charts extracted by ingest are re-placed by the layout engine in its
    own style. Returns the rendered .pptx as a download."""
    from deckengine.ingest import ingest_pptx_bytes
    raw = await file.read()
    try:
        deck = ingest_pptx_bytes(raw, uploads_dir=UPLOADS, url_prefix="/uploads")
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"failed to ingest: {e}"})
    theme = PALETTES.get(palette, Theme())
    resolved = [layout_resolve(s, theme) for s in deck.slides]
    fd, out = tempfile.mkstemp(prefix="deckengine-up-", suffix=".pptx")
    os.close(fd)
    render_deck(resolved, out)
    return FileResponse(
        out, filename="reengineered.pptx",
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


# ---- auth ----------------------------------------------------------------

class LoginReq(BaseModel):
    username: str = ""
    password: str = ""


@app.post("/login")
def login(req: LoginReq):
    """Issue a bearer token for valid credentials.

    Shared BU_AUTH_* env vars across portfolio projects mean the SAME
    username/password works on every project's Space. Tokens are not
    portable across projects unless BU_AUTH_SECRET is also shared."""
    if not check_password(req.username, req.password):
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)
    return {"token": mint_token(req.username), "user": req.username}


# ---- static frontend -----------------------------------------------------
#
# Layout:
#   /            -> the v3 landing page (frontend/v2-assets/landing.html)
#   /storyboard  -> the new storyboard page with thread tracks
#   /workbench   -> the new three-panel workbench
#   /canvas      -> the original single-slide canvas (kept for back-compat)
#   /workbench-v1 -> the previous workbench we built today (kept for diff)
#
# All asset files (css/jsx/js) are served from the `frontend/` directory.
# The v2 assets live at `frontend/v2-assets/`; the catch-all serves both.

V2_ASSETS = os.path.join(FRONTEND, "v2-assets")


def _serve_html(relpath: str) -> HTMLResponse:
    target = os.path.join(FRONTEND, relpath)
    with open(target, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/", response_class=HTMLResponse)
def index():
    """v3 landing (scrollytelling marketing page)."""
    return _serve_html("v2-assets/landing.html")


@app.get("/setup", response_class=HTMLResponse)
@app.get("/setup/", response_class=HTMLResponse)
def setup():
    """Step 02 · pick the goal. Audience + mode + stakes picker."""
    return _serve_html("v2-assets/setup.html")


@app.get("/storyboard")
@app.get("/storyboard/")
def storyboard_redirect():
    """Legacy /storyboard kept duplicating the workbench's step 03 with
    different demo data, which confused users about which one was real.
    There is now ONE storyboard — phase 3 of /workbench."""
    return RedirectResponse(url="/workbench", status_code=308)


@app.get("/workbench", response_class=HTMLResponse)
@app.get("/workbench/", response_class=HTMLResponse)
def workbench():
    """The new three-panel workbench."""
    return _serve_html("v2-assets/workbench-v2.html")


@app.get("/canvas", response_class=HTMLResponse)
@app.get("/canvas/", response_class=HTMLResponse)
def canvas():
    """Back-compat: the original single-slide canvas (v1)."""
    return _serve_html("index.html")


@app.get("/workbench-v1", response_class=HTMLResponse)
@app.get("/workbench-v1/", response_class=HTMLResponse)
def workbench_v1():
    """Back-compat: the workbench we built earlier today, kept for diff."""
    return _serve_html("workbench.html")


@app.get("/workspace", response_class=HTMLResponse)
@app.get("/workspace/", response_class=HTMLResponse)
def workspace():
    """The unified Create/Data/Refine/Condense workspace, wired to a real
    generation backend via workspace-backend.js."""
    return _serve_html("workspace.html")


# Asset mounts + catch-all
if os.path.isdir(FRONTEND):
    app.mount("/frontend", StaticFiles(directory=FRONTEND), name="frontend")
    app.mount("/assets",   StaticFiles(directory=FRONTEND), name="assets")
    if os.path.isdir(V2_ASSETS):
        app.mount("/v2-assets", StaticFiles(directory=V2_ASSETS), name="v2-assets")
    # Mount /uploads so ingest-extracted images are reachable via the
    # paths the IR carries (e.g. /uploads/<deck-id>/slide00_00.png).
    app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

    @app.get("/{filename:path}")
    def root_assets(filename: str):
        # Don't shadow API or health
        if filename.startswith(("api/", "health")):
            return Response(status_code=404)
        # Try v2-assets first so the new pages' relative `<script src="...">`
        # work without rewriting their HTML to add a path prefix.
        for base in (V2_ASSETS, FRONTEND):
            target = os.path.normpath(os.path.join(base, filename))
            if not target.startswith(base):
                continue
            if os.path.isfile(target):
                return FileResponse(target)
        return Response(status_code=404)
