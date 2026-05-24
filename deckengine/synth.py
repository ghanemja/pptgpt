"""
Slide synthesis — Python port of `frontend/mockBackend.js` slide builders.

This is the "design judgment" layer that was previously mocked in the browser.
It emits SlideSpec dicts that the UI renders verbatim (see `frontend/types.md`).

Contract preserved exactly: same SlideSpec shape, same block fields, same
canvas (1280x720), same question decks, same per-direction archetypes.

§0 holds. Geometry stays out of the IR; this module is the *content-renderer*
that turns raw text + answers into a fully resolved SlideSpec. No clocks, no
randomness; pure functions of (req, answers).
"""
from __future__ import annotations
import math
import re
from typing import Any


# ---- question decks (one per mode) ---------------------------------------

QUESTION_DECKS: dict[str, list[dict]] = {
    "draft": [
        {"id": "q_lead",  "region": "top",    "text": "Lead with the headline, or open with the question it answers?", "options": ["Headline first", "Question first"]},
        {"id": "q_focus", "region": "right",  "text": "Foreground the numbers, or the narrative?",                     "options": ["Numbers up front", "Narrative up front"]},
        {"id": "q_tone",  "region": "left",   "text": "Bold and dark, or clean and light?",                            "options": ["Bold + dark", "Clean + light"]},
        {"id": "q_close", "region": "bottom", "text": "End on a takeaway, or on a call to action?",                    "options": ["Takeaway", "Call to action"]},
    ],
    "refine": [
        {"id": "q_keep",  "region": "top",    "text": "Keep the current structure, or rework it?",          "options": ["Keep structure", "Rework structure"]},
        {"id": "q_tone",  "region": "left",   "text": "Quieter and more confident, or louder and bolder?",   "options": ["Quieter", "Louder"]},
        {"id": "q_focus", "region": "right",  "text": "Pull the eye to the data, or to the conclusion?",     "options": ["To the data", "To the conclusion"]},
    ],
    "condense": [
        {"id": "q_arc",   "region": "top",    "text": "Compress to one big idea, or preserve the arc?",      "options": ["One big idea", "Preserve the arc"]},
        {"id": "q_cut",   "region": "left",   "text": "What gets cut first — context, or supporting detail?","options": ["Cut context", "Cut detail"]},
        {"id": "q_close", "region": "bottom", "text": "Land on a number, or on the recommendation?",          "options": ["A number", "A recommendation"]},
        {"id": "q_focus", "region": "right",  "text": "Stat-led slides, or story-led slides?",                "options": ["Stat-led", "Story-led"]},
    ],
    "visualize": [
        {"id": "q_emphasis", "region": "top",    "text": "Lead with the formula, or the intuition?",                  "options": ["Formula first", "Intuition first"]},
        {"id": "q_layout",   "region": "right",  "text": "Plot front-and-center, or split with the explanation?",     "options": ["Plot center", "Split layout"]},
        {"id": "q_annot",    "region": "left",   "text": "Annotate the curve, or let it breathe?",                    "options": ["Annotated", "Clean"]},
        {"id": "q_palette",  "region": "bottom", "text": "Cool palette (teals), or warm accent (yellow)?",             "options": ["Cool", "Warm"]},
    ],
    "synthesize": [
        {"id": "q_chart", "region": "top",    "text": "Bars, or line over time?",                       "options": ["Bars", "Line"]},
        {"id": "q_label", "region": "right",  "text": "Label every value, or just the axis ticks?",     "options": ["Every value", "Just ticks"]},
        {"id": "q_focus", "region": "left",   "text": "Hero the biggest number, or the trend?",         "options": ["Hero the number", "Hero the trend"]},
        {"id": "q_close", "region": "bottom", "text": "Close on what the data means, or what to do?",   "options": ["What it means", "What to do"]},
    ],
}


# ---- tiny parsers --------------------------------------------------------

def _parse_single(text: str) -> dict:
    lines = [s.strip() for s in (text or "").split("\n") if s.strip()]
    return {
        "title":   lines[0] if lines else "Untitled slide",
        "bullets": lines[1:],
        "stat":    _pick_stat(text),
    }


def _parse_deck(raw: str) -> list[dict]:
    parts = [s.strip() for s in re.split(r"^\s*---+\s*$", raw or "", flags=re.M) if s.strip()]
    if not parts:
        return [_parse_single(raw)]
    return [_parse_single(p) for p in parts]


def _pick_stat(text: str | None) -> str:
    if not text:
        return "+14%"
    m = re.search(r"[+\-]\d+(?:\.\d+)?%?", text) or re.search(r"\d+(?:\.\d+)?%", text)
    return m.group(0) if m else "+14%"


# ---- palettes (per archetype) --------------------------------------------

PALETTES = {
    "editorial": {"bg": "#F6F2EA", "ink": "#1A1A1A", "accent": "#1E2761", "muted": "#7B7468", "sub": "#3D362B", "rule": "#1A1A1A"},
    "boldDark":  {"bg": "#0F1226", "ink": "#FFFFFF", "accent": "#F4B58A", "muted": "#A6ABC4", "sub": "#D6DAEC", "rule": "#F4B58A"},
    "boldLight": {"bg": "#FAFAF7", "ink": "#0F1226", "accent": "#F4B58A", "muted": "#6C7A89", "sub": "#334155", "rule": "#F4B58A"},
    "data":      {"bg": "#FFFFFF", "ink": "#0F172A", "accent": "#1E2761", "muted": "#6C7A89", "sub": "#334155", "rule": "#E5E7EB"},
}


# ---- per-direction slide builders ----------------------------------------
# Each returns a SlideSpec dict matching frontend/types.md exactly.

def _editorial_slide(role: str, c: dict, answers: dict) -> dict:
    p = PALETTES["editorial"]
    lead_q = answers.get("q_lead") == "Question first"
    eyebrow = {
        "singleton": "A QUESTION" if lead_q else "THE FINDING",
        "cover":     "IN BRIEF",
        "stat":      "THE NUMBER",
        "takeaways": "TO REMEMBER",
        "recap":     "TO REMEMBER",
    }.get(role, "A NOTE")

    blocks: list[dict] = [
        {"type": "text", "text": eyebrow, "x": 96, "y": 96, "w": 400, "h": 24,
         "font": "mono", "size": 13, "weight": 500, "color": p["muted"],
         "letterSpacing": 0.24, "transform": "uppercase"},
        {"type": "rule", "x": 96, "y": 132, "w": 28, "h": 1, "color": p["ink"]},
        {"type": "text", "text": "pptgpt  ·  " + (c.get("pageLabel") or "01 / 01"),
         "x": 96, "y": 656, "w": 400, "h": 20,
         "font": "mono", "size": 12, "weight": 400, "color": "#9A9286",
         "letterSpacing": 0.12, "transform": "uppercase"},
    ]

    if role == "stat":
        blocks += [
            {"type": "text", "text": c["stat"], "x": 96, "y": 192, "w": 1088, "h": 280,
             "font": "serif", "size": 240, "weight": 400, "italic": False,
             "color": p["ink"], "lineHeight": 0.95, "letterSpacing": -0.04},
            {"type": "text", "text": c["statLabel"], "x": 96, "y": 488, "w": 800, "h": 80,
             "font": "serif", "size": 28, "italic": True, "color": p["sub"], "lineHeight": 1.35},
        ]
    elif role in ("takeaways", "recap"):
        blocks += [
            {"type": "text", "text": c["title"], "x": 96, "y": 176, "w": 1000, "h": 100,
             "font": "serif", "size": 44, "weight": 500, "color": p["ink"], "lineHeight": 1.15},
            {"type": "bullets", "items": (c.get("bullets") or [])[:3],
             "x": 96, "y": 300, "w": 1000, "h": 280,
             "font": "serif", "size": 26, "weight": 400, "color": p["sub"],
             "lineHeight": 1.5, "marker": "number", "markerColor": p["muted"], "gap": 14},
        ]
    else:
        big = c["question"] if (role == "singleton" and lead_q) else c["title"]
        blocks += [
            {"type": "text", "text": big, "x": 96, "y": 188, "w": 1000, "h": 320,
             "font": "serif", "size": 84, "weight": 400, "italic": lead_q,
             "color": p["ink"], "lineHeight": 1.05, "letterSpacing": -0.02},
            {"type": "text", "text": c["support"], "x": 96, "y": 552, "w": 760, "h": 80,
             "font": "serif", "size": 22, "weight": 400, "color": p["sub"], "lineHeight": 1.45},
        ]

    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": p["bg"], "ink": p["ink"], "accent": p["accent"], "muted": p["muted"]},
            "blocks": blocks}


def _bold_slide(role: str, c: dict, answers: dict) -> dict:
    dark = answers.get("q_tone") not in ("Clean + light", "Quieter")
    p = PALETTES["boldDark"] if dark else PALETTES["boldLight"]
    eyebrow = {
        "singleton": "KEY POINT", "cover": "KEY POINT",
        "stat": "THE METRIC",
        "takeaways": "THE TAKEAWAY", "recap": "THE TAKEAWAY",
    }.get(role, "NOTE")

    blocks: list[dict] = [
        {"type": "rect", "x": 0, "y": 0, "w": 8, "h": 720, "fill": p["accent"]},
        {"type": "tag", "text": eyebrow, "x": 96, "y": 96, "w": 110, "h": 26,
         "fill": p["accent"], "color": "#0F1226", "size": 11},
    ]

    if role == "stat":
        blocks += [
            {"type": "text", "text": c["stat"], "x": 96, "y": 152, "w": 1088, "h": 380,
             "font": "sans", "size": 280, "weight": 700,
             "color": p["ink"], "lineHeight": 0.92, "letterSpacing": -0.05},
            {"type": "rule", "x": 96, "y": 560, "w": 64, "h": 3, "color": p["accent"]},
            {"type": "text", "text": c["statLabel"], "x": 96, "y": 588, "w": 900, "h": 60,
             "font": "sans", "size": 22, "weight": 500, "color": p["sub"],
             "letterSpacing": 0.06, "transform": "uppercase"},
        ]
    elif role in ("takeaways", "recap"):
        blocks += [
            {"type": "text", "text": c["title"], "x": 96, "y": 168, "w": 1088, "h": 140,
             "font": "sans", "size": 60, "weight": 700, "color": p["ink"], "lineHeight": 1.05, "letterSpacing": -0.02},
            {"type": "rule", "x": 96, "y": 332, "w": 64, "h": 3, "color": p["accent"]},
            {"type": "bullets", "items": (c.get("bullets") or [])[:3],
             "x": 96, "y": 368, "w": 1000, "h": 280,
             "font": "sans", "size": 28, "weight": 500, "color": p["sub"],
             "lineHeight": 1.45, "marker": "number", "markerColor": p["accent"], "gap": 12},
        ]
    else:
        blocks += [
            {"type": "text", "text": c["title"], "x": 96, "y": 168, "w": 1088, "h": 360,
             "font": "sans", "size": 120, "weight": 700,
             "color": p["ink"], "lineHeight": 0.98, "letterSpacing": -0.035},
            {"type": "rule", "x": 96, "y": 568, "w": 64, "h": 3, "color": p["accent"]},
            {"type": "text", "text": c["support"], "x": 96, "y": 600, "w": 900, "h": 80,
             "font": "sans", "size": 22, "weight": 400, "color": p["sub"], "lineHeight": 1.4},
        ]

    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": p["bg"], "ink": p["ink"], "accent": p["accent"], "muted": p["muted"]},
            "blocks": blocks}


def _data_slide(role: str, c: dict, answers: dict) -> dict:
    p = PALETTES["data"]
    cta = answers.get("q_close") in ("Call to action", "A recommendation")

    blocks: list[dict] = [
        {"type": "text", "text": "Q3 / SIGNAL", "x": 96, "y": 88, "w": 400, "h": 24,
         "font": "mono", "size": 13, "weight": 500, "color": p["muted"],
         "letterSpacing": 0.22, "transform": "uppercase"},
    ]

    if role == "stat":
        blocks += [
            {"type": "text", "text": c["stat"], "x": 96, "y": 144, "w": 1088, "h": 380,
             "font": "sans", "size": 280, "weight": 600,
             "color": p["accent"], "lineHeight": 0.9, "letterSpacing": -0.04},
            {"type": "text", "text": c["statLabel"], "x": 96, "y": 560, "w": 900, "h": 40,
             "font": "sans", "size": 22, "weight": 500,
             "color": p["muted"], "letterSpacing": 0.05, "transform": "uppercase"},
            {"type": "rule", "x": 96, "y": 624, "w": 200, "h": 1, "color": "#E5E7EB"},
        ]
    elif role in ("takeaways", "recap"):
        close_block = (
            {"type": "tag", "text": "BOOK A REVIEW →", "x": 96, "y": 624, "w": 188, "h": 32,
             "fill": p["accent"], "color": "#FFFFFF", "size": 12}
            if cta else
            {"type": "text", "text": "Compounds monthly · holds in down-quarters",
             "x": 96, "y": 632, "w": 760, "h": 20, "font": "mono", "size": 12, "weight": 400,
             "color": p["muted"], "letterSpacing": 0.08}
        )
        blocks += [
            {"type": "text", "text": c["title"], "x": 96, "y": 152, "w": 1088, "h": 120,
             "font": "serif", "size": 40, "weight": 500, "color": p["ink"], "lineHeight": 1.15},
            {"type": "rule", "x": 96, "y": 300, "w": 64, "h": 1, "color": p["accent"]},
            {"type": "bullets", "items": (c.get("bullets") or [])[:3],
             "x": 96, "y": 332, "w": 1088, "h": 280,
             "font": "sans", "size": 22, "weight": 400, "color": p["sub"],
             "lineHeight": 1.55, "marker": "dot", "markerColor": p["accent"], "gap": 14},
            close_block,
        ]
    else:
        numbers_first = answers.get("q_focus") not in ("Narrative up front", "To the conclusion")
        close_block = (
            {"type": "tag", "text": "BOOK A REVIEW →", "x": 96, "y": 624, "w": 188, "h": 32,
             "fill": p["accent"], "color": "#FFFFFF", "size": 12}
            if cta else
            {"type": "text", "text": "Compounds monthly · holds in down-quarters",
             "x": 96, "y": 632, "w": 760, "h": 20, "font": "mono", "size": 12, "weight": 400,
             "color": p["muted"], "letterSpacing": 0.08}
        )
        blocks += [
            {"type": "text", "text": c["stat"],
             "x": 96, "y": 144 if numbers_first else 380, "w": 760, "h": 260,
             "font": "sans", "size": 220, "weight": 600,
             "color": p["accent"], "lineHeight": 0.92, "letterSpacing": -0.04},
            {"type": "text", "text": c["statLabel"],
             "x": 96, "y": 410 if numbers_first else 644, "w": 760, "h": 40,
             "font": "sans", "size": 20, "weight": 500,
             "color": p["muted"], "letterSpacing": 0.04, "transform": "uppercase"},
            {"type": "rule", "x": 904, "y": 144, "w": 1, "h": 432, "color": "#E5E7EB"},
            {"type": "text", "text": c["title"],
             "x": 944, "y": 144 if numbers_first else 88, "w": 256, "h": 200,
             "font": "serif", "size": 28, "weight": 500, "color": p["ink"], "lineHeight": 1.2},
            {"type": "bullets", "items": (c.get("bullets") or [])[:3],
             "x": 944, "y": 320 if numbers_first else 200, "w": 256, "h": 280,
             "font": "sans", "size": 14, "weight": 400, "color": p["sub"],
             "lineHeight": 1.55, "marker": "dot", "markerColor": p["accent"], "gap": 8},
            close_block,
        ]

    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": p["bg"], "ink": p["ink"], "accent": p["accent"], "muted": p["muted"]},
            "blocks": blocks}


# ---- visualize-mode (3b1b-language plot slides) --------------------------

def _detect_plot(raw: str, title: str) -> dict:
    text = ((title or "") + " " + (raw or "")).lower()
    has = lambda w: w in text

    if has("damped") or has("oscillat") or has("decay") or has("rlc"):
        return {
            "fnId": "damped",
            "params": {"A": 1, "gamma": 0.3, "omega": 4},
            "paramSchema": [
                {"name": "A",     "label": "A · amplitude", "default": 1,   "min": 0,   "max": 2,   "step": 0.05},
                {"name": "gamma", "label": "γ · damping",   "default": 0.3, "min": 0,   "max": 1.5, "step": 0.05},
                {"name": "omega", "label": "ω · frequency", "default": 4,   "min": 0.5, "max": 10,  "step": 0.1},
            ],
            "xRange": [0, 8], "yRange": [-1.2, 1.2],
            "formula": "y = A · e^(−γx) · cos(ωx)",
        }
    if has("gaussian") or has("normal distribution") or has("bell") or has("normal"):
        return {
            "fnId": "gaussian",
            "params": {"A": 1, "mu": 0, "sigma": 1},
            "paramSchema": [
                {"name": "mu",    "label": "μ · mean",      "default": 0, "min": -3,  "max": 3, "step": 0.1},
                {"name": "sigma", "label": "σ · std-dev",   "default": 1, "min": 0.2, "max": 3, "step": 0.05},
                {"name": "A",     "label": "A · amplitude", "default": 1, "min": 0,   "max": 2, "step": 0.05},
            ],
            "xRange": [-4, 4], "yRange": [0, 1.2],
            "formula": "y = A · exp(−½((x−μ)/σ)²)",
        }
    if has("sigmoid") or has("logistic"):
        return {
            "fnId": "sigmoid",
            "params": {"A": 1, "k": 1, "x0": 0},
            "paramSchema": [
                {"name": "k",  "label": "k · steepness", "default": 1, "min": 0.2, "max": 5, "step": 0.1},
                {"name": "x0", "label": "x₀ · midpoint", "default": 0, "min": -3,  "max": 3, "step": 0.1},
            ],
            "xRange": [-5, 5], "yRange": [-0.1, 1.2],
            "formula": "y = 1 / (1 + e^(−k(x−x₀)))",
        }
    if has("exponential") or has("growth") or has("compound"):
        return {
            "fnId": "exponential",
            "params": {"A": 1, "k": 0.5},
            "paramSchema": [
                {"name": "k", "label": "k · rate",      "default": 0.5, "min": -1, "max": 1.5, "step": 0.05},
                {"name": "A", "label": "A · amplitude", "default": 1,   "min": 0,  "max": 2,   "step": 0.05},
            ],
            "xRange": [0, 5], "yRange": [0, 5],
            "formula": "y = A · e^(kx)",
        }
    return {
        "fnId": "sine",
        "params": {"A": 1, "omega": 1, "phi": 0},
        "paramSchema": [
            {"name": "A",     "label": "A · amplitude", "default": 1, "min": 0,         "max": 2,         "step": 0.05},
            {"name": "omega", "label": "ω · frequency", "default": 1, "min": 0.1,       "max": 4,         "step": 0.05},
            {"name": "phi",   "label": "φ · phase",     "default": 0, "min": -math.pi,  "max": math.pi,   "step": 0.1},
        ],
        "xRange": [-2 * math.pi, 2 * math.pi], "yRange": [-1.5, 1.5],
        "formula": "y = A · sin(ωx + φ)",
    }


def _plot_block(plot: dict, x: int, y: int, w: int, h: int, color: str, opts: dict | None = None) -> dict:
    opts = opts or {}
    return {
        "type": "plot", "x": x, "y": y, "w": w, "h": h,
        "bg": opts.get("bg") or "#0a0a14",
        "curves": [{"fn": plot["fnId"], "params": plot["params"], "color": color, "width": opts.get("width", 3)}],
        "xRange": plot["xRange"], "yRange": plot["yRange"],
        "paramSchema": plot["paramSchema"],
        "showGrid": opts.get("showGrid", True),
        "showAxes": opts.get("showAxes", True),
        "showTickLabels": opts.get("showTickLabels", True),
        "gridColor": opts.get("gridColor", "rgba(255,255,255,0.05)"),
        "axisColor": opts.get("axisColor", "rgba(255,255,255,0.55)"),
        "tickColor": "rgba(255,255,255,0.3)",
        "tickLabelColor": "rgba(255,255,255,0.55)",
        "xLabel": opts.get("xLabel"),
        "yLabel": opts.get("yLabel"),
        "paddingLeft": opts.get("paddingLeft"),
        "paddingRight": opts.get("paddingRight"),
        "paddingTop": opts.get("paddingTop"),
        "paddingBottom": opts.get("paddingBottom"),
    }


def _visualize_content(req: dict) -> dict:
    if req.get("outline"):
        s = req["outline"][0]
        return {
            "title": (s.get("title") or "Untitled visualization").strip(),
            "messages": [m.strip() for m in (s.get("messages") or [])[:3] if (m or "").strip()],
        }
    lines = [s.strip() for s in (req.get("rawContent") or "").split("\n") if s.strip()]
    return {"title": lines[0] if lines else "Untitled visualization",
            "messages": lines[1:4]}


def _manim_classic(content: dict, plot: dict, answers: dict, main: str, accent2: str) -> dict:
    annotated = answers.get("q_annot") == "Annotated"
    formula_first = answers.get("q_emphasis") == "Formula first"
    blocks = [
        {"type": "text", "text": "manim · 3b1b", "x": 64, "y": 56, "w": 400, "h": 24,
         "font": "mono", "size": 12, "weight": 500, "color": "rgba(255,255,255,0.45)",
         "letterSpacing": 0.22, "transform": "uppercase"},
        {"type": "text", "text": content["title"],
         "x": 64, "y": 90, "w": 1152, "h": 80,
         "font": "serif", "size": 44, "weight": 500, "italic": True,
         "color": "#fff", "letterSpacing": -0.005, "lineHeight": 1.1},
    ]
    if formula_first:
        blocks.append({"type": "text", "text": plot["formula"], "x": 64, "y": 168, "w": 1152, "h": 40,
                       "font": "serif", "italic": True, "size": 24, "color": accent2})
    blocks.append(_plot_block(plot, 140, 230 if formula_first else 200, 1000, 380 if formula_first else 410, main, {
        "showGrid": annotated, "showAxes": True, "showTickLabels": annotated,
        "xLabel": "x" if annotated else None, "yLabel": "y" if annotated else None,
    }))
    if not formula_first:
        blocks.append({"type": "text", "text": plot["formula"], "x": 64, "y": 640, "w": 1152, "h": 40,
                       "font": "serif", "italic": True, "size": 22, "color": accent2, "align": "center"})
    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#0F0F1E", "ink": "#fff", "accent": main, "muted": "rgba(255,255,255,0.6)"},
            "blocks": blocks}


def _split_lecture(content: dict, plot: dict, answers: dict, main: str, accent2: str) -> dict:
    formula_first = answers.get("q_emphasis") == "Formula first"
    annotated = answers.get("q_annot") == "Annotated"
    msgs = content["messages"] or ["Pick a parameter to tune", "Watch the curve respond", "Read off the relationship"]
    blocks: list[dict] = [
        {"type": "text", "text": "lecture · split", "x": 64, "y": 56, "w": 400, "h": 24,
         "font": "mono", "size": 12, "color": "rgba(255,255,255,0.45)",
         "letterSpacing": 0.22, "transform": "uppercase"},
        {"type": "text", "text": content["title"],
         "x": 64, "y": 96, "w": 540, "h": 120,
         "font": "serif", "italic": True, "size": 36, "weight": 500, "color": "#fff",
         "lineHeight": 1.15, "letterSpacing": -0.005},
    ]
    if formula_first:
        blocks.append({"type": "text", "text": plot["formula"], "x": 64, "y": 234, "w": 540, "h": 40,
                       "font": "serif", "italic": True, "size": 22, "color": accent2})
    blocks.append({"type": "bullets", "items": msgs[:3],
                   "x": 64, "y": 296 if formula_first else 248, "w": 540, "h": 360,
                   "font": "sans", "size": 19, "weight": 400,
                   "color": "rgba(255,255,255,0.85)", "lineHeight": 1.55,
                   "marker": "number", "markerColor": main, "gap": 16})
    if not formula_first:
        blocks.append({"type": "text", "text": plot["formula"], "x": 64, "y": 632, "w": 540, "h": 32,
                       "font": "serif", "italic": True, "size": 18, "color": accent2})
    blocks.append(_plot_block(plot, 660, 96, 556, 528, main, {
        "showGrid": True, "showAxes": True, "showTickLabels": annotated,
        "xLabel": "x", "yLabel": "y",
    }))
    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#0F0F1E", "ink": "#fff", "accent": main, "muted": "rgba(255,255,255,0.6)"},
            "blocks": blocks}


def _annotated_full(content: dict, plot: dict, answers: dict, main: str, accent2: str) -> dict:
    blocks: list[dict] = [
        _plot_block(plot, 0, 0, 1280, 720, main, {
            "bg": "#0F0F1E", "width": 4,
            "showGrid": True, "showAxes": True, "showTickLabels": True,
            "gridColor": "rgba(255,255,255,0.04)",
            "axisColor": "rgba(255,255,255,0.4)",
            "xLabel": "x", "yLabel": "y",
            "paddingLeft": 96, "paddingRight": 96, "paddingTop": 160, "paddingBottom": 110,
        }),
        {"type": "text", "text": "01 · visualize", "x": 64, "y": 56, "w": 240, "h": 20,
         "font": "mono", "size": 11, "weight": 500, "color": accent2,
         "letterSpacing": 0.22, "transform": "uppercase"},
        {"type": "text", "text": content["title"],
         "x": 64, "y": 80, "w": 800, "h": 80,
         "font": "serif", "italic": True, "size": 32, "weight": 500,
         "color": "#fff", "lineHeight": 1.15},
        {"type": "text", "text": plot["formula"],
         "x": 800, "y": 90, "w": 416, "h": 60,
         "font": "serif", "italic": True, "size": 22, "color": accent2, "align": "right"},
    ]
    if content["messages"]:
        blocks.append({"type": "text", "text": "— " + content["messages"][0],
                       "x": 64, "y": 656, "w": 1152, "h": 30,
                       "font": "serif", "italic": True, "size": 18,
                       "color": "rgba(255,255,255,0.7)"})
    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#0F0F1E", "ink": "#fff", "accent": main, "muted": "rgba(255,255,255,0.6)"},
            "blocks": blocks}


# ---- synthesize-mode (data → chart slides) ------------------------------

def _parse_data_table(text: str) -> dict | None:
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    if len(lines) < 2:
        return None
    sep = re.compile(r"\s*[,\t|]\s*|\s{2,}")
    headers = [h for h in sep.split(lines[0]) if h]
    if len(headers) < 2:
        return None
    rows: list[dict] = []
    for line in lines[1:]:
        cells = [c for c in sep.split(line) if c][:len(headers)]
        if len(cells) < 2:
            continue
        label = cells[0]
        try:
            value = float(re.sub(r"[$,%]", "", cells[1]))
        except ValueError:
            continue
        row = {"label": label, "value": value}
        if len(cells) > 2:
            try:
                row["secondary"] = float(re.sub(r"[$,%]", "", cells[2]))
            except ValueError:
                pass
        rows.append(row)
    if not rows:
        return None
    return {"headers": headers, "rows": rows}


def _synthesize_content(req: dict) -> dict:
    table = _parse_data_table(req.get("rawContent") or "")
    if not table:
        text = req.get("rawContent") or ""
        pairs: list[dict] = []
        for m in re.finditer(r"([A-Za-z0-9 _-]+?)\s*[:=]\s*([+\-]?\d+(?:\.\d+)?)", text):
            try:
                pairs.append({"label": m.group(1).strip(), "value": float(m.group(2))})
            except ValueError:
                pass
            if len(pairs) >= 8:
                break
        if len(pairs) >= 2:
            table = {"headers": ["label", "value"], "rows": pairs}
    if not table:
        table = {"headers": ["q", "rev"], "rows": [
            {"label": "Q1", "value": 32}, {"label": "Q2", "value": 38},
            {"label": "Q3", "value": 42}, {"label": "Q4", "value": 45},
        ]}
    title_line = ""
    if req.get("outline") and req["outline"]:
        title_line = req["outline"][0].get("title") or ""
    if not title_line:
        title_line = (req.get("rawContent") or "").split("\n")[0] or "Untitled data"
    messages = []
    if req.get("outline") and req["outline"]:
        messages = [m for m in (req["outline"][0].get("messages") or []) if m][:3]
    return {"title": title_line, "messages": messages,
            "data": table["rows"], "yLabel": table["headers"][1], "xLabel": table["headers"][0]}


def _synth_chart_slide(role: str, c: dict, answers: dict) -> dict:
    hero_number = answers.get("q_focus") == "Hero the number"
    close_action = answers.get("q_close") == "What to do"
    every_label = answers.get("q_label") != "Just ticks"
    chart_kind = "line" if answers.get("q_chart") == "Line" else "bar"

    if role == "editorial":
        return {
            "canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#F6F2EA", "ink": "#1A1A1A", "accent": "#1E2761", "muted": "#7B7468"},
            "blocks": [
                {"type": "text", "text": "THE DATA", "x": 96, "y": 96, "w": 400, "h": 24,
                 "font": "mono", "size": 13, "weight": 500, "color": "#7B7468",
                 "letterSpacing": 0.24, "transform": "uppercase"},
                {"type": "rule", "x": 96, "y": 132, "w": 28, "h": 1, "color": "#1A1A1A"},
                {"type": "text", "text": c["title"],
                 "x": 96, "y": 168, "w": 1088, "h": 80,
                 "font": "serif", "size": 38, "weight": 500, "italic": True,
                 "color": "#1A1A1A", "lineHeight": 1.15},
                {"type": "chart",
                 "x": 96, "y": 264, "w": 720, "h": 360,
                 "kind": chart_kind, "data": c["data"],
                 "bg": "#FFFFFF", "primaryColor": "#1E2761",
                 "axisColor": "#D8D2C4", "gridColor": "#EDE9DF", "labelColor": "#7B7468",
                 "showValueLabels": every_label},
                {"type": "bullets", "items": c["messages"] if c["messages"] else [c["yLabel"]],
                 "x": 864, "y": 264, "w": 320, "h": 360,
                 "font": "serif", "size": 17, "weight": 400, "italic": False,
                 "color": "#3D362B", "lineHeight": 1.55,
                 "marker": "dash", "markerColor": "#7B7468", "gap": 10},
                {"type": "text", "text": "— Next step: invest in Q4 expansion" if close_action
                    else "— " + (c["messages"][0] if c["messages"] else "A consistent trend"),
                 "x": 96, "y": 656, "w": 1088, "h": 30,
                 "font": "serif", "italic": True, "size": 18, "color": "#7B7468"},
            ],
        }
    if role == "bold":
        dark = answers.get("q_tone") not in ("Quieter", "Clean + light")
        bg = "#0F1226" if dark else "#FAFAF7"
        ink = "#FFFFFF" if dark else "#0F1226"
        sub = "#D6DAEC" if dark else "#334155"
        accent = "#F4B58A"
        return {
            "canvasW": 1280, "canvasH": 720,
            "palette": {"bg": bg, "ink": ink, "accent": accent, "muted": "#A6ABC4" if dark else "#6C7A89"},
            "blocks": [
                {"type": "rect", "x": 0, "y": 0, "w": 8, "h": 720, "fill": accent},
                {"type": "tag", "text": "THE NUMBERS", "x": 96, "y": 96, "w": 130, "h": 26,
                 "fill": accent, "color": "#0F1226", "size": 11},
                {"type": "text", "text": c["title"],
                 "x": 96, "y": 144, "w": 1088, "h": 80,
                 "font": "sans", "size": 48, "weight": 700,
                 "color": ink, "lineHeight": 1.05, "letterSpacing": -0.02},
                {"type": "chart",
                 "x": 96, "y": 240, "w": 1088, "h": 380,
                 "kind": chart_kind, "data": c["data"],
                 "bg": "#1A1E3D" if dark else "#FFFFFF", "primaryColor": accent,
                 "axisColor": "rgba(255,255,255,0.25)" if dark else "#E5E7EB",
                 "gridColor": "rgba(255,255,255,0.08)" if dark else "#F1F5F9",
                 "labelColor": "#D6DAEC" if dark else "#6C7A89",
                 "showValueLabels": every_label},
                {"type": "text", "text": "Action: invest in Q4 expansion" if close_action
                    else (c["messages"][0] if c["messages"] else "A consistent trend — and it accelerates"),
                 "x": 96, "y": 644, "w": 1088, "h": 40,
                 "font": "sans", "size": 18, "weight": 500, "color": sub, "letterSpacing": 0.02},
            ],
        }
    # data archetype
    top = max(c["data"], key=lambda r: r.get("value", 0)) if c["data"] else {"label": "", "value": 0}
    blocks: list[dict] = [
        {"type": "text", "text": "SIGNAL", "x": 96, "y": 88, "w": 400, "h": 24,
         "font": "mono", "size": 13, "weight": 500, "color": "#6C7A89",
         "letterSpacing": 0.22, "transform": "uppercase"},
    ]
    if hero_number:
        blocks += [
            {"type": "text", "text": str(top["value"]),
             "x": 96, "y": 128, "w": 560, "h": 240,
             "font": "sans", "size": 200, "weight": 600,
             "color": "#1E2761", "lineHeight": 0.92, "letterSpacing": -0.04},
            {"type": "text", "text": c["yLabel"] + " · " + str(top["label"]),
             "x": 96, "y": 392, "w": 560, "h": 28,
             "font": "sans", "size": 16, "weight": 500, "color": "#6C7A89",
             "letterSpacing": 0.06, "transform": "uppercase"},
        ]
    blocks += [
        {"type": "text", "text": c["title"],
         "x": 96, "y": 448 if hero_number else 128, "w": 560 if hero_number else 1088, "h": 60,
         "font": "serif", "size": 24 if hero_number else 36, "weight": 500, "color": "#0F172A", "lineHeight": 1.2},
        {"type": "chart",
         "x": 696 if hero_number else 96, "y": 128 if hero_number else 200,
         "w": 488 if hero_number else 1088, "h": 420 if hero_number else 380,
         "kind": chart_kind, "data": c["data"],
         "bg": "#FFFFFF", "primaryColor": "#1E2761",
         "axisColor": "#E5E7EB", "gridColor": "#F1F5F9", "labelColor": "#6C7A89",
         "showValueLabels": every_label},
    ]
    if c["messages"]:
        blocks.append({"type": "text", "text": "— " + c["messages"][0],
                       "x": 96, "y": 664, "w": 1088, "h": 30,
                       "font": "serif", "italic": True, "size": 16, "color": "#6C7A89"})
    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#FFFFFF", "ink": "#0F172A", "accent": "#1E2761", "muted": "#6C7A89"},
            "blocks": blocks}


# ---- content-extraction helpers -----------------------------------------

def _singleton_content(raw: str) -> dict:
    s = _parse_single(raw)
    return {
        "title":     s["title"],
        "question":  "What changed in Q3 — and is it durable?",
        "support":   " · ".join(s["bullets"]) or "Retention strong · churn down two points · revenue compounding",
        "stat":      s["stat"],
        "statLabel": "YoY revenue, Q3",
        "bullets":   s["bullets"] if s["bullets"] else [
            "Retention up 4 pts", "Churn down to 1.8%", "New cohort LTV +22%",
        ],
        "pageLabel": "01 / 01",
    }


def _condensed_deck(raw: str, answers: dict) -> dict:
    slides = _parse_deck(raw)
    cover = slides[0] if slides else {"title": "Untitled deck", "bullets": []}
    all_text = "\n".join([s["title"] for s in slides] + sum([s["bullets"] for s in slides], []))
    stat = _pick_stat(all_text)
    seen: dict[str, bool] = {}
    bullets: list[str] = []
    for s in slides:
        for b in s["bullets"]:
            if b not in seen:
                seen[b] = True
                bullets.append(b)
            if len(bullets) == 3:
                break
        if len(bullets) == 3:
            break
    one_big = answers.get("q_arc") == "One big idea"
    close_num = answers.get("q_close") == "A number"
    return {
        "cover": {"title": cover["title"], "support": " · ".join(bullets), "bullets": bullets,
                  "stat": stat, "statLabel": "HEADLINE NUMBER",
                  "question": "One question. One answer." if one_big else cover["title"],
                  "pageLabel": "01 / 03"},
        "stat":  {"title": cover["title"], "bullets": bullets, "stat": stat,
                  "statLabel": "THE NUMBER THAT MATTERS",
                  "question": "In one number:", "support": (bullets[0] if bullets else ""),
                  "pageLabel": "02 / 03"},
        "takeaways": {"title": f"Bottom line: {stat}" if close_num else "What to do next",
                      "bullets": bullets, "stat": stat, "statLabel": "OUTCOME",
                      "question": "What to do next", "support": (bullets[0] if bullets else ""),
                      "pageLabel": "03 / 03"},
    }


def _baseline_ir(req: dict) -> dict:
    slides = _parse_deck(req.get("rawContent") or "")
    c = _parse_single(req.get("rawContent") or "")
    mode = req.get("mode") or "draft"
    eyebrow = (f"DECK · {len(slides)} SLIDES · DRAFT" if mode == "condense"
               else "REWORK · DRAFT" if mode == "refine" else "DRAFT")
    blocks: list[dict] = [
        {"type": "text", "text": eyebrow,
         "x": 80, "y": 72, "w": 600, "h": 28,
         "font": "mono", "size": 14, "weight": 500,
         "color": "#6C7A89", "letterSpacing": 0.18, "transform": "uppercase"},
        {"type": "rule", "x": 80, "y": 116, "w": 36, "h": 2, "color": "#0F172A"},
        {"type": "text", "text": c["title"],
         "x": 80, "y": 160, "w": 1120, "h": 240,
         "font": "serif", "size": 64, "weight": 500,
         "color": "#0F172A", "lineHeight": 1.12, "letterSpacing": -0.015},
    ]
    if c["bullets"]:
        blocks.append({"type": "bullets", "items": c["bullets"][:5],
                       "x": 80, "y": 440, "w": 1120, "h": 240,
                       "font": "sans", "size": 22, "weight": 400,
                       "color": "#334155", "lineHeight": 1.5,
                       "marker": "dash", "markerColor": "#6C7A89", "gap": 6})
    return {"canvasW": 1280, "canvasH": 720,
            "palette": {"bg": "#FAFAF7", "ink": "#0F172A", "accent": "#1E2761", "muted": "#6C7A89"},
            "blocks": blocks}


# ---- direction assembly --------------------------------------------------

def _build_directions(req: dict) -> list[dict]:
    answers = req.get("answers") or {}
    mode = req.get("mode") or "draft"

    if mode == "synthesize":
        c = _synthesize_content(req)
        ed = _synth_chart_slide("editorial", c, answers)
        bo = _synth_chart_slide("bold",      c, answers)
        da = _synth_chart_slide("data",      c, answers)
        return [
            {"key": "editorial", "label": "Editorial Chart", "blurb": "Chart left, story column right, single takeaway closes.",
             "previewSpec": ed, "slides": [ed]},
            {"key": "bold",      "label": "Bold Chart",      "blurb": "Full-width chart with display-sans title and accent rule.",
             "previewSpec": bo, "slides": [bo]},
            {"key": "data",      "label": "Hero Number",     "blurb": "Headline value front-and-center; chart supports.",
             "previewSpec": da, "slides": [da]},
        ]

    if mode == "visualize":
        content = _visualize_content(req)
        plot = _detect_plot(req.get("rawContent") or "", content["title"])
        cool = answers.get("q_palette") != "Warm"
        main = "#4ec5ff" if cool else "#ffd166"
        accent2 = "#ffd166" if cool else "#4ec5ff"
        ma = _manim_classic(content, plot, answers, main, accent2)
        sl = _split_lecture(content, plot, answers, main, accent2)
        an = _annotated_full(content, plot, answers, main, accent2)
        return [
            {"key": "manim",     "label": "Manim Classic", "blurb": "Title up top, plot center, formula as the closing line.",
             "previewSpec": ma, "slides": [ma]},
            {"key": "split",     "label": "Split Lecture", "blurb": "Half lecture notes, half plot — sized for explanation.",
             "previewSpec": sl, "slides": [sl]},
            {"key": "annotated", "label": "Full Bleed",    "blurb": "Plot is the slide. Title and formula overlay the canvas.",
             "previewSpec": an, "slides": [an]},
        ]

    if mode == "condense":
        c = _condensed_deck(req.get("rawContent") or "", answers)

        def make(fn):
            slides = [
                fn("cover",     {**c["cover"],     "pageLabel": "01 / 03"}, answers),
                fn("stat",      {**c["stat"],      "pageLabel": "02 / 03"}, answers),
                fn("takeaways", {**c["takeaways"], "pageLabel": "03 / 03"}, answers),
            ]
            return {"previewSpec": slides[0], "slides": slides}

        ed = make(_editorial_slide); bo = make(_bold_slide); da = make(_data_slide)
        return [
            {"key": "editorial", "label": "Editorial Compression", "blurb": "Three slides. Eyebrow + serif headline + numbered close.", **ed},
            {"key": "bold",      "label": "Bold Throughline",       "blurb": "Single visual voice across all three. Display sans, accent rule.", **bo},
            {"key": "data",      "label": "Number First",           "blurb": "Cover defers to the stat. Story slides earn the page.", **da},
        ]

    # draft / refine
    content = _singleton_content(req.get("rawContent") or "")
    ed = _editorial_slide("singleton", content, answers)
    bo = _bold_slide("singleton",      content, answers)
    da = _data_slide("singleton",      content, answers)
    return [
        {"key": "editorial", "label": "Editorial Calm",   "blurb": "Serif headline, generous air, single eyebrow.",
         "previewSpec": ed, "slides": [ed]},
        {"key": "bold",      "label": "Bold Statement",   "blurb": "Display sans, weighted color block, accent rule.",
         "previewSpec": bo, "slides": [bo]},
        {"key": "data",      "label": "Data Foreground",  "blurb": "Stat hero, supporting column, light footer.",
         "previewSpec": da, "slides": [da]},
    ]


# ---- public entrypoint ---------------------------------------------------

def backend(req: dict) -> dict:
    """Equivalent of `window.mockBackend(req)` in the frontend.

    Pure function. Same shape in, same shape out — see `frontend/types.md`.
    """
    mode = req.get("mode") or "draft"
    answers = req.get("answers") or {}
    deck = QUESTION_DECKS.get(mode) or QUESTION_DECKS["draft"]
    answered = {k for k, v in answers.items() if v}
    remaining = [q for q in deck if q["id"] not in answered]

    slide_ir = _baseline_ir(req)
    wants_live = bool(req.get("wantsLiveDirections"))
    ready = len(remaining) == 0
    directions = _build_directions({**req, "mode": mode}) if (ready or wants_live) else []

    return {"slideIR": slide_ir, "questions": remaining, "directions": directions}
