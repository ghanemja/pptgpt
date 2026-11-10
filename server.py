"""
FastAPI backend — speaks the frontend contract from `frontend/types.md`.

Endpoints
---------
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
  Pages and assets are served flat from `frontend/` — see the route list
  at the "static frontend" section near the end of this file.

Offline. No outbound calls.
"""
from __future__ import annotations
import os
import re
import io
import tempfile
from typing import Any

from fastapi import FastAPI, HTTPException, Response, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response as FResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import auth_middleware, mint_token, check_password

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
from deckengine.preview import slide_png, native_png, available as preview_available
from deckengine import kit as kitmod
from deckengine.kit import KitError
from deckengine.kit_ingest import learn as kit_learn, norms as kit_norms
from deckengine.coach import (
    list_personas, load_persona, critique_slide, review_deck, LENSES as COACH_LENSES,
    CoachError, save_persona, delete_persona, parse_criteria, criteria_for, criterion_dict,
)
from deckengine.scorecard import score_panel
from deckengine.template import (
    save_template, load_template, list_templates, delete_template,
    template_path, to_dict as tpl_to_dict, TemplateError,
    backdrop_png, backdrop_available,
)

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

class StoryboardReq(BaseModel):
    text: str = ""
    mode: str = "draft"
    audience: str | None = None
    targetCount: int | None = None


class CritiqueReq(BaseModel):
    audience: str = "exec"
    mode: str = "draft"
    outline: list[dict] = []


class CritiqueSlideReq(BaseModel):
    slide: dict
    coach: str = "board-chair"
    next: dict | None = None        # the following slide, for the handoff lens
    org: str | None = None          # judge by this company's learned norms


class CritiqueDeckReq(BaseModel):
    slides: list[dict] = []
    coach: str = "board-chair"
    overrides: dict | None = None   # {strictness, lenses} tuned for this run
    org: str | None = None          # judge by this company's learned norms


class ScorecardReq(BaseModel):
    slides: list[dict] = []
    coaches: list[str] = ["board-chair"]   # the panel
    audience: str = "exec"                 # the room the deck is for
    purpose: str = ""                      # the decision it asks for (from scoping)
    org: str | None = None                 # house norms and criteria


class SaveCoachReq(BaseModel):
    name: str
    basedOn: str = "board-chair"    # the persona it was tuned from (its voice)
    strictness: str | None = None
    lenses: dict | None = None      # {lens or kit:<id>: weight}; absent = off
    tagline: str = ""


class PreviewReq(BaseModel):
    spec: dict | None = None        # ONE resolved SlideSpec (engine-placed)
    slide: dict | None = None       # ONE workspace slide (cast into the template)
    templateId: str | None = None
    org: str | None = None          # the company: layout preferences + assets


class RenderReq(BaseModel):
    slides: list[dict]              # resolved SlideSpecs, or workspace slides
    templateId: str | None = None   # render onto this uploaded template
    native: bool = False            # cast into the template's own layouts
    org: str | None = None          # the company: layout preferences + assets


class DiagramLayoutReq(BaseModel):
    diagram: dict                   # content only: kind, nodes, edges (no geometry)
    w: float                        # the box, in the caller's pixels
    h: float
    slideW: float = 720             # how many of those pixels span the 13.333in slide
    colors: dict | None = None      # the slide's {bg, accent, ink, highlight}; roles come back


class DiagramExtractReq(BaseModel):
    text: str
    model: bool = False             # let the model read implied structure (grounded)


class KitCreateReq(BaseModel):
    name: str
    description: str = ""


class KitImportReq(BaseModel):
    path: str
    mode: str = "copy"              # copy | link
    part: str | None = None         # examples | assets | template | ... | None = auto


class KitVoiceReq(BaseModel):
    text: str


class KitRulesReq(BaseModel):
    add: list[str] = []


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
    engine: str = "auto"        # 'auto' (LLM first) | 'fast' (embeddings first)
    sides: str = "both"         # 'both' | 'before' (skip the simulated side)


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
    org: str | None = None          # write in this company's house style


# ---- API routes ----------------------------------------------------------

@app.post("/api/preview_png")
def api_preview_png(req: PreviewReq):
    """One slide, rendered exactly as it exports.

    The HTML preview can only use fonts the viewer has installed, so a deck
    on a template built in Bookman Old Style silently previews in something
    else. This renders the real .pptx through LibreOffice and returns the
    image, so the preview and the file agree. 503 when LibreOffice is absent
    — the UI keeps its HTML preview rather than showing nothing.
    """
    # With a template, the slide is CAST into that template's own layouts, so
    # its positions, type ramp and bullet styling are the template's. Without
    # one, the engine's own placement is rendered.
    if req.slide is not None and req.templateId:
        path = native_png(req.slide, req.templateId, org=req.org)
    elif req.spec is not None:
        path = slide_png(req.spec, req.templateId, org=req.org)
    else:
        return JSONResponse({"error": "need a spec or a slide"}, status_code=400)
    if not path:
        reason = ("LibreOffice is not installed on the server"
                  if not preview_available() else "could not render this slide")
        return JSONResponse({"error": reason}, status_code=503)
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=600"})


# ---- company kits ----------------------------------------------------------
#
# A kit is a folder under kits/<slug>/. Everything below reads or writes that
# folder and nothing else, so uploading here, pointing at a folder, and
# dragging files in by hand all end up identical. See kits/README.md.

def _kit_criteria(org: str | None):
    """A company's own review criteria, parsed; None when it has none.

    Raises CoachError/KitError on a criteria file we will not use, so the
    person who wrote it hears what is wrong instead of a silent fallback.
    """
    if not org:
        return None
    raw = kitmod.criteria_raw(org)
    return parse_criteria(raw) if raw is not None else None


def _kit_norms(org: str | None):
    if not org:
        return None
    try:
        return kit_norms(org)
    except Exception:
        return None


def _local_only(request: Request):
    """Refuse a request that did not come from this machine.

    Reading an arbitrary folder, or opening one in the file manager, is
    exactly right for someone running pptgpt on their own laptop and exactly
    wrong for anyone reaching this server over a network. Those two routes
    answer only to localhost, whatever the auth settings say.
    """
    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        return JSONResponse({"error": "only available on this machine (localhost)"},
                            status_code=403)
    return None


def _kit_error(e: Exception):
    msg = str(e)
    status = 404 if msg.startswith("no kit") else 400
    return JSONResponse({"error": msg}, status_code=status)


@app.get("/api/kits")
def api_kits():
    """Every company kit on this machine."""
    return {"kits": kitmod.list_kits(), "root": kitmod.KITS_DIR}


@app.post("/api/kits")
def api_kit_create(req: KitCreateReq):
    """A new kit: the folder structure plus starter files to edit."""
    try:
        slug = kitmod.create_kit(req.name, req.description)
        return kitmod.scan(slug)
    except KitError as e:
        return _kit_error(e)


@app.get("/api/kits/{slug}")
def api_kit(slug: str):
    """The kit's state, re-read from disk every time — so a file dropped in
    by hand shows up the next time the screen is opened."""
    try:
        return kitmod.scan(slug)
    except KitError as e:
        return _kit_error(e)


@app.post("/api/kits/{slug}/upload")
async def api_kit_upload(slug: str, files: list[UploadFile] = File(...),
                         part: str | None = Form(None)):
    """Files from the browser, sorted into the kit by type (or by `part`)."""
    try:
        payload = [(f.filename or "file", await f.read()) for f in files]
        report = kitmod.add_files(slug, payload, part or None)
        return {**report, "kit": kitmod.scan(slug)}
    except KitError as e:
        return _kit_error(e)


@app.post("/api/kits/{slug}/import")
def api_kit_import(slug: str, req: KitImportReq, request: Request):
    """Bring in a folder on this machine — copied in, or linked in place."""
    refused = _local_only(request)
    if refused:
        return refused
    try:
        report = kitmod.import_path(slug, req.path, mode=req.mode, part=req.part)
        return {**report, "kit": kitmod.scan(slug)}
    except KitError as e:
        return _kit_error(e)


@app.post("/api/kits/{slug}/reveal")
def api_kit_reveal(slug: str, request: Request):
    """Open the kit's folder in Finder / Explorer, for dragging files in."""
    refused = _local_only(request)
    if refused:
        return refused
    try:
        path = kitmod.kit_dir(slug)
        if not os.path.isdir(path):
            raise KitError(f"no kit {slug!r}")
    except KitError as e:
        return _kit_error(e)
    import subprocess
    import sys as _sys
    opener = ("open" if _sys.platform == "darwin" else
              "explorer" if _sys.platform.startswith("win") else "xdg-open")
    try:
        subprocess.Popen([opener, path])
        return {"opened": path}
    except OSError as e:
        return JSONResponse({"error": f"could not open the folder: {e}", "path": path},
                            status_code=500)


@app.post("/api/kits/{slug}/learn")
def api_kit_learn(slug: str):
    """Read the example decks and write what they teach to learned.json."""
    try:
        if not kitmod.example_files(slug):
            return JSONResponse({"error": "add some example decks first"}, status_code=400)
        result = kit_learn(slug)
        return {"learned": result, "kit": kitmod.scan(slug)}
    except KitError as e:
        return _kit_error(e)


@app.put("/api/kits/{slug}/voice")
def api_kit_voice(slug: str, req: KitVoiceReq):
    try:
        kitmod.set_voice(slug, req.text)
        return kitmod.scan(slug)
    except KitError as e:
        return _kit_error(e)


@app.post("/api/kits/{slug}/rules")
def api_kit_rules(slug: str, req: KitRulesReq):
    """Add house rules to the kit's profile — typically the ones learning
    suggested, after a person has decided they are true."""
    import json as _json
    try:
        path = os.path.join(kitmod.kit_dir(slug), "profile.json")
        if not os.path.isfile(path):
            raise KitError("this kit has no profile.json")
        with open(path, "r", encoding="utf-8") as fh:
            prof = _json.load(fh)
        rules = prof.setdefault("style", {}).setdefault("rules", [])
        for r in req.add:
            r = str(r).strip()
            if r and r not in rules:
                rules.append(r)
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(prof, fh, indent=2)
            fh.write("\n")
        return kitmod.scan(slug)
    except KitError as e:
        return _kit_error(e)


@app.get("/api/kits/{slug}/assets")
def api_kit_assets(slug: str, q: str = "", limit: int = 48):
    try:
        return {"assets": kitmod.search_assets(slug, q, limit=max(1, min(limit, 200)))}
    except KitError as e:
        return _kit_error(e)


@app.get("/api/kits/{slug}/asset")
def api_kit_asset(slug: str, file: str):
    """One asset file, for the library's thumbnails and the slide preview."""
    try:
        path = kitmod.asset_path(slug, file)
    except KitError as e:
        return _kit_error(e)
    media = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
             ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    return FileResponse(path, media_type=media.get(os.path.splitext(path)[1].lower(),
                                                   "application/octet-stream"),
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/coaches")
def api_coaches():
    """The critic personas this install ships, then the ones people saved."""
    return {"coaches": list_personas()}


@app.post("/api/coaches")
def api_save_coach(req: SaveCoachReq):
    """Keep a tuned reviewer under a name, to pick again later."""
    try:
        saved = save_persona(req.name, req.basedOn, strictness=req.strictness,
                             lenses=req.lenses, tagline=req.tagline)
    except CoachError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"coach": saved, "coaches": list_personas()}


@app.delete("/api/coaches/{slug}")
def api_delete_coach(slug: str):
    """Forget a saved reviewer. Shipped personas stay."""
    try:
        delete_persona(slug)
    except CoachError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"coaches": list_personas()}


@app.post("/api/critique_slide")
def api_critique_slide(req: CritiqueSlideReq):
    """One slide, read by one persona.

    Deterministic: the same slide and persona always produce the same notes,
    so a note is a property of the slide rather than of a sampling seed.
    """
    try:
        persona = load_persona(req.coach)
    except CoachError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    norms = _kit_norms(req.org)
    try:
        crits = {c.id: c for c in (_kit_criteria(req.org) or [])}
    except (CoachError, KitError):
        crits = {}                  # the review phase reports a bad file; the coach just reads
    return critique_slide(req.slide, persona,
                          context={"next": req.next, "norms": norms, "criteria": crits})


@app.post("/api/scorecard")
def api_scorecard(req: ScorecardReq):
    """A panel of reviewers, each scoring the deck by aspect, for this room.

    Cheap and deterministic, so the workspace calls it as the deck is edited
    and shows the scores moving. A reviewer that no longer exists (a saved
    one deleted elsewhere) is reported in `missing` rather than failing the
    whole panel.
    """
    personas, missing = [], []
    for slug in req.coaches[:8]:
        try:
            personas.append(load_persona(slug))
        except CoachError:
            missing.append(slug)
    try:
        crits = _kit_criteria(req.org)
    except (CoachError, KitError):
        crits = None
    out = score_panel(req.slides, personas, audience=req.audience, purpose=req.purpose,
                      norms=_kit_norms(req.org), criteria=crits)
    out["missing"] = missing
    return out


@app.get("/api/coach_lenses")
def api_coach_lenses(org: str | None = None):
    """Every lens a persona can be tuned with, for the review's own UI.

    `criteria` is the same set as the configurator should show it: the
    company kit's own criteria first, in its words, then the rest. A kit
    whose criteria.json we will not use says why in `error`.
    """
    error = None
    try:
        kit = _kit_criteria(org)
    except (CoachError, KitError) as e:
        kit, error = None, f"criteria.json: {e}"
    return {"lenses": sorted(COACH_LENSES),
            "criteria": [criterion_dict(c) for c in criteria_for(kit)],
            "kit": bool(kit), "error": error}


@app.post("/api/critique_deck")
def api_critique_deck(req: CritiqueDeckReq):
    """The whole deck, read by one persona, with deck-level counts."""
    try:
        persona = load_persona(req.coach)
        return review_deck(req.slides, persona, req.overrides, _kit_norms(req.org),
                           _kit_criteria(req.org))
    except KitError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except CoachError as e:
        status = 404 if "no coach" in str(e) or "bad coach" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=status)


@app.get("/api/templates")
def api_templates():
    """Every uploaded slide template, as profiles (theme + constraints)."""
    return {"templates": list_templates()}


@app.post("/api/templates")
async def api_template_upload(file: UploadFile = File(...)):
    """Store a .pptx/.potx and return its profile.

    The template supplies brand and constraints; layout.py still resolves
    every box. See deckengine/template.py for why that keeps §0 intact.
    """
    try:
        data = await file.read()
        prof = save_template(data, file.filename or "template.pptx")
        # Rasterise now: it takes a few seconds, and doing it here means the
        # preview never has to wait for it later.
        backdrop_png(prof.id)
        return tpl_to_dict(prof)
    except TemplateError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/templates/{tid}/backdrop.png")
def api_template_backdrop(tid: str):
    """A PNG of the template's own master — the real backdrop, not a colour.

    Rendered once per template through LibreOffice and cached. Without
    LibreOffice on the host there is no backdrop, and the UI falls back to
    the template's palette rather than pretending.
    """
    try:
        path = backdrop_png(tid)
    except TemplateError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    if not path:
        reason = ("LibreOffice is not installed on the server"
                  if not backdrop_available() else "could not render this template")
        return JSONResponse({"error": reason}, status_code=503)
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/templates/{tid}")
def api_template(tid: str):
    try:
        return tpl_to_dict(load_template(tid))
    except TemplateError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.delete("/api/templates/{tid}")
def api_template_delete(tid: str):
    try:
        delete_template(tid)
        return {"ok": True, "id": tid}
    except TemplateError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except OSError as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
    src = template_path(req.templateId)
    resolver = kitmod.resolver_for(req.org)
    if req.native and src:
        from deckengine.native import render_native
        render_native(req.slides, out, src,
                      preferred_layouts=kitmod.preferred_layouts(req.org),
                      asset_resolver=resolver)
    else:
        render_specs(req.slides, out, template_path=src, asset_resolver=resolver)
    return FileResponse(
        out, filename="deck.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.post("/api/diagram/layout")
def api_diagram_layout(req: DiagramLayoutReq):
    """Diagram content + a box → the engine's geometry, in the caller's px.

    The preview draws this verbatim; the export lays the same content out in
    the same box in inches, so the two agree."""
    from deckengine import diagram as D
    from deckengine.boundary import diagram_to_px
    ppi = req.slideW / 13.333
    try:
        rd = D.resolve(req.diagram, (0.0, 0.0, req.w / ppi, req.h / ppi))
    except D.DiagramError as e:
        raise HTTPException(status_code=422, detail=str(e))
    c = req.colors or {}
    pal = D.palette(c.get("bg") or "#FFFFFF", c.get("accent") or "#1E2761",
                    c.get("ink") or "#11120E", c.get("highlight"))
    return diagram_to_px(rd, ppi, palette=pal)


@app.post("/api/diagram/extract")
def api_diagram_extract(req: DiagramExtractReq):
    """Text → diagram content. Deterministic reading first; with `model`,
    the model may add structure the prose implies, but only labels grounded
    in the text survive."""
    from deckengine import diagram as D
    content = None
    if req.model:
        from deckengine import narrative
        if narrative.available():
            content = D.extract_with_model(req.text, narrative.call)
    if content is None:
        content = D.extract(req.text)
    if content is None:
        return {"diagram": None}
    try:
        return {"diagram": D.to_dict(D.from_dict(content))}
    except D.DiagramError as e:
        return {"diagram": None, "error": str(e)}


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
    """The IR-engine path: parse_to_ir → ambiguity → layout.resolve, returned
    as {slideIR, questions, directions} — the shape `window.mockBackend`
    returns, so a SlideSpec renderer can draw either."""
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
        house=kitmod.house_brief(req.org),
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
        engine=req.engine or "auto",
        sides=req.sides or "both",
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
#   /             -> the landing page (frontend/landing.html)
#   /workbench    -> the five-phase workbench (frontend/workbench-v2.html)
#   /workspace    -> the unified workspace (frontend/workspace.html)
#   /canvas       -> the original single-slide canvas (kept for back-compat)
#   /workbench-v1 -> the previous workbench (kept for diff)
#
# Every page and asset lives flat in `frontend/`, so a page's relative
# `<script src="...">` resolves through the catch-all below.


_ASSET_REF = re.compile(r'\b(src|href)="(?!https?:|//|#|data:|mailto:)([^"?#]+\.(?:jsx|js|css))"')


def _serve_html(relpath: str) -> HTMLResponse:
    """Serve a page, stamping local asset refs with the file's mtime.

    This is the dev server. Its pages are edited constantly, and a browser
    holding a stale .jsx looks exactly like an edit that did not take — the
    request never leaves the cache, so no header on the response can fix it
    after the fact. Stamping the URL changes it, which is the one thing a
    cache cannot ignore. Netlify builds its own pages and sets its own cache
    headers; nothing here affects them.
    """
    target = os.path.join(FRONTEND, relpath)
    page_dir = os.path.dirname(target)
    with open(target, "r", encoding="utf-8") as f:
        html = f.read()

    def stamp(m: "re.Match[str]") -> str:
        attr, path = m.group(1), m.group(2)
        for base in (page_dir, FRONTEND):
            candidate = os.path.normpath(os.path.join(base, path.lstrip("/")))
            if os.path.isfile(candidate):
                return f'{attr}="{path}?v={int(os.path.getmtime(candidate))}"'
        return m.group(0)

    return HTMLResponse(_ASSET_REF.sub(stamp, html))


@app.get("/", response_class=HTMLResponse)
def index():
    """v3 landing (scrollytelling marketing page)."""
    return _serve_html("landing.html")


@app.get("/setup", response_class=HTMLResponse)
@app.get("/setup/", response_class=HTMLResponse)
def setup():
    """Step 02 · pick the goal. Audience + mode + stakes picker."""
    return _serve_html("setup.html")


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
    return _serve_html("workbench-v2.html")


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
    # Mount /uploads so ingest-extracted images are reachable via the
    # paths the IR carries (e.g. /uploads/<deck-id>/slide00_00.png).
    app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

    @app.get("/{filename:path}")
    def root_assets(filename: str):
        # Don't shadow API or health
        if filename.startswith(("api/", "health")):
            return Response(status_code=404)
        target = os.path.normpath(os.path.join(FRONTEND, filename))
        if target.startswith(FRONTEND + os.sep) and os.path.isfile(target):
            # Local dev edits these files constantly, and a stale .jsx in
            # the browser cache looks exactly like a change that did not
            # take. Netlify sets its own (short) cache headers in
            # netlify.toml; this server is only ever the dev server.
            return FileResponse(target, headers={"Cache-Control": "no-store"})
        return Response(status_code=404)
