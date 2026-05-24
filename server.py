"""
FastAPI backend — speaks the frontend contract from `frontend/types.md`.

Endpoints
---------
  POST /api/backend     mirror of `window.mockBackend(req)`.
  POST /api/storyboard  mirror of `window.extractStoryboard(req)`.
  POST /api/critique    mirror of `window.generateCritique(req)`.
  POST /api/render      { slides: SlideSpec[] } -> .pptx download.
  POST /api/plot        { block: PlotBlock, params?: dict } -> PNG.
  GET  /health

Static
------
  GET  /                serves `frontend/index.html`.
  GET  /workbench       serves `frontend/workbench.html`.
  GET  /frontend/*      serves the rest of `frontend/`.

Offline. No outbound calls. Same shapes as the mock so the UI swap is
literally `mockBackend.js` -> `fetch('/api/backend', ...)`.
"""
from __future__ import annotations
import os
import tempfile
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response as FResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deckengine.synth import backend as synth_backend
from deckengine.storyboard import extract_storyboard, generate_critique
from deckengine.spec_render import render_specs, _render_plot_png

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
    """Plot-only render. Merges `params` onto curve defaults, returns PNG."""
    block = dict(req.block or {})
    overrides = req.params or {}
    if overrides:
        curves = []
        for curve in block.get("curves") or []:
            merged = dict(curve.get("params") or {})
            merged.update({k: v for k, v in overrides.items() if k in merged or k in {"A", "omega", "phi", "gamma", "mu", "sigma", "k", "x0", "a", "b", "c", "d"}})
            curves.append({**curve, "params": merged})
        block["curves"] = curves
    png = _render_plot_png(block)
    if not png:
        return Response(status_code=503, content="matplotlib not installed")
    return Response(content=png, media_type="image/png")


@app.get("/health")
def health():
    return {"ok": True}


# ---- static frontend -----------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(FRONTEND, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/workbench", response_class=HTMLResponse)
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
