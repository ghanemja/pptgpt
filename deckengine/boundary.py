"""
Boundary translators: IR + ResolvedSlide  ⇄  JSON / SlideSpec.

This is the ONLY place that adds '#' to colors (R1.5.1) and converts inches
to canvas-pixel coordinates the UI expects (R4: "the API … converts
inches→percent at the JSON boundary only; it performs no layout").

The frontend's SlideSpec uses a 1280×720 px coordinate space and `#RRGGBB`
hex. We translate at the boundary — no other module changes.
"""
from __future__ import annotations
from dataclasses import asdict

from .ir import Slide, ContentBlock, BlockKind, LayoutIntent, Deck, Theme, PALETTES
from .layout import ResolvedSlide, Box, CANVAS_W, CANVAS_H, resolve


SPEC_W = 1280  # design pixel canvas the UI was built against
SPEC_H = 720


def _hash(c: str) -> str:
    """Add the leading '#' (R1.5.1)."""
    return c if c.startswith("#") else f"#{c}"


def _font_key(font: str) -> str:
    """Map a Theme.header_font / body_font name to the SlideSpec font key."""
    f = (font or "").lower()
    if "georgia" in f or "serif" in f: return "serif"
    if "calibri" in f or "arial" in f or "sans" in f: return "sans"
    if "mono" in f or "courier" in f or "consolas" in f: return "mono"
    return "sans"


def _in_to_px(v: float, axis: str) -> float:
    if axis == "x" or axis == "w":
        return (v / CANVAS_W) * SPEC_W
    return (v / CANVAS_H) * SPEC_H


def _box_to_block(b: Box) -> dict:
    """Box -> SlideSpec block (a 'text' block; rules and rects come from roles)."""
    base = {
        "type": "text",
        "x": _in_to_px(b.x, "x"),
        "y": _in_to_px(b.y, "y"),
        "w": _in_to_px(b.w, "w"),
        "h": _in_to_px(b.h, "h"),
    }
    if b.role == "accent_rule" or b.role == "divider":
        # render as a thin filled rect at the same coords
        return {
            "type": "rule",
            "x": base["x"], "y": base["y"], "w": base["w"], "h": base["h"],
            "color": _hash(b.color),
        }
    return {
        **base,
        "text": b.text,
        "font": _font_key(b.font),
        "size": b.size_pt * (SPEC_H / (CANVAS_H * 72)) * 72,  # pt scaled
        "weight": 700 if b.bold else 400,
        "color": _hash(b.color),
        "align": b.align,
        "valign": b.valign,
        "role": b.role,
    }


def resolved_to_spec(rs: ResolvedSlide, theme: Theme) -> dict:
    """ResolvedSlide -> SlideSpec dict matching frontend/types.md."""
    blocks = [_box_to_block(b) for b in rs.boxes]
    return {
        "canvasW": SPEC_W,
        "canvasH": SPEC_H,
        "palette": {
            "bg": _hash(rs.bg),
            "ink": _hash(theme.fg_on_dark if theme.dark else theme.fg_on_light),
            "accent": _hash(theme.accent),
            "muted": _hash(theme.sub_on_dark if theme.dark else theme.sub_on_light),
        },
        "blocks": blocks,
        "archetype": rs.archetype,
    }


# ---- IR <-> dict (for /api/ir + ingest output) ---------------------------

def ir_block_to_dict(b: ContentBlock) -> dict:
    out = {"kind": b.kind.value, "emphasis": b.emphasis}
    if b.text is not None:   out["text"] = b.text
    if b.items is not None:  out["items"] = list(b.items)
    if b.value is not None:  out["value"] = b.value
    if b.label is not None:  out["label"] = b.label
    return out


def ir_slide_to_dict(s: Slide) -> dict:
    out = {
        "blocks": [ir_block_to_dict(b) for b in s.blocks],
        "intent": s.intent.value,
        "notes": s.notes,
    }
    # Surface visuals to the UI when ingest captured them. Empty list is
    # omitted so the JSON stays compact for slides with no images.
    if s.images:
        out["images"] = [
            {
                "path":       i.path,
                "alt":        i.alt,
                "source_idx": i.source_idx,
                "kind":       i.kind,
                **({"chart_data": i.chart_data} if i.chart_data else {}),
            }
            for i in s.images
        ]
    return out


def deck_to_dict(d: Deck) -> dict:
    return {
        "title": d.title,
        "slides": [ir_slide_to_dict(s) for s in d.slides],
        "theme": {"name": d.theme.name, "dark": d.theme.dark, "primary": _hash(d.theme.primary)},
    }


def dict_to_ir_block(d: dict) -> ContentBlock:
    return ContentBlock(
        kind=BlockKind(d.get("kind", "paragraph")),
        text=d.get("text"),
        items=d.get("items"),
        value=d.get("value"),
        label=d.get("label"),
        emphasis=int(d.get("emphasis") or 0),
    )


def dict_to_ir_slide(d: dict) -> Slide:
    from .ir import ImageRef
    intent_raw = d.get("intent") or "auto"
    try:
        intent = LayoutIntent(intent_raw)
    except ValueError:
        intent = LayoutIntent.AUTO
    images = []
    for im in (d.get("images") or []):
        images.append(ImageRef(
            path=im.get("path", ""),
            alt=im.get("alt", ""),
            source_idx=int(im.get("source_idx", 0)),
            kind=im.get("kind", "photo"),
            chart_data=im.get("chart_data"),
        ))
    return Slide(
        blocks=[dict_to_ir_block(b) for b in (d.get("blocks") or [])],
        intent=intent,
        notes=d.get("notes"),
        images=images,
    )


# ---- the "design" entrypoint --------------------------------------------

def design(slide: Slide, theme: Theme | None = None, archetype: str | None = None) -> dict:
    """Resolve one slide and translate to a SlideSpec dict."""
    theme = theme or Theme()
    rs = resolve(slide, theme, archetype=archetype)
    return resolved_to_spec(rs, theme)


def design_directions(slide: Slide, palettes: dict[str, Theme] | None = None) -> list[dict]:
    """R1.6.1: same Slide, multiple Themes -> multiple directions, identical
    geometry, differing palette. Cheap by design."""
    palettes = palettes or PALETTES
    out = []
    for key, theme in palettes.items():
        spec = design(slide, theme)
        out.append({
            "key": key,
            "label": theme.name,
            "blurb": f"Engine-resolved · {theme.name}",
            "previewSpec": spec,
            "slides": [spec],
        })
    return out


def design_deck_directions(deck: Deck, palettes: dict[str, Theme] | None = None) -> list[dict]:
    palettes = palettes or PALETTES
    out = []
    for key, theme in palettes.items():
        slides = [design(s, theme) for s in deck.slides]
        out.append({
            "key": key,
            "label": theme.name,
            "blurb": f"Engine-resolved deck · {theme.name}",
            "previewSpec": slides[0] if slides else None,
            "slides": slides,
        })
    return out
